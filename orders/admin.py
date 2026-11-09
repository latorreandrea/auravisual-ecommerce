from django.contrib import admin
from django.utils.html import format_html, format_html_join

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "payment_status",
        "stock_state",
        "total_display",
        "created_at",
    )
    list_filter = ("status", "payment_status", "stock_state", "created_at")
    search_fields = ("user__username", "user__email", "stripe_payment_intent_id")
    list_select_related = ("user", "shipping_address")
    date_hierarchy = "created_at"
    readonly_fields = (
        "user",
        "cart",
        "shipping_address",
        "items_summary",
        "total_amount",
        "currency",
        "reserved_until",
        "stripe_payment_intent_id",
        "created_at",
    )
    fieldsets = (
        ("Order", {"fields": ("user", "cart", "shipping_address", "created_at")}),
        ("Items", {"fields": ("items_summary",)}),
        ("Fulfilment", {"fields": ("status",)}),
        (
            "Payment and stock",
            {
                "fields": (
                    "payment_status",
                    "stock_state",
                    "reserved_until",
                    "total_amount",
                    "currency",
                    "stripe_payment_intent_id",
                ),
                "description": (
                    "Stock moves from reserved to committed when the payment "
                    "arrives, and back to the shelf when the order is released. "
                    "These fields are written by the checkout, not by hand."
                ),
            },
        ),
    )

    @admin.display(description="Total", ordering="total_amount")
    def total_display(self, obj):
        return format_html("{} {}", obj.total_amount, obj.currency)

    @admin.display(description="Items")
    def items_summary(self, obj):
        """Read-only list of what the order contains (the cart is immutable)."""

        if obj is None or not obj.cart_id:
            return "-"
        lines = [
            (item.product.title, item.quantity)
            for item in obj.cart.items.select_related("product")
        ]
        if not lines:
            return "-"
        return format_html_join("", "{} &times; {}<br>", lines)
