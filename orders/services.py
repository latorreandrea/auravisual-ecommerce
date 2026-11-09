"""Order placement and stock bookkeeping.

Stock moves in three steps, so the same code works with an asynchronous payment
provider (Stripe) later:

* ``reserve_stock`` holds the ordered units (``Product.reserved_quantity``), so
  nobody else can buy them while the customer is on the payment page;
* ``commit_stock`` turns the hold into a permanent decrement of
  ``Product.stock_quantity`` once the money arrived;
* ``release_stock`` gives the units back when the order is cancelled, the
  payment fails or the hold expires (``expire_stock_holds`` command).

``place_order`` runs reserve and commit inside one transaction because the
storefront has no gateway yet: an order is final the moment it is placed. When
Stripe is wired in, the checkout will only reserve and the payment webhook will
commit (or release), without touching anything else.

Promotions never change the number of units: with the ``5 for EUR 40`` break,
seven units still take seven units out of the stock, they are just charged
EUR 60 instead of EUR 70.

Every write uses ``F()`` expressions with a guard in the ``filter()``, so two
concurrent checkouts can never oversell: the second one updates zero rows and
fails with a readable ``CheckoutError``.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from cart.context import normalize_session_cart
from cart.models import Cart, CartItem
from products.models import Product
from promotions.services import active_promotions_for, price_line

from .models import Order


class CheckoutError(Exception):
    """A checkout cannot be completed.

    ``messages`` holds one readable line per problem (a product that ran out of
    stock, a product that was unpublished, ...), ready for ``messages.error``.
    """

    def __init__(self, messages):
        if isinstance(messages, str):
            messages = [messages]
        self.messages = list(messages)
        super().__init__(" ".join(self.messages))


def _aggregate_quantities(lines):
    """Sum the units per product: two cart lines can share the same product.

    The session cart keys a line by ``<product>:<draft>``, so a customer can hold
    the plain product and a customized version of it at the same time. They are
    the same physical stock, so the units must be added up.
    """

    quantities = {}
    for line in lines.values():
        product_id = line["product_id"]
        quantities[product_id] = quantities.get(product_id, 0) + line["quantity"]
    return quantities


def _lock_products(product_ids):
    return {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=list(product_ids))
    }


def _availability_problems(quantities, products):
    problems = []
    for product_id, quantity in quantities.items():
        product = products.get(product_id)
        if product is None or not product.is_active:
            problems.append(
                "One of the products in your cart is no longer available. "
                "Remove it from the cart and try again."
            )
            continue
        if quantity < 1:
            problems.append(f'The quantity of "{product.title}" is not valid.')
            continue
        if quantity > product.available_quantity:
            problems.append(
                f'Only {product.available_quantity} of "{product.title}" '
                f"can be ordered right now."
            )
    return problems


def _priced_lines(lines, products):
    """Price every cart line exactly like the cart page does.

    The order total is the sum of the line totals, so it always matches what the
    customer saw in the cart, promotions included.
    """

    promotions_map = active_promotions_for(products)
    priced = []
    for line_key, line in lines.items():
        product = products.get(line["product_id"])
        if product is None:
            continue
        priced.append(
            {
                "line_key": line_key,
                "product": product,
                "quantity": line["quantity"],
                "pricing": price_line(
                    product,
                    line["quantity"],
                    promotions_map.get(product.pk, ()),
                ),
            }
        )
    return priced


@transaction.atomic
def place_order(user, session_cart, shipping_address):
    """Create the order for a session cart and take its units out of the stock.

    Returns the saved ``Order``. Raises ``CheckoutError`` when the cart is empty
    or a product is unavailable: the transaction rolls back, so neither the order
    nor a stock movement survives a failed checkout.
    """

    lines = normalize_session_cart(session_cart)
    if not lines:
        raise CheckoutError("Your cart is empty.")

    quantities = _aggregate_quantities(lines)
    # Lock before reading, so the availability check cannot be invalidated by a
    # checkout that runs at the same time.
    products = _lock_products(quantities)
    problems = _availability_problems(quantities, products)
    if problems:
        raise CheckoutError(problems)

    priced = _priced_lines(lines, products)
    total = sum(
        (entry["pricing"].net_total for entry in priced),
        Decimal("0.00"),
    )

    cart = Cart.objects.create(user=user)
    CartItem.objects.bulk_create(
        [
            CartItem(cart=cart, product=products[product_id], quantity=quantity)
            for product_id, quantity in quantities.items()
        ]
    )
    order = Order.objects.create(
        user=user,
        cart=cart,
        shipping_address=shipping_address,
        # No payment provider yet: the storefront order is paid on the spot.
        payment_status=Order.PaymentStatus.PAID,
        total_amount=total,
        currency=settings.STORE_CURRENCY,
    )
    reserve_stock(order)
    commit_stock(order)
    return order


@transaction.atomic
def reserve_stock(order, minutes=None):
    """Hold the units of ``order`` so nobody else can buy them.

    Idempotent: an order that already left ``NONE`` is returned untouched, which
    is what a payment webhook needs when it receives the same event twice.
    """

    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.stock_state != Order.StockState.NONE:
        return order

    quantities = {
        item.product_id: item.quantity
        for item in order.cart.items.select_related("product")
    }
    products = _lock_products(quantities)
    problems = _availability_problems(quantities, products)
    if problems:
        raise CheckoutError(problems)

    for product_id, quantity in quantities.items():
        reserved = Product.objects.filter(
            pk=product_id,
            is_active=True,
            reserved_quantity__lte=F("stock_quantity") - quantity,
        ).update(reserved_quantity=F("reserved_quantity") + quantity)
        if not reserved:
            raise CheckoutError(
                f'"{products[product_id].title}" sold out while the order was '
                f"being placed. Please review the cart."
            )

    order.stock_state = Order.StockState.RESERVED
    order.reserved_until = timezone.now() + timedelta(
        minutes=settings.STOCK_RESERVATION_MINUTES if minutes is None else minutes
    )
    order.save(update_fields=["stock_state", "reserved_until"])
    return order


@transaction.atomic
def commit_stock(order):
    """Turn the hold of ``order`` into a permanent stock decrement."""

    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.stock_state in {Order.StockState.COMMITTED, Order.StockState.RELEASED}:
        return order

    quantities = {item.product_id: item.quantity for item in order.cart.items.all()}
    for product_id, quantity in quantities.items():
        if order.stock_state == Order.StockState.RESERVED:
            # The units are already held by this order: free the hold and take
            # them off the shelf in a single statement.
            committed = Product.objects.filter(
                pk=product_id,
                reserved_quantity__gte=quantity,
            ).update(
                reserved_quantity=F("reserved_quantity") - quantity,
                stock_quantity=F("stock_quantity") - quantity,
            )
        else:
            # Nothing was reserved (an order created by hand, or a gateway that
            # reports a payment before the hold): decrement the shelf directly.
            committed = Product.objects.filter(
                pk=product_id,
                stock_quantity__gte=quantity,
            ).update(stock_quantity=F("stock_quantity") - quantity)
        if not committed:
            raise CheckoutError(
                f"The stock of order #{order.pk} could not be updated for product "
                f"{product_id}. Please check the shelf before shipping it."
            )

    order.stock_state = Order.StockState.COMMITTED
    order.reserved_until = None
    order.save(update_fields=["stock_state", "reserved_until"])
    return order


@transaction.atomic
def release_stock(order):
    """Give the held units of ``order`` back to the shelf."""

    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.stock_state != Order.StockState.RESERVED:
        return order

    for item in order.cart.items.all():
        Product.objects.filter(
            pk=item.product_id,
            reserved_quantity__gte=item.quantity,
        ).update(reserved_quantity=F("reserved_quantity") - item.quantity)

    order.stock_state = Order.StockState.RELEASED
    order.reserved_until = None
    order.save(update_fields=["stock_state", "reserved_until"])
    return order


def expired_holds(now=None):
    """Reserved orders whose hold is over (used by ``expire_stock_holds``)."""

    return Order.objects.filter(
        stock_state=Order.StockState.RESERVED,
        reserved_until__lt=now or timezone.now(),
    )
