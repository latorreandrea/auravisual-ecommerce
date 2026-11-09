from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import redirect, render

from accounts.models import ShippingAddress
from cart.context import CART_SESSION_KEY, _build_cart_summary
from cart.models import CartItem

from .forms import CheckoutForm
from .models import Order
from .services import CheckoutError, place_order


@login_required
def order_list(request):
    orders = (
        Order.objects.filter(user=request.user)
        .select_related("shipping_address")
        .prefetch_related(
            Prefetch(
                "cart__items",
                queryset=CartItem.objects.select_related("product"),
            )
        )
        .order_by("-created_at")
    )
    return render(request, "orders/list.html", {"orders": orders})


@login_required
def checkout(request):
    """Collect the shipping address and turn the session cart into an order."""

    session_cart = request.session.get(CART_SESSION_KEY, {})
    cart_summary = _build_cart_summary(session_cart, request.user)
    if not cart_summary["items"]:
        messages.error(request, "Your cart is empty: add a product before checking out.")
        return redirect("cart:detail")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            try:
                order = place_order(request.user, session_cart, address)
            except CheckoutError as error:
                # The transaction rolled back: nothing was charged and no stock
                # moved. Drop the address too, so a retry cannot pile up rows.
                address.delete()
                for problem in error.messages:
                    messages.error(request, problem)
            else:
                request.session[CART_SESSION_KEY] = {}
                units = order.item_count
                messages.success(
                    request,
                    f"Order #{order.pk} placed: {units} "
                    f'{"unit" if units == 1 else "units"} for '
                    f"{order.currency} {order.total_amount}.",
                )
                return redirect("orders:list")
    else:
        latest_address = (
            ShippingAddress.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        initial = (
            {
                field: getattr(latest_address, field)
                for field in CheckoutForm.Meta.fields
            }
            if latest_address is not None
            else {}
        )
        form = CheckoutForm(initial=initial)

    return render(
        request,
        "orders/checkout.html",
        {
            "form": form,
            "cart_summary": cart_summary,
            "reservation_minutes": settings.STOCK_RESERVATION_MINUTES,
        },
    )
