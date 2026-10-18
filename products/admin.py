from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.utils.html import format_html

from .models import CustomizationZone, Product, ProductView
from .services.images import optimize_mockup


class ProductViewAdminForm(forms.ModelForm):
    class Meta:
        model = ProductView
        fields = "__all__"

    def clean_mockup_image(self):
        image = self.cleaned_data.get("mockup_image")
        if not image or not isinstance(image, UploadedFile):
            # No new file was chosen: keep the optimized mockup already stored.
            return image

        optimized, width, height = optimize_mockup(image)
        self.instance.canvas_width_px = width
        self.instance.canvas_height_px = height
        return optimized


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


class CustomizationZoneInline(admin.TabularInline):
    model = CustomizationZone
    extra = 0
    fields = (
        "name",
        "x",
        "y",
        "width",
        "height",
        "rotation",
        "allow_rotation",
        "allow_scaling",
        "max_file_size_mb",
        "aspect_ratio_locked",
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
        "canvas_width_px",
        "canvas_height_px",
        "overlay_texture",
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
    search_fields = ("title", "slug", "description")
    prepopulated_fields = {"slug": ("title",)}
    inlines = (ProductViewInline,)
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProductView)
class ProductViewAdmin(MockupPreviewMixin, admin.ModelAdmin):
    form = ProductViewAdminForm
    list_display = ("product", "name", "sort_order", "canvas_width_px", "canvas_height_px", "zone_count")
    list_filter = ("product",)
    search_fields = ("product__title", "name")
    inlines = (CustomizationZoneInline,)
    readonly_fields = ("mockup_preview", "canvas_width_px", "canvas_height_px")
    fieldsets = (
        ("View", {"fields": ("product", "name", "sort_order")}),
        (
            "Mockup",
            {
                "fields": (
                    "mockup_image",
                    "mockup_preview",
                    "canvas_width_px",
                    "canvas_height_px",
                    "overlay_texture",
                )
            },
        ),
    )

    @admin.display(description="Zones")
    def zone_count(self, obj):
        return obj.zones.count()


@admin.register(CustomizationZone)
class CustomizationZoneAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product_view",
        "x",
        "y",
        "width",
        "height",
        "allow_rotation",
        "allow_scaling",
        "max_file_size_mb",
    )
    list_filter = ("product_view__product", "product_view", "allow_rotation", "allow_scaling")
    search_fields = ("name", "product_view__name", "product_view__product__title")
