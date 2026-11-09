from decimal import Decimal

from django.urls import reverse

from customization.models import CustomizationDraft
from products.models import Product
from promotions.services import active_promotions_for, price_line

CART_SESSION_KEY = "cart"


def line_key(product_id, draft_id=None):
    """Session key for a cart line: ``<product_id>`` or ``<product_id>:<draft_uuid>``."""

    if draft_id:
        return f"{int(product_id)}:{draft_id}"
    return str(int(product_id))


def normalize_session_cart(session_cart):
    """Return the current cart shape, upgrading the legacy ``{id: qty}`` format."""

    normalized = {}
    if not isinstance(session_cart, dict):
        return normalized

    for key, value in session_cart.items():
        if isinstance(value, dict):
            product_id = value.get("product_id")
            quantity = value.get("quantity")
            draft_id = value.get("draft_id") or None
            if product_id is None:
                product_id = str(key).split(":", 1)[0]
        else:
            product_id = str(key).split(":", 1)[0]
            quantity = value
            draft_id = None

        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if product_id <= 0 or quantity <= 0:
            continue

        draft_id = str(draft_id) if draft_id else None
        normalized[line_key(product_id, draft_id)] = {
            "product_id": product_id,
            "quantity": quantity,
            "draft_id": draft_id,
        }

    return normalized


def _build_cart_summary(session_cart, user=None):
    lines = normalize_session_cart(session_cart)
    items = []
    subtotal = Decimal("0.00")
    total = Decimal("0.00")

    product_ids = {line["product_id"] for line in lines.values()}
    products = Product.objects.filter(pk__in=product_ids, is_active=True)
    products_map = {product.pk: product for product in products}
    promotions_map = active_promotions_for(products_map)

    draft_ids = {line["draft_id"] for line in lines.values() if line["draft_id"]}
    drafts_map = {}
    if draft_ids and user is not None and user.is_authenticated:
        drafts = CustomizationDraft.objects.filter(pk__in=draft_ids, user=user)
        drafts_map = {str(draft.pk): draft for draft in drafts}

    for key, line in lines.items():
        product = products_map.get(line["product_id"])
        if not product:
            continue

        draft = drafts_map.get(line["draft_id"]) if line["draft_id"] else None
        draft_missing = bool(line["draft_id"]) and draft is None
        if draft and draft.product_id != product.pk:
            draft = None
            draft_missing = True

        pricing = price_line(
            product,
            line["quantity"],
            promotions_map.get(product.pk, ()),
        )
        subtotal += pricing.gross_total
        total += pricing.net_total
        items.append(
            {
                "line_key": key,
                "product_id": product.pk,
                "name": product.title,
                "slug": product.slug,
                "price": pricing.unit_price,
                "unit_price": pricing.unit_price,
                "quantity": line["quantity"],
                "gross_line_total": pricing.gross_total,
                "line_total": pricing.net_total,
                "discount_total": pricing.discount_total,
                "promotion_name": pricing.promotion.name if pricing.promotion else "",
                "promotion_label": pricing.promotion_label,
                "extra_units": pricing.extra_units,
                # Stock: the cart cannot promise more units than are actually
                # free (physical stock minus the holds of pending payments).
                "available_quantity": product.available_quantity,
                "is_out_of_stock": product.is_out_of_stock,
                "exceeds_stock": line["quantity"] > product.available_quantity,
                "draft": draft,
                "draft_id": str(draft.pk) if draft else None,
                "draft_missing": draft_missing,
                "preview_url": draft.preview_url if draft else "",
                "draft_detail_url": (
                    reverse("customization:draft_detail", kwargs={"draft_id": draft.pk})
                    if draft
                    else ""
                ),
                "customize_url": reverse("customization:editor", kwargs={"slug": product.slug}),
            }
        )

    return {
        "items": items,
        "subtotal": subtotal,
        "discount_total": subtotal - total,
        "total": total,
        "count": sum(item["quantity"] for item in items),
        # One flag for the cart page and the checkout button: a cart that asks
        # for more units than are free cannot be checked out.
        "has_stock_issue": any(item["exceeds_stock"] for item in items),
    }


def cart_context(request):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    return {"cart_summary": _build_cart_summary(session_cart, request.user)}
