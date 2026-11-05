from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet

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


class PromotionTierInline(admin.TabularInline):
    model = PromotionTier
    form = PromotionTierForm
    formset = PromotionTierFormSet
    fields = ("quantity", "price")
    extra = 1
    min_num = 1


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "ladder", "is_active", "updated_at")
    list_filter = ("is_active", "product")
    list_editable = ("is_active",)
    list_select_related = ("product",)
    search_fields = ("name", "product__title")
    autocomplete_fields = ("product",)
    readonly_fields = ("created_at", "updated_at", "ladder")
    inlines = (PromotionTierInline,)
    fieldsets = (
        (
            "Promotion",
            {
                "fields": ("name", "product", "is_active"),
                "description": "A promotion applies to a single product.",
            },
        ),
        (
            "Price breaks",
            {
                "fields": ("ladder",),
                "description": (
                    "Add one price break per quantity, e.g. 5 units for EUR 40 "
                    "and 10 units for EUR 70. Units above a break stay at the "
                    "product base price."
                ),
            },
        ),
        ("History", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Price breaks")
    def ladder(self, obj):
        if obj is None or not obj.pk:
            return "-"
        return obj.tiers_summary or "-"
