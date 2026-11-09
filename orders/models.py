from decimal import Decimal

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Order(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Order received"
        PREPARING = "preparing", "Being prepared"
        SHIPPED = "shipped", "Shipped"

    class PaymentStatus(models.TextChoices):
        """Payment lifecycle, kept apart from the fulfilment ``status``.

        No gateway is wired in yet, so every order the storefront places is
        ``PAID`` immediately. Stripe will own this field: the payment intent
        starts as ``UNPAID`` and the webhook moves it to ``PAID`` or ``FAILED``.
        """

        UNPAID = "unpaid", "Awaiting payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        REFUNDED = "refunded", "Refunded"

    class StockState(models.TextChoices):
        """Where the ordered units are in the reserve/commit/release cycle."""

        NONE = "none", "No stock taken"
        RESERVED = "reserved", "Stock reserved"
        COMMITTED = "committed", "Stock committed"
        RELEASED = "released", "Reservation released"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    cart = models.ForeignKey("cart.Cart", on_delete=models.PROTECT, related_name="orders")
    shipping_address = models.ForeignKey(
        "accounts.ShippingAddress",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
    )
    stock_state = models.CharField(
        max_length=20,
        choices=StockState.choices,
        default=StockState.NONE,
    )
    # When a hold stops being valid. Empty for orders that already committed
    # their stock (or never took any): see orders.services.
    reserved_until = models.DateTimeField(null=True, blank=True)
    # Snapshot of the total computed at checkout. Stripe needs an amount that
    # was calculated server-side, and the order history must not drift when a
    # price or a promotion changes later.
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(max_length=3, default="EUR")
    # Filled in when Stripe is wired in; empty for the orders placed today.
    stripe_payment_intent_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Order #{self.pk}"

    @property
    def item_count(self):
        """Units in the order, counting every cart line."""

        return sum(item.quantity for item in self.cart.items.all())
