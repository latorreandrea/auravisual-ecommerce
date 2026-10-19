from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from .models import CustomizationZone, Product, ProductView
from .services.images import optimize_mockup


class BootstrapFormMixin:
    """Apply the Bootstrap classes used across the store to model forms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class MockupImageFormMixin:
    """Optimise a newly uploaded mockup and store its real canvas size."""

    def clean_mockup_image(self):
        image = self.cleaned_data.get("mockup_image")
        if not image or not isinstance(image, UploadedFile):
            # No new file was chosen: keep the optimized mockup already stored.
            return image

        optimized, width, height = optimize_mockup(image)
        self.instance.canvas_width_px = width
        self.instance.canvas_height_px = height
        return optimized


class ProductCreateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = ("title", "description", "base_price", "stock_quantity", "is_active")
        labels = {
            "base_price": "Base price (EUR)",
            "stock_quantity": "Stock quantity",
            "is_active": "Visible in the catalogue",
        }
        help_texts = {
            "description": "A short description shown on the product card.",
            "is_active": "Inactive products are hidden from the home page and the catalogue.",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 4, "placeholder": "What is this product, and what is it for?"}
            ),
            "base_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "stock_quantity": forms.NumberInput(attrs={"min": "0", "step": "1"}),
        }


class ProductViewForm(MockupImageFormMixin, BootstrapFormMixin, forms.ModelForm):
    """The first view of a product, created together with the product itself."""

    class Meta:
        model = ProductView
        fields = ("name", "sort_order", "mockup_image", "overlay_texture")
        labels = {
            "name": "View name",
            "sort_order": "Display order",
            "mockup_image": "Mockup image",
            "overlay_texture": "Overlay texture (optional)",
        }
        help_texts = {
            "name": 'Use a clear side name such as "Front", "Back" or "Left side".',
            "sort_order": "Lower numbers appear first in the editor.",
            "mockup_image": (
                "PNG, JPG/JPEG or WebP. The image is resized, converted to WebP "
                "and stripped of metadata automatically."
            ),
            "overlay_texture": (
                "Optional PNG/WebP layer for reflections or shadows. It is applied "
                "above the customer artwork."
            ),
        }
        widgets = {
            "sort_order": forms.NumberInput(attrs={"min": "1", "step": "1"}),
        }


class CustomizationZoneForm(BootstrapFormMixin, forms.ModelForm):
    """One printable area, expressed in mockup pixels."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["max_file_size_mb"].initial = settings.CUSTOMIZATION_MAX_UPLOAD_MB
        self.fields["max_file_size_mb"].help_text = (
            f"Cannot exceed the store-wide limit of {settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB."
        )

    class Meta:
        model = CustomizationZone
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
        labels = {
            "name": "Area name",
            "x": "X position (px)",
            "y": "Y position (px)",
            "width": "Width (px)",
            "height": "Height (px)",
            "rotation": "Default rotation (degrees)",
            "allow_rotation": "Customers can rotate the artwork",
            "allow_scaling": "Customers can zoom the artwork",
            "max_file_size_mb": "Maximum image size (MB)",
            "aspect_ratio_locked": "Lock the original aspect ratio",
        }
        help_texts = {
            "x": "Distance from the left edge of the mockup.",
            "y": "Distance from the top edge of the mockup.",
            "width": "The area must fit inside the mockup width.",
            "height": "The area must fit inside the mockup height.",
            "max_file_size_mb": "Cannot exceed the store-wide upload limit shown on this page.",
        }
        widgets = {
            "x": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "y": forms.NumberInput(attrs={"min": "0", "step": "1"}),
            "width": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "height": forms.NumberInput(attrs={"min": "1", "step": "1"}),
            "rotation": forms.NumberInput(attrs={"min": "-180", "max": "180", "step": "1"}),
            "max_file_size_mb": forms.NumberInput(attrs={"min": "1", "step": "1"}),
        }
