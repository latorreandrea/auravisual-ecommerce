from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory

from .models import Product, ProductView
from .services.images import optimize_mockup

MAX_PRODUCT_VIEWS = 8
DEFAULT_AREA_RATIOS = {
    "x_ratio": 0.1,
    "y_ratio": 0.1,
    "width_ratio": 0.8,
    "height_ratio": 0.8,
}


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


class ProductEditForm(ProductCreateForm):
    """Edit the scalar product fields from the staff hub.

    The sides (mockups and print areas) are created by the wizard and keep being
    managed from the Django admin, so this form never touches them.
    """

    class Meta(ProductCreateForm.Meta):
        labels = {
            **ProductCreateForm.Meta.labels,
            "stock_quantity": "Stock quantity (physical units)",
        }
        help_texts = {
            **ProductCreateForm.Meta.help_texts,
            "base_price": (
                "Price of a single unit. Promotions are validated against it, so "
                "changing it can invalidate an existing ladder."
            ),
            "stock_quantity": (
                "Units on the shelf. Units held by orders waiting for payment are "
                "subtracted automatically."
            ),
        }


class ProductViewForm(MockupImageFormMixin, BootstrapFormMixin, forms.ModelForm):
    """One product side, created together with the product itself."""

    class Meta:
        model = ProductView
        fields = ("name", "mockup_image")
        labels = {
            "name": "Side name",
            "mockup_image": "Mockup image",
        }
        help_texts = {
            "name": 'Use a clear side name such as "Front", "Back" or "Left side".',
            "mockup_image": (
                "PNG, JPG/JPEG or WebP. The image is resized, converted to WebP "
                "and stripped of metadata automatically."
            ),
        }


ProductViewFormSet = inlineformset_factory(
    Product,
    ProductView,
    form=ProductViewForm,
    extra=0,
    can_delete=False,
    min_num=1,
    validate_min=True,
    max_num=MAX_PRODUCT_VIEWS,
    validate_max=True,
)


class SideAreaForm(BootstrapFormMixin, forms.Form):
    """Printable area of one product side, drawn in the staff wizard.

    The browser draws a rectangle and submits normalized ratios. They are
    converted to pixels only after ``optimize_mockup`` has stored the final
    canvas dimensions, so the saved area always matches the optimized mockup
    used by the customer editor and the renderer.

    Unchecking ``customizable`` turns the side into a fixed side: no area is
    saved, the side is never offered to the customer and it is printed exactly
    as its mockup.
    """

    customizable = forms.BooleanField(
        required=False,
        initial=True,
        label="Customers can customize this side",
        help_text=(
            "Uncheck it for a fixed side: customers will only see the mockup, "
            "and the side is printed unchanged."
        ),
    )
    full_face = forms.BooleanField(
        required=False,
        label="Use the entire side",
        help_text="Make the whole optimized mockup available for customization.",
    )
    x_ratio = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.HiddenInput,
    )
    y_ratio = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.HiddenInput,
    )
    width_ratio = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.HiddenInput,
    )
    height_ratio = forms.FloatField(
        required=False,
        min_value=0,
        max_value=1,
        widget=forms.HiddenInput,
    )
    rotation = forms.FloatField(
        required=False,
        min_value=-180,
        max_value=180,
        initial=0,
        label="Default rotation (degrees)",
    )
    allow_rotation = forms.BooleanField(
        required=False,
        initial=True,
        label="Customers can rotate the artwork",
    )
    allow_scaling = forms.BooleanField(
        required=False,
        initial=True,
        label="Customers can zoom the artwork",
    )
    max_file_size_mb = forms.IntegerField(
        required=False,
        min_value=1,
        label="Maximum image size (MB)",
        help_text="Cannot exceed the store-wide customer upload limit.",
    )
    aspect_ratio_locked = forms.BooleanField(
        required=False,
        label="Lock the original aspect ratio",
    )

    def __init__(self, *args, canvas_width=0, canvas_height=0, **kwargs):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        super().__init__(*args, **kwargs)
        upload_limit = settings.CUSTOMIZATION_MAX_UPLOAD_MB
        self.fields["max_file_size_mb"].initial = upload_limit
        self.fields["max_file_size_mb"].max_value = upload_limit
        self.fields["max_file_size_mb"].help_text = (
            f"Cannot exceed the store-wide limit of {upload_limit} MB."
        )
        self.fields["rotation"].widget.attrs.update(
            {"min": "-180", "max": "180", "step": "1"}
        )
        self.fields["max_file_size_mb"].widget.attrs.update(
            {"min": "1", "max": str(upload_limit), "step": "1"}
        )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data:
            return cleaned_data

        # A fixed side has no printable area: nothing else to validate.
        if not cleaned_data.get("customizable"):
            return cleaned_data

        if cleaned_data.get("full_face"):
            cleaned_data.update(
                {
                    "x_ratio": 0.0,
                    "y_ratio": 0.0,
                    "width_ratio": 1.0,
                    "height_ratio": 1.0,
                }
            )
            return cleaned_data

        ratio_fields = ("x_ratio", "y_ratio", "width_ratio", "height_ratio")
        if any(cleaned_data.get(field) is None for field in ratio_fields):
            raise forms.ValidationError(
                "Draw a printable area, enable “Use the entire side” or uncheck "
                "“Customers can customize this side”."
            )

        x = cleaned_data["x_ratio"]
        y = cleaned_data["y_ratio"]
        width = cleaned_data["width_ratio"]
        height = cleaned_data["height_ratio"]

        if width <= 0 or height <= 0:
            self.add_error("width_ratio", "The printable area must have a positive size.")
        if x + width > 1.000001:
            self.add_error("width_ratio", "The printable area exceeds the mockup width.")
        if y + height > 1.000001:
            self.add_error("height_ratio", "The printable area exceeds the mockup height.")
        if self.canvas_width and width * self.canvas_width < 1:
            self.add_error("width_ratio", "The printable area is too narrow.")
        if self.canvas_height and height * self.canvas_height < 1:
            self.add_error("height_ratio", "The printable area is too short.")

        max_size = cleaned_data.get("max_file_size_mb")
        if max_size and max_size > settings.CUSTOMIZATION_MAX_UPLOAD_MB:
            self.add_error(
                "max_file_size_mb",
                f"The limit cannot exceed the global cap of "
                f"{settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB.",
            )

        return cleaned_data

    def apply_to(self, product_view):
        """Store the drawn area (or the fixed-side flag) on the product side."""

        if not self.cleaned_data.get("customizable"):
            product_view.make_fixed()
        else:
            if self.cleaned_data.get("full_face"):
                x = 0.0
                y = 0.0
                width = float(product_view.canvas_width_px)
                height = float(product_view.canvas_height_px)
            else:
                x = round(self.cleaned_data["x_ratio"] * product_view.canvas_width_px, 2)
                y = round(self.cleaned_data["y_ratio"] * product_view.canvas_height_px, 2)
                width = round(
                    self.cleaned_data["width_ratio"] * product_view.canvas_width_px, 2
                )
                height = round(
                    self.cleaned_data["height_ratio"] * product_view.canvas_height_px, 2
                )
            product_view.print_x = x
            product_view.print_y = y
            product_view.print_width = width
            product_view.print_height = height

        product_view.rotation = float(self.cleaned_data.get("rotation") or 0)
        product_view.allow_rotation = bool(self.cleaned_data.get("allow_rotation"))
        product_view.allow_scaling = bool(self.cleaned_data.get("allow_scaling"))
        product_view.aspect_ratio_locked = bool(
            self.cleaned_data.get("aspect_ratio_locked")
        )
        product_view.max_file_size_mb = (
            self.cleaned_data.get("max_file_size_mb")
            or settings.CUSTOMIZATION_MAX_UPLOAD_MB
        )
        return product_view
