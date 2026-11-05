"""Price computation for quantity based promotions.

Every page that shows a price (catalogue, home, cart) goes through
``price_line`` or ``attach_promotion_badges`` so a promotion can never be
applied twice, or applied differently in two places.

Rule: a break covers ``tier.quantity`` units at ``tier.price``, the units above
the break stay at the product base price. With a base price of EUR 10 and the
breaks 5 for EUR 40 / 10 for EUR 70, seven units cost 40 + 2 * 10 = EUR 60.
The winning break is the one with the lowest net total, and the base price is
used when no break is cheaper.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .models import CENTS, Promotion, PromotionTier


@dataclass(frozen=True)
class LinePricing:
    """Price of a single line after the best applicable quantity break."""

    unit_price: Decimal
    quantity: int
    gross_total: Decimal
    net_total: Decimal
    discount_total: Decimal
    promotion: Promotion | None = None
    tier: PromotionTier | None = None
    promotion_label: str = ""

    @property
    def has_discount(self):
        return self.discount_total > 0

    @property
    def extra_units(self):
        """Units charged at the base price on top of the applied break."""

        if self.tier is None:
            return 0
        return max(self.quantity - self.tier.quantity, 0)


def tier_label(tier):
    """Short label for a break, e.g. ``5 for €40.00``."""

    return f"{tier.quantity} for €{tier.price}"


def promotion_label(promotion, tier):
    """Label shown in the cart, e.g. ``T-shirt bundle · 5 for €40.00``."""

    return f"{promotion.name} · {tier_label(tier)}"


def active_promotions_for(product_ids):
    """Return ``{product_id: [Promotion, ...]}`` with ``tiers`` prefetched."""

    ids = [int(pk) for pk in product_ids if pk]
    grouped = {}
    if not ids:
        return grouped
    promotions = (
        Promotion.objects.filter(product_id__in=ids, is_active=True)
        .prefetch_related("tiers")
        .order_by("pk")
    )
    for promotion in promotions:
        grouped.setdefault(promotion.product_id, []).append(promotion)
    return grouped


def promotions_for_product(product, promotions=None):
    """Active promotions of one product, reusing a prefetched list when given."""

    if promotions is None:
        return list(active_promotions_for([product.pk]).get(product.pk, ()))
    return [promotion for promotion in promotions if promotion.is_active]


def best_break(product, quantity, promotions=None):
    """Cheapest ``(promotion, tier, net_total)`` for a line, or ``None``."""

    quantity = int(quantity or 0)
    if quantity < 1:
        return None
    unit_price = product.base_price
    best = None
    for promotion in promotions_for_product(product, promotions):
        for tier in promotion.tiers.all():
            if tier.quantity > quantity:
                continue
            net_total = (tier.price + unit_price * (quantity - tier.quantity)).quantize(
                CENTS, rounding=ROUND_HALF_UP
            )
            if best is None or (net_total, -tier.quantity) < (
                best[2],
                -best[1].quantity,
            ):
                best = (promotion, tier, net_total)
    return best


def price_line(product, quantity, promotions=None):
    """Price a single line of ``quantity`` units of ``product``.

    ``promotions`` may be a prefetched list of the product promotions; when it
    is ``None`` the active promotions are fetched for that product only.
    """

    quantity = max(int(quantity or 0), 0)
    unit_price = product.base_price
    gross_total = (unit_price * quantity).quantize(CENTS, rounding=ROUND_HALF_UP)
    best = best_break(product, quantity, promotions)
    if best is None or best[2] >= gross_total:
        return LinePricing(
            unit_price=unit_price,
            quantity=quantity,
            gross_total=gross_total,
            net_total=gross_total,
            discount_total=Decimal("0.00"),
        )
    promotion, tier, net_total = best
    return LinePricing(
        unit_price=unit_price,
        quantity=quantity,
        gross_total=gross_total,
        net_total=net_total,
        discount_total=gross_total - net_total,
        promotion=promotion,
        tier=tier,
        promotion_label=promotion_label(promotion, tier),
    )


def attach_promotion_badges(products):
    """Attach ``promotion_name`` / ``promotion_teaser`` to each product.

    The teaser is the most convenient quantity break, so catalogue cards can
    show ``from 10 for €70.00`` with a single query for the whole page.
    """

    products = list(products)
    grouped = active_promotions_for(product.pk for product in products)
    for product in products:
        best_promotion = None
        best_tier = None
        for promotion in grouped.get(product.pk, ()):
            for tier in promotion.tiers.all():
                if best_tier is None or (tier.unit_price, -tier.quantity) < (
                    best_tier.unit_price,
                    -best_tier.quantity,
                ):
                    best_promotion = promotion
                    best_tier = tier
        product.promotion_name = best_promotion.name if best_promotion else ""
        product.promotion_teaser = tier_label(best_tier) if best_tier else ""
    return products
