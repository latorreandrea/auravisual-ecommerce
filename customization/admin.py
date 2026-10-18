from django.contrib import admin
from django.utils.html import format_html

from .models import CustomizationDraft


@admin.register(CustomizationDraft)
class CustomizationDraftAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "preview_thumb", "print_ready", "created_at")
    list_filter = ("product", "created_at")
    search_fields = ("id", "user__username", "user__email", "product__title")
    readonly_fields = (
        "id",
        "user",
        "product",
        "configuration_json",
        "preview_thumb",
        "print_file_url",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("Draft", {"fields": ("id", "user", "product", "created_at", "updated_at")}),
        ("Configuration", {"fields": ("configuration_json",)}),
        ("Generated files", {"fields": ("preview_thumb", "print_file_url")}),
    )

    @admin.display(description="Preview")
    def preview_thumb(self, obj):
        if not obj.preview_url:
            return "-"
        return format_html(
            '<img src="{}" alt="Customization preview" '
            'style="max-height:120px;max-width:180px;object-fit:contain;'
            'background:#f4f4f4;border-radius:6px;padding:4px;">',
            obj.preview_url,
        )

    @admin.display(boolean=True, description="Print ready")
    def print_ready(self, obj):
        return bool(obj.print_file_url)

