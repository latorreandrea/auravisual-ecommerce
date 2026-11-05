from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import models

CENTS = Decimal("0.01")


class Promotion(models.Model):
    """A named, quantity based price bundle for a single product.

    The admin picks the product, gives the promotion a name and adds one
    ``PromotionTier`` per price break (5 units for EUR 40, 10 for EUR 70, ...).
    Every price shown on the storefront is computed by ``promotions.services``
    so the catalogue, the cart and the product pages always agree.
    """

    name = models.CharField(
        max_length=120,
        help_text='Shown in the cart next to the discount, e.g. "T-shirt bundle".',
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="promotions",
        help_text="A promotion only applies to this product.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive promotions are ignored by the storefront.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("product__title", "name")

    def __str__(self):
        return f"{self.name} ({self.product})"

    @property
    def tiers_summary(self):
        """Human readable ladder, e.g. ``5 for EUR 40.00, 10 for EUR 70.00``."""

        return ", ".join(
            f"{tier.quantity} for EUR {tier.price}" for tier in self.tiers.all()
        )

    @staticmethod
    def validate_tiers(pairs, base_price):
        """Validate ``(quantity, price)`` breaks and return them sorted.

        A break must be a real saving, totals must grow with the quantity and
        the unit price must drop when the bundle grows: that keeps the ladder
        predictable and makes the biggest affordable break the best one.
        """

        tiers = sorted(
            (int(quantity), Decimal(str(price)))
            for quantity, price in pairs
            if quantity and price is not None
        )
        if not tiers:
            raise ValidationError("Add at least one quantity/price break.")

        base_price = Decimal(str(base_price)) if base_price is not None else None
        seen = set()
        previous = None
        for quantity, price in tiers:
            if quantity in seen:
                raise ValidationError(
                    f"The {quantity}-unit break is defined more than once."
                )
            seen.add(quantity)
            if quantity < 1:
                raise ValidationError("A break needs at least one unit.")
            if price <= 0:
                raise ValidationError(
                    f"The price for {quantity} units must be greater than zero."
                )
            if base_price is not None and price >= base_price * quantity:
                raise ValidationError(
                    f"{quantity} units for EUR {price} is not a saving: at the "
                    f"base price they cost EUR {base_price * quantity}."
                )
            if previous is not None:
                previous_quantity, previous_price = previous
                if price <= previous_price:
                    raise ValidationError(
                        f"The total for {quantity} units (EUR {price}) must be "
                        f"higher than the total for {previous_quantity} units "
                        f"(EUR {previous_price})."
                    )
                if price * previous_quantity >= previous_price * quantity:
                    raise ValidationError(
                        f"The {quantity}-unit break must have a lower unit price "
                        f"than the {previous_quantity}-unit break."
                    )
            previous = (quantity, price)
        return tiers


class PromotionTier(models.Model):
    """One price break: ``quantity`` units cost ``price`` in total."""

    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        related_name="tiers",
    )
    quantity = models.PositiveIntegerField(
        help_text="Units that unlock this price, e.g. 5.",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Total price in EUR for that many units, e.g. 40.00 for 5 units.",
    )

    class Meta:
        ordering = ("quantity",)
        constraints = (
            models.UniqueConstraint(
                fields=("promotion", "quantity"),
                name="unique_promotion_tier_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="promotion_tier_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="promotion_tier_price_gt_0",
            ),
        )

    def __str__(self):
        return f"{self.quantity} for EUR {self.price}"

    @property
    def unit_price(self):
        """Price of a single unit inside this break."""

        if not self.quantity:
            return Decimal("0.00")
        return (self.price / Decimal(self.quantity)).quantize(
            CENTS, rounding=ROUND_HALF_UP
        )

    def clean(self):
        """Check this break against the other breaks of the same promotion."""

        super().clean()
        if not self.promotion_id:
            return
        promotion = self.promotion
        pairs = [
            (tier.quantity, tier.price)
            for tier in promotion.tiers.exclude(pk=self.pk)
        ]
        if self.quantity and self.price is not None:
            pairs.append((self.quantity, self.price))
        promotion.validate_tiers(pairs, promotion.product.base_price)
