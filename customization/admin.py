from django.contrib import admin, messages
from django.utils.html import format_html

from .models import CustomizationDraft
from .services.printing import generate_print_file


@admin.register(CustomizationDraft)
class CustomizationDraftAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "user",
        "product",
        "side_count",
        "preview_thumb",
        "print_ready",
        "updated_at",
    )
    list_filter = ("product", "created_at")
    search_fields = ("id", "name", "user__username", "user__email", "product__title")
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
        (
            "Project",
            {
                "fields": (
                    "id",
                    "name",
                    "user",
                    "product",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        ("Configuration", {"fields": ("configuration_json",)}),
        ("Generated files", {"fields": ("preview_thumb", "print_file_url")}),
    )
    actions = ("regenerate_print_file",)

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

    @admin.display(description="Sides")
    def side_count(self, obj):
        return len((obj.configuration_json or {}).get("views", []))

    @admin.action(description="Generate print file (ZIP with one PNG per side)")
    def regenerate_print_file(self, request, queryset):
        generated = 0
        failed = 0
        for draft in queryset.select_related("product"):
            try:
                generate_print_file(draft, force=True)
                generated += 1
            except Exception:
                failed += 1
        if generated:
            self.message_user(
                request,
                f"{generated} print file(s) generated.",
                level=messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                f"{failed} print file(s) could not be generated.",
                level=messages.ERROR,
            )
