from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .forms import MockupImageFormMixin
from .models import Product, ProductView


class ProductViewAdminForm(MockupImageFormMixin, forms.ModelForm):
    class Meta:
        model = ProductView
        fields = "__all__"


class MockupPreviewMixin:
    @admin.display(description="Preview")
    def mockup_preview(self, obj):
        if not obj or not obj.mockup_image:
            return "-"
        return format_html(
            '<img src="{}" alt="Mockup preview" '
            'style="max-height:140px;max-width:240px;object-fit:contain;'
            'background:#f4f4f4;border-radius:6px;padding:4px;">',
            obj.mockup_image.url,
        )


class ProductViewInline(MockupPreviewMixin, admin.TabularInline):
    model = ProductView
    form = ProductViewAdminForm
    extra = 0
    fields = (
        "name",
        "sort_order",
        "mockup_image",
        "mockup_preview",
        "print_width",
        "print_height",
    )
    readonly_fields = ("mockup_preview", "canvas_width_px", "canvas_height_px")
    show_change_link = True


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "base_price",
        "stock_quantity",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (ProductViewInline,)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductView)
class ProductViewAdmin(MockupPreviewMixin, admin.ModelAdmin):
    form = ProductViewAdminForm
    list_display = (
        "product",
        "name",
        "sort_order",
        "side_kind",
        "canvas_width_px",
        "canvas_height_px",
    )
    list_filter = ("product", "allow_rotation", "allow_scaling")
    search_fields = ("product__title", "name")
    readonly_fields = ("mockup_preview", "canvas_width_px", "canvas_height_px")
    fieldsets = (
        ("Side", {"fields": ("product", "name", "sort_order")}),
        (
            "Mockup",
            {
                "fields": (
                    "mockup_image",
                    "mockup_preview",
                    "canvas_width_px",
                    "canvas_height_px",
                )
            },
        ),
        (
            "Printable area",
            {
                "fields": ("print_x", "print_y", "print_width", "print_height"),
                "description": (
                    "Leave the width and height empty to make this a fixed side: "
                    "customers will only see the mockup and it is printed unchanged."
                ),
            },
        ),
        (
            "Customer controls",
            {
                "fields": (
                    "rotation",
                    "allow_rotation",
                    "allow_scaling",
                    "aspect_ratio_locked",
                    "max_file_size_mb",
                )
            },
        ),
    )

    @admin.display(description="Kind")
    def side_kind(self, obj):
        return "Customizable" if obj.is_customizable else "Fixed"
