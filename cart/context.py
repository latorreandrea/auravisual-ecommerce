from decimal import Decimal

from django.urls import reverse

from customization.models import CustomizationDraft
from products.models import Product

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
    total = Decimal("0.00")

    product_ids = {line["product_id"] for line in lines.values()}
    products = Product.objects.filter(pk__in=product_ids, is_active=True)
    products_map = {product.pk: product for product in products}

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

        line_total = product.base_price * line["quantity"]
        total += line_total
        items.append(
            {
                "line_key": key,
                "product_id": product.pk,
                "name": product.title,
                "slug": product.slug,
                "price": product.base_price,
                "quantity": line["quantity"],
                "line_total": line_total,
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
        "total": total,
        "count": sum(item["quantity"] for item in items),
    }


def cart_context(request):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    return {"cart_summary": _build_cart_summary(session_cart, request.user)}
