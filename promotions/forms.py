"""Promotion forms shared by the Django admin and the staff pages.

The ladder validation lives here, so both surfaces enforce exactly the same
rules: every break is compared with the product base price and with its
siblings through ``Promotion.validate_tiers``.
"""

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from products.forms import BootstrapFormMixin
from products.models import Product

from .models import Promotion, PromotionTier


class PromotionTierForm(forms.ModelForm):
    class Meta:
        model = PromotionTier
        fields = ("quantity", "price")
        labels = {"quantity": "Units", "price": "Total price (EUR)"}


class PromotionTierFormSet(BaseInlineFormSet):
    """Validate the whole ladder, because a break depends on its siblings.

    ``min_num`` alone is not enforced by the admin, and the checks that compare
    breaks with each other cannot live on a single form, so both live here.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        pairs = []
        for form in self.forms:
            data = form.cleaned_data
            if not data or data.get("DELETE"):
                continue
            pairs.append((data.get("quantity"), data.get("price")))
        promotion = self.instance
        product = getattr(promotion, "product", None)
        if product is None:
            # The main form already reports the missing product.
            return
        promotion.validate_tiers(pairs, product.base_price)


class PromotionForm(BootstrapFormMixin, forms.ModelForm):
    """Name, product and activation flag of a promotion."""

    class Meta:
        model = Promotion
        fields = ("name", "product", "is_active")
        labels = {"product": "Product", "is_active": "Active in the storefront"}
        help_texts = {
            "name": 'Shown in the cart next to the discount, e.g. "T-shirt bundle".',
            "product": "A promotion only applies to a single product.",
            "is_active": "Inactive promotions are ignored by the catalogue and the cart.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Staff pages list the catalogue alphabetically and show the base price,
        # because a break has to beat it to be accepted. Products that already
        # have a promotion are flagged: the storefront only uses one ladder per
        # product, so a second one would be silently ignored.
        existing = Promotion.objects.all()
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        promoted_ids = set(existing.values_list("product_id", flat=True))
        self.fields["product"].queryset = Product.objects.order_by("title")
        self.fields["product"].label_from_instance = lambda product: (
            f"{product.title} (EUR {product.base_price})"
            + (" - already promoted" if product.pk in promoted_ids else "")
        )


class StaffPromotionTierForm(BootstrapFormMixin, PromotionTierForm):
    """The admin break form plus the Bootstrap classes used by the store."""


PromotionTierStoreFormSet = inlineformset_factory(
    Promotion,
    PromotionTier,
    form=StaffPromotionTierForm,
    formset=PromotionTierFormSet,
    extra=1,
    can_delete=True,
)
