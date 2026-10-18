from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from customization.models import CustomizationDraft
from products.models import Product

from .context import (
    CART_SESSION_KEY,
    _build_cart_summary,
    line_key,
    normalize_session_cart,
)


def cart_detail(request):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    return render(
        request,
        "cart/detail.html",
        {"cart_summary": _build_cart_summary(session_cart, request.user)},
    )


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)

    draft = None
    draft_id = request.POST.get("draft_id") or ""
    if draft_id:
        if not request.user.is_authenticated:
            messages.error(request, "Sign in to add a customized product to your cart.")
            return redirect("account_login")
        try:
            draft = CustomizationDraft.objects.filter(
                pk=draft_id,
                user=request.user,
                product=product,
            ).first()
        except (ValidationError, ValueError):
            draft = None
        if draft is None:
            messages.error(request, "That customization draft is no longer available.")
            return redirect("products:list")

    session_cart = normalize_session_cart(request.session.get(CART_SESSION_KEY, {}))
    current_qty = sum(
        line["quantity"]
        for line in session_cart.values()
        if line["product_id"] == product.pk
    )
    if current_qty + 1 > product.stock_quantity:
        messages.error(request, f"Not enough stock for {product.title}.")
        return redirect("products:list")

    key = line_key(product.pk, draft.pk if draft else None)
    line = session_cart.get(
        key,
        {
            "product_id": product.pk,
            "draft_id": str(draft.pk) if draft else None,
            "quantity": 0,
        },
    )
    line["quantity"] += 1
    session_cart[key] = line

    request.session[CART_SESSION_KEY] = session_cart
    suffix = " with your customization" if draft else ""
    messages.success(request, f"{product.title}{suffix} was added to your cart.")
    if draft:
        return redirect("cart:detail")
    return redirect("products:list")


@require_POST
def remove_from_cart(request, line_key):
    session_cart = normalize_session_cart(request.session.get(CART_SESSION_KEY, {}))
    if line_key not in session_cart:
        messages.error(request, "That item is not in your cart.")
        return redirect("cart:detail")

    session_cart[line_key]["quantity"] -= 1
    if session_cart[line_key]["quantity"] <= 0:
        session_cart.pop(line_key)

    request.session[CART_SESSION_KEY] = session_cart
    messages.success(request, "Your cart has been updated.")
    return redirect("cart:detail")


@require_POST
def clear_cart(request):
    request.session[CART_SESSION_KEY] = {}
    messages.success(request, "Your cart has been emptied.")
    return redirect("cart:detail")
