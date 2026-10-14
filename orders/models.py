from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Order(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Order received"
        PREPARING = "preparing", "Being prepared"
        SHIPPED = "shipped", "Shipped"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    cart = models.ForeignKey("cart.Cart", on_delete=models.PROTECT, related_name="orders")
    shipping_address = models.ForeignKey(
        "accounts.ShippingAddress",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Order #{self.pk}"
