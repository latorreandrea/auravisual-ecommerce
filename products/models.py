from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


@dataclass(frozen=True)
class PrintArea:
    """Value object describing the printable area of a product side.

    It exposes the same interface a customization area always had, so the
    configuration validator, the renderer and the print pipeline can keep
    working with plain area geometry.
    """

    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    allow_rotation: bool = True
    allow_scaling: bool = True
    aspect_ratio_locked: bool = False
    max_file_size_mb: int = 10

    @property
    def effective_max_file_size_mb(self):
        return min(self.max_file_size_mb, settings.CUSTOMIZATION_MAX_UPLOAD_MB)


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

    @property
    def customizable_views(self):
        """Sides the customer can actually customize (a print area exists)."""

        return [view for view in self.views.all() if view.is_customizable]

    @property
    def has_customizable_sides(self):
        return any(view.is_customizable for view in self.views.all())


class ProductView(models.Model):
    """A product side (front, back, ...) with the mockup used by the editor.

    A side is customizable when it has a printable area (``print_width`` and
    ``print_height`` are set); otherwise it is a fixed side that is printed
    exactly as its mockup and is never offered to the customer.
    """

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
    canvas_width_px = models.PositiveIntegerField(editable=False, default=0)
    canvas_height_px = models.PositiveIntegerField(editable=False, default=0)

    print_x = models.FloatField(
        default=0, help_text="X coordinate of the top-left corner, in mockup pixels."
    )
    print_y = models.FloatField(
        default=0, help_text="Y coordinate of the top-left corner, in mockup pixels."
    )
    print_width = models.FloatField(
        null=True,
        blank=True,
        help_text=(
            "Width of the printable area, in mockup pixels. Leave it empty to make "
            "this a fixed side that customers cannot customize."
        ),
    )
    print_height = models.FloatField(
        null=True,
        blank=True,
        help_text="Height of the printable area, in mockup pixels.",
    )
    rotation = models.FloatField(
        default=0, help_text="Default rotation of the area, in degrees (-180 to 180)."
    )
    allow_rotation = models.BooleanField(
        default=True, help_text="Customers can rotate the artwork inside the area."
    )
    allow_scaling = models.BooleanField(
        default=True, help_text="Customers can zoom the artwork inside the area."
    )
    aspect_ratio_locked = models.BooleanField(
        default=False,
        help_text="Keep the customer image at its original aspect ratio.",
    )
    max_file_size_mb = models.PositiveIntegerField(
        default=10,
        help_text=(
            "Maximum size of the customer image in MB. It can only be lowered: "
            "the global CUSTOMIZATION_MAX_UPLOAD_MB setting is a hard cap."
        ),
    )

    class Meta:
        ordering = ("sort_order", "id")

    def __str__(self):
        return f"{self.product} - {self.name}"

    @property
    def is_customizable(self):
        """A side is customizable only when the admin drew a printable area."""

        return bool(self.print_width and self.print_height)

    @property
    def print_area(self):
        """Return the printable area as a ``PrintArea`` (``None`` when fixed)."""

        if not self.is_customizable:
            return None
        return PrintArea(
            x=float(self.print_x),
            y=float(self.print_y),
            width=float(self.print_width),
            height=float(self.print_height),
            rotation=float(self.rotation),
            allow_rotation=self.allow_rotation,
            allow_scaling=self.allow_scaling,
            aspect_ratio_locked=self.aspect_ratio_locked,
            max_file_size_mb=self.max_file_size_mb,
        )

    @property
    def effective_max_file_size_mb(self):
        return min(self.max_file_size_mb, settings.CUSTOMIZATION_MAX_UPLOAD_MB)

    def make_fixed(self):
        """Turn the side into a fixed (not customizable) side."""

        self.print_width = None
        self.print_height = None
        self.print_x = 0
        self.print_y = 0

    def clean(self):
        errors = {}
        if not self.is_customizable:
            return

        if self.print_width <= 0:
            errors["print_width"] = "The print area width must be greater than zero."
        if self.print_height <= 0:
            errors["print_height"] = "The print area height must be greater than zero."
        if self.print_x < 0:
            errors["print_x"] = "The print area X cannot be negative."
        if self.print_y < 0:
            errors["print_y"] = "The print area Y cannot be negative."
        if not -180 <= self.rotation <= 180:
            errors["rotation"] = "Rotation must be between -180 and 180 degrees."
        if self.max_file_size_mb > settings.CUSTOMIZATION_MAX_UPLOAD_MB:
            errors["max_file_size_mb"] = (
                f"The limit cannot exceed the global cap of "
                f"{settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB."
            )

        if self.canvas_width_px and self.canvas_height_px:
            if self.print_x + self.print_width > self.canvas_width_px:
                errors["print_width"] = "The area exceeds the mockup width."
            if self.print_y + self.print_height > self.canvas_height_px:
                errors["print_height"] = "The area exceeds the mockup height."

        if errors:
            raise ValidationError(errors)
