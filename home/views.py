from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.models import F, Prefetch
from django.shortcuts import render

from cart.models import CartItem
from customization.models import CustomizationDraft
from orders.models import Order
from products.models import Product, ProductView
from promotions.models import Promotion
from promotions.services import attach_promotion_badges

# The home page only teases the catalogue: it shows the newest products and a
# link to the paginated catalogue (see products.views.product_list).
LATEST_PRODUCTS_LIMIT = 6
# The workspace grid fits four miniatures per row, so two full rows are enough.
WORKSPACE_PROJECT_LIMIT = 8


def _attach_primary_views(products):
    """Attach the first mockup of each product without extra queries."""

    for product in products:
        views = list(product.views.all())
        product.primary_view = next((view for view in views if view.mockup_image), None)
    return products


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(default)
        except (TypeError, ValueError):
            return 0.0


def _rounded(value):
    return round(float(value), 3)


def _stored_preview_url(draft):
    """Return a saved preview URL only when the file really exists."""

    if draft is None or not draft.preview_webp_url:
        return ""

    field = draft.preview_webp_url
    try:
        if not field.storage.exists(field.name):
            return ""
        return field.url
    except (OSError, ValueError):
        return ""


def _first_customized_image(draft):
    """Return ``(view, image)`` for the first customized side of the project."""

    if draft is None or not isinstance(draft.configuration_json, dict):
        return None, None

    views = {view.pk: view for view in draft.product.views.all()}
    for entry in draft.configuration_json.get("views", []):
        if not isinstance(entry, dict):
            continue
        image = entry.get("image")
        if not isinstance(image, dict) or not image.get("asset_path"):
            continue
        view = views.get(_as_int(entry.get("product_view_id")))
        if view is not None:
            return view, image
    return None, None


def _build_card_layers(view, image):
    """Translate the saved placement into SVG-ready layer data.

    Values stay in mockup pixels and are rendered inside an SVG ``viewBox``, so
    the clipping and clockwise rotation match the editor and
    ``customization.services.rendering.render_view`` exactly.
    """

    if view is None or not isinstance(image, dict):
        return []

    area = view.print_area
    canvas_width = float(view.canvas_width_px or 0)
    canvas_height = float(view.canvas_height_px or 0)
    if area is None or canvas_width <= 0 or canvas_height <= 0:
        return []

    asset_path = image.get("asset_path")
    asset_url = image.get("asset_url")
    if not isinstance(asset_path, str):
        asset_path = ""
    if not isinstance(asset_url, str):
        asset_url = ""
    try:
        if asset_path:
            if not default_storage.exists(asset_path):
                return []
            asset_url = asset_url or default_storage.url(asset_path)
    except (OSError, ValueError):
        return []
    if not asset_url:
        return []

    transform = image.get("transform")
    if not isinstance(transform, dict):
        transform = {}
    x = _as_float(transform.get("x"), area.x)
    y = _as_float(transform.get("y"), area.y)
    width = _as_float(transform.get("width"), area.width)
    height = _as_float(transform.get("height"), area.height)
    rotation = _as_float(transform.get("rotation"), area.rotation)
    if width <= 0 or height <= 0:
        return []

    return [
        {
            "zone_x": _rounded(area.x),
            "zone_y": _rounded(area.y),
            "zone_width": _rounded(area.width),
            "zone_height": _rounded(area.height),
            "x": _rounded(x),
            "y": _rounded(y),
            "width": _rounded(width),
            "height": _rounded(height),
            "rotation": _rounded(rotation),
            "center_x": _rounded(x + width / 2),
            "center_y": _rounded(y + height / 2),
            "asset_url": asset_url,
            "alt": image.get("original_name") or view.name,
        }
    ]

def _card_views(product):
    return [view for view in product.views.all() if view.mockup_image]


def _attach_card_preview(target, draft, product):
    """Attach the visual used by the home cards, the hero and the project list."""

    preview_url = _stored_preview_url(draft)
    views = _card_views(product)
    view = views[0] if views else None
    layers = []

    if not preview_url and draft is not None:
        layer_view, image = _first_customized_image(draft)
        if layer_view is not None:
            view = layer_view
            layers = _build_card_layers(layer_view, image)

    mockup_url = view.mockup_image.url if view and view.mockup_image else ""

    target.card_preview_url = preview_url
    target.card_mockup_url = mockup_url
    target.card_canvas_width = view.canvas_width_px if view else 0
    target.card_canvas_height = view.canvas_height_px if view else 0
    target.card_layers = layers
    target.card_uses_preview = bool(preview_url)
    target.card_image_url = preview_url or mockup_url
    target.card_has_visual = bool(preview_url or layers or mockup_url)
    return target


def _prefetched_views_queryset():
    return ProductView.objects.order_by("sort_order", "id")


STAFF_RECENT_PROMOTIONS_LIMIT = 5


@login_required
def staff_dashboard(request):
    """Staff hub: the read-only counters and the shortcuts to change the shop.

    The page never writes: every button sends the staff member to the list that
    owns the data (the catalogue, the promotion manager or the Django admin), so
    there is exactly one place to create or edit each record.
    """

    if not request.user.is_staff:
        raise PermissionDenied

    promotions = (
        Promotion.objects.select_related("product")
        .prefetch_related("tiers")
        .order_by("-updated_at", "-created_at")[:STAFF_RECENT_PROMOTIONS_LIMIT]
    )

    return render(
        request,
        "home/staff_dashboard.html",
        {
            "product_count": Product.objects.count(),
            "active_product_count": Product.objects.filter(is_active=True).count(),
            "out_of_stock_count": Product.objects.filter(
                stock_quantity__lte=F("reserved_quantity")
            ).count(),
            "promotion_count": Promotion.objects.count(),
            "active_promotion_count": Promotion.objects.filter(is_active=True).count(),
            "recent_promotions": promotions,
            "order_count": Order.objects.count(),
        },
    )


def index(request):
    # Newest first: this section teases what just landed, while the complete
    # (paginated) catalogue lives behind the "Full catalogue" call to action.
    products = list(
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("views", queryset=_prefetched_views_queryset())
        )
        .order_by("-created_at", "-id")[:LATEST_PRODUCTS_LIMIT]
    )
    _attach_primary_views(products)

    # The catalogue teaser always previews the base product: a customer's own
    # drafts belong to the workspace, never to the shop cards.
    for product in products:
        _attach_card_preview(product, None, product)

    # Single query for the whole grid: each card teases the best price break.
    attach_promotion_badges(products)

    featured_product = next(
        (product for product in products if product.primary_view),
        products[0] if products else None,
    )

    latest_draft = None
    recent_drafts = []
    buy_again = []

    if request.user.is_authenticated:
        user_drafts = (
            CustomizationDraft.objects.filter(
                user=request.user, product__is_active=True
            )
            .select_related("product")
            .prefetch_related(
                Prefetch("product__views", queryset=_prefetched_views_queryset())
            )
            .order_by("-updated_at", "-created_at")
        )

        # The hero shows the project the customer touched most recently; the
        # workspace lists the newest ones as compact miniatures.
        latest_draft = user_drafts.first()
        if latest_draft is not None:
            _attach_card_preview(latest_draft, latest_draft, latest_draft.product)
            recent_drafts = list(user_drafts[:WORKSPACE_PROJECT_LIMIT])
            for draft in recent_drafts:
                _attach_card_preview(draft, draft, draft.product)

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
    else:
        for product in products:
            _attach_card_preview(product, None, product)

    return render(
        request,
        "home/index.html",
        {
            "products": products,
            "featured_product": featured_product,
            "latest_draft": latest_draft,
            "recent_drafts": recent_drafts,
            "buy_again": buy_again,
            "max_upload_mb": settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        },
    )
