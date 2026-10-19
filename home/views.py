from django.conf import settings
from django.db.models import Prefetch
from django.shortcuts import render

from cart.models import CartItem
from customization.models import CustomizationDraft
from orders.models import Order
from products.models import Product, ProductView


def _attach_primary_views(products):
    """Attach the first mockup of each product without extra queries."""

    for product in products:
        views = list(product.views.all())
        product.primary_view = next((view for view in views if view.mockup_image), None)
    return products


def index(request):
    products = list(
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("views", queryset=ProductView.objects.order_by("sort_order", "id"))
        )
        .order_by("title")[:6]
    )
    _attach_primary_views(products)

    featured_product = next(
        (product for product in products if product.primary_view),
        products[0] if products else None,
    )

    recent_drafts = []
    buy_again = []
    if request.user.is_authenticated:
        recent_drafts = list(
            CustomizationDraft.objects.filter(user=request.user, product__is_active=True)
            .select_related("product")
            .order_by("-updated_at")[:3]
        )

        latest_order = (
            Order.objects.filter(user=request.user)
            .select_related("cart")
            .prefetch_related(
                Prefetch("cart__items", queryset=CartItem.objects.select_related("product"))
            )
            .order_by("-created_at")
            .first()
        )
        if latest_order:
            seen_products = set()
            for item in latest_order.cart.items.all():
                if item.product.is_active and item.product_id not in seen_products:
                    seen_products.add(item.product_id)
                    buy_again.append(item)
                if len(buy_again) == 3:
                    break

    return render(
        request,
        "home/index.html",
        {
            "products": products,
            "featured_product": featured_product,
            "recent_drafts": recent_drafts,
            "buy_again": buy_again,
            "max_upload_mb": settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        },
    )
