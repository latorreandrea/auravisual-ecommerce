from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Product(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._build_unique_slug()
        super().save(*args, **kwargs)

    def _build_unique_slug(self):
        base = slugify(self.title)[:120] or "product"
        slug = base
        suffix = 2
        while Product.objects.exclude(pk=self.pk).filter(slug=slug).exists():
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug

    def get_absolute_url(self):
        return reverse("customization:editor", kwargs={"slug": self.slug})


class ProductView(models.Model):
    """A product side (front, back, ...) with the mockup used by the editor."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="views")
    name = models.CharField(max_length=80, help_text='e.g. "Front", "Back", "Left side".')
    sort_order = models.PositiveIntegerField(default=1)
    mockup_image = models.ImageField(
        upload_to="products/mockups/",
        help_text=(
            "Upload a transparent PNG (or another PNG/JPEG/WebP image). "
            "The file is optimised automatically: resized, converted to WebP and "
            "stripped of metadata."
        ),
    )
    overlay_texture = models.ImageField(
        upload_to="products/overlays/",
        blank=True,
        help_text="Optional reflections, shadows or finishing effects applied above the user image.",
    )
    canvas_width_px = models.PositiveIntegerField(editable=False, default=0)
    canvas_height_px = models.PositiveIntegerField(editable=False, default=0)

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return f"{self.product} - {self.name}"

    @property
    def has_zones(self):
        return self.zones.exists()


class CustomizationZone(models.Model):
    """Printable area inside a specific product view."""

    product_view = models.ForeignKey(ProductView, on_delete=models.CASCADE, related_name="zones")
    name = models.CharField(max_length=80, help_text='e.g. "Main logo area", "Back photo".')
    x = models.FloatField(default=0, help_text="X coordinate of the top-left corner, in mockup pixels.")
    y = models.FloatField(default=0, help_text="Y coordinate of the top-left corner, in mockup pixels.")
    width = models.FloatField(help_text="Allowed area width, in mockup pixels.")
    height = models.FloatField(help_text="Allowed area height, in mockup pixels.")
    rotation = models.FloatField(default=0, help_text="Default rotation of the area, in degrees (-180 to 180).")
    allow_rotation = models.BooleanField(default=True)
    allow_scaling = models.BooleanField(default=True)
    max_file_size_mb = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Maximum size of each customer image in MB. It can only be lowered: "
            "the global CUSTOMIZATION_MAX_UPLOAD_MB setting is a hard cap."
        ),
    )
    aspect_ratio_locked = models.BooleanField(
        default=False,
        help_text="Keep the customer image at its original aspect ratio.",
    )

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.product_view} - {self.name}"

    @property
    def effective_max_file_size_mb(self):
        return min(self.max_file_size_mb, settings.CUSTOMIZATION_MAX_UPLOAD_MB)

    def clean(self):
        errors = {}
        view = self.product_view

        if self.width is not None and self.width <= 0:
            errors["width"] = "Width must be greater than zero."
        if self.height is not None and self.height <= 0:
            errors["height"] = "Height must be greater than zero."
        if self.x is not None and self.x < 0:
            errors["x"] = "X cannot be negative."
        if self.y is not None and self.y < 0:
            errors["y"] = "Y cannot be negative."
        if self.rotation is not None and not -180 <= self.rotation <= 180:
            errors["rotation"] = "Rotation must be between -180 and 180 degrees."
        if self.max_file_size_mb and self.max_file_size_mb > settings.CUSTOMIZATION_MAX_UPLOAD_MB:
            errors["max_file_size_mb"] = (
                f"The limit cannot exceed the global cap of {settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB."
            )

        if view and view.canvas_width_px and view.canvas_height_px:
            if self.x is not None and self.width is not None and self.x + self.width > view.canvas_width_px:
                errors["width"] = "The area exceeds the mockup width."
            if self.y is not None and self.height is not None and self.y + self.height > view.canvas_height_px:
                errors["height"] = "The area exceeds the mockup height."

        if errors:
            raise ValidationError(errors)
