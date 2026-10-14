from decimal import Decimal

from products.models import Product

CART_SESSION_KEY = "cart"


def _build_cart_summary(session_cart):
    items = []
    total = Decimal("0.00")
    products = Product.objects.filter(pk__in=session_cart.keys(), is_active=True)
    products_map = {str(product.pk): product for product in products}

    for product_id, quantity in session_cart.items():
        product = products_map.get(product_id)
        if not product:
            continue
        line_total = product.price * quantity
        total += line_total
        items.append(
            {
                "product_id": product.pk,
                "name": product.name,
                "price": product.price,
                "quantity": quantity,
                "line_total": line_total,
            }
        )

    return {"items": items, "total": total, "count": sum(item["quantity"] for item in items)}


def cart_context(request):
    session_cart = request.session.get(CART_SESSION_KEY, {})
    return {"cart_summary": _build_cart_summary(session_cart)}
