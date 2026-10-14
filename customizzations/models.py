from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ProductCustomization(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="customizations")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="customizations")
    front_image = models.ImageField(upload_to="customizations/front/")
    back_image = models.ImageField(upload_to="customizations/back/")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.product}"
