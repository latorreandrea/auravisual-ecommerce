from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.models import Product

from .context import CART_SESSION_KEY, _build_cart_summary


def cart_detail(request):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    return render(request, "cart/detail.html", {"cart_summary": _build_cart_summary(session_cart)})


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    session_cart = request.session.get(CART_SESSION_KEY, {})
    current_qty = int(session_cart.get(str(product_id), 0))
    if current_qty + 1 > product.stock_quantity:
        messages.error(request, f"Not enough stock for {product.name}.")
        return redirect("products:list")

    session_cart[str(product_id)] = current_qty + 1
    request.session[CART_SESSION_KEY] = session_cart
    messages.success(request, f"{product.name} was added to your cart.")
    return redirect("products:list")


@require_POST
def remove_from_cart(request, product_id):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    key = str(product_id)
    if key not in session_cart:
        messages.error(request, "That product is not in your cart.")
        return redirect("cart:detail")

    new_qty = session_cart[key] - 1
    if new_qty <= 0:
        session_cart.pop(key)
    else:
        session_cart[key] = new_qty

    request.session[CART_SESSION_KEY] = session_cart
    messages.success(request, "Your cart has been updated.")
    return redirect("cart:detail")


@require_POST
def clear_cart(request):
    request.session[CART_SESSION_KEY] = {}
    messages.success(request, "Your cart has been emptied.")
    return redirect("cart:detail")
