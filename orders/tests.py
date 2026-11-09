from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ShippingAddress
from cart.context import CART_SESSION_KEY, line_key
from cart.models import Cart, CartItem
from products.models import Product
from promotions.models import Promotion, PromotionTier

from .models import Order
from .services import (
    CheckoutError,
    commit_stock,
    expired_holds,
    place_order,
    release_stock,
    reserve_stock,
)

User = get_user_model()

SHIPPING_DATA = {
    "full_name": "Ada Shopper",
    "line_1": "1 Main Street",
    "line_2": "",
    "city": "Copenhagen",
    "postal_code": "1000",
    "country": "Denmark",
}


class CheckoutFixtureMixin:
    """A signed-in customer with ten EUR 10.00 units in stock."""

    def create_fixture(self, stock_quantity=10):
        self.user = User.objects.create_user(
            username="shopper",
            password="s3cret-pass",
        )
        self.product = Product.objects.create(
            title="Classic Tee",
            base_price=Decimal("10.00"),
            stock_quantity=stock_quantity,
        )
        self.address = ShippingAddress.objects.create(
            user=self.user,
            full_name="Ada Shopper",
            line_1="1 Main Street",
            city="Copenhagen",
            postal_code="1000",
            country="Denmark",
        )

    def set_session_cart(self, lines):
        """``lines`` is a list of ``(product, quantity, draft_id)`` tuples."""

        session = self.client.session
        session[CART_SESSION_KEY] = {
            line_key(product.pk, draft_id): {
                "product_id": product.pk,
                "draft_id": draft_id,
                "quantity": quantity,
            }
            for product, quantity, draft_id in lines
        }
        session.save()

    def make_order(self, quantity=2, product=None, user=None):
        product = product or self.product
        user = user or self.user
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        return Order.objects.create(
            user=user,
            cart=cart,
            shipping_address=self.address,
        )


class CheckoutViewTests(CheckoutFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()
        self.client.force_login(self.user)

    def test_checkout_page_lists_the_cart_and_asks_for_the_address(self):
        self.set_session_cart([(self.product, 2, None)])

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shipping address")
        self.assertContains(response, "Classic Tee")
        self.assertContains(response, "20.00")

    def test_the_latest_address_is_prefilled(self):
        self.set_session_cart([(self.product, 1, None)])

        response = self.client.get(reverse("orders:checkout"))

        self.assertContains(response, 'value="1 Main Street"')

    def test_placing_an_order_takes_the_units_out_of_the_stock(self):
        self.set_session_cart([(self.product, 2, None)])

        response = self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        self.assertRedirects(response, reverse("orders:list"))
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, Decimal("20.00"))
        self.assertEqual(order.currency, "EUR")
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.stock_state, Order.StockState.COMMITTED)
        self.assertEqual(order.cart.items.count(), 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)
        self.assertEqual(self.product.reserved_quantity, 0)
        # The cart is emptied so the customer cannot order twice.
        self.assertEqual(self.client.session[CART_SESSION_KEY], {})

    def test_promotions_change_the_price_but_never_the_units(self):
        promotion = Promotion.objects.create(name="T-shirt bundle", product=self.product)
        PromotionTier.objects.create(
            promotion=promotion,
            quantity=5,
            price=Decimal("40.00"),
        )
        # 5 units for EUR 40 plus 2 units at the base price: EUR 60, not EUR 70.
        self.set_session_cart([(self.product, 7, None)])

        response = self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        self.assertRedirects(response, reverse("orders:list"))
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total_amount, Decimal("60.00"))

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertEqual(order.cart.items.get().quantity, 7)

    def test_two_lines_of_the_same_product_are_one_cart_item(self):
        self.set_session_cart(
            [
                (self.product, 2, None),
                (self.product, 3, "6f6a1c1e-0f1d-4c62-9d7f-2f0c4a1b1c11"),
            ]
        )

        response = self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        self.assertRedirects(response, reverse("orders:list"))
        items = CartItem.objects.filter(cart__user=self.user)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().quantity, 5)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_insufficient_stock_rolls_everything_back(self):
        self.product.stock_quantity = 3
        self.product.save(update_fields=["stock_quantity"])
        self.set_session_cart([(self.product, 5, None)])

        response = self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "can be ordered right now")
        self.assertFalse(Order.objects.exists())
        self.assertEqual(Cart.objects.count(), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        self.assertEqual(self.product.reserved_quantity, 0)
        # The address stored for the attempt is dropped again.
        self.assertEqual(ShippingAddress.objects.filter(user=self.user).count(), 1)

    def test_an_empty_cart_never_reaches_the_checkout(self):
        response = self.client.get(reverse("orders:checkout"))

        self.assertRedirects(response, reverse("cart:detail"))
        self.assertFalse(Order.objects.exists())

    def test_unpublished_products_leave_the_cart_empty(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        self.set_session_cart([(self.product, 1, None)])

        response = self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        self.assertRedirects(response, reverse("cart:detail"))
        self.assertFalse(Order.objects.exists())

    def test_the_shipping_address_is_required(self):
        self.set_session_cart([(self.product, 1, None)])

        response = self.client.post(reverse("orders:checkout"), {"full_name": "Ada"})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_anonymous_customers_are_sent_to_the_login_page(self):
        self.client.logout()

        response = self.client.get(reverse("orders:checkout"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

    def test_order_history_lists_the_items_and_the_total(self):
        self.set_session_cart([(self.product, 2, None)])
        self.client.post(reverse("orders:checkout"), SHIPPING_DATA)

        response = self.client.get(reverse("orders:list"))

        self.assertContains(response, "Classic Tee &times; 2")
        self.assertContains(response, "20.00")



class StockServiceTests(CheckoutFixtureMixin, TestCase):
    """The reserve/commit/release cycle the Stripe webhook will drive."""

    def setUp(self):
        self.create_fixture()

    def session_cart(self, quantity=1):
        return {
            line_key(self.product.pk): {
                "product_id": self.product.pk,
                "draft_id": None,
                "quantity": quantity,
            }
        }

    def test_reserving_holds_the_units_without_taking_them_off_the_shelf(self):
        order = self.make_order(quantity=4)

        reserved = reserve_stock(order)

        self.assertEqual(reserved.stock_state, Order.StockState.RESERVED)
        self.assertGreater(reserved.reserved_until, timezone.now())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)
        self.assertEqual(self.product.reserved_quantity, 4)
        self.assertEqual(self.product.available_quantity, 6)

    def test_reserving_twice_reserves_once(self):
        order = self.make_order(quantity=4)

        reserve_stock(order)
        reserve_stock(Order.objects.get(pk=order.pk))

        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 4)

    def test_committing_turns_the_hold_into_a_sale(self):
        order = self.make_order(quantity=4)
        reserve_stock(order)

        committed = commit_stock(Order.objects.get(pk=order.pk))

        self.assertEqual(committed.stock_state, Order.StockState.COMMITTED)
        self.assertIsNone(committed.reserved_until)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 0)
        self.assertEqual(self.product.stock_quantity, 6)

    def test_committing_twice_takes_the_units_once(self):
        order = self.make_order(quantity=4)
        reserve_stock(order)

        commit_stock(order)
        commit_stock(Order.objects.get(pk=order.pk))

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 6)

    def test_committing_without_a_hold_decrements_the_shelf(self):
        order = self.make_order(quantity=3)

        commit_stock(order)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 7)
        self.assertEqual(self.product.reserved_quantity, 0)

    def test_releasing_gives_the_held_units_back(self):
        order = self.make_order(quantity=4)
        reserve_stock(order)

        released = release_stock(Order.objects.get(pk=order.pk))

        self.assertEqual(released.stock_state, Order.StockState.RELEASED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 0)
        self.assertEqual(self.product.stock_quantity, 10)

    def test_a_hold_blocks_the_last_units(self):
        reserve_stock(self.make_order(quantity=10))

        with self.assertRaises(CheckoutError):
            place_order(self.user, self.session_cart(1), self.address)

        self.assertEqual(Order.objects.count(), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.available_quantity, 0)

    def test_an_empty_cart_is_rejected(self):
        with self.assertRaises(CheckoutError):
            place_order(self.user, {}, self.address)

    def test_an_unpublished_product_cannot_be_ordered(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        with self.assertRaises(CheckoutError):
            place_order(self.user, self.session_cart(1), self.address)

        self.assertFalse(Order.objects.exists())


class ExpireStockHoldsCommandTests(CheckoutFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()

    def test_expired_holds_are_released_and_the_payment_marked_failed(self):
        order = self.make_order(quantity=2)
        reserve_stock(order, minutes=-5)
        self.assertEqual(expired_holds().count(), 1)

        output = StringIO()
        call_command("expire_stock_holds", stdout=output)

        self.assertIn("Released 1 expired stock hold", output.getvalue())
        order.refresh_from_db()
        self.assertEqual(order.stock_state, Order.StockState.RELEASED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 0)
        self.assertEqual(self.product.stock_quantity, 10)

    def test_a_dry_run_changes_nothing(self):
        order = self.make_order(quantity=2)
        reserve_stock(order, minutes=-5)

        output = StringIO()
        call_command("expire_stock_holds", "--dry-run", stdout=output)

        self.assertIn("would be released", output.getvalue())
        order.refresh_from_db()
        self.assertEqual(order.stock_state, Order.StockState.RESERVED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 2)

    def test_a_hold_inside_its_window_survives(self):
        order = self.make_order(quantity=2)
        reserve_stock(order)

        call_command("expire_stock_holds", stdout=StringIO())

        order.refresh_from_db()
        self.assertEqual(order.stock_state, Order.StockState.RESERVED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 2)
