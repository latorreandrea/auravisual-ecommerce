from django.contrib import admin

from .forms import PromotionTierForm, PromotionTierFormSet
from .models import Promotion, PromotionTier


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
