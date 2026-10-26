from django import forms
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.forms import inlineformset_factory

from .models import CustomizationZone, Product, ProductView
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


class PrintAreaForm(BootstrapFormMixin, forms.Form):
    """One printable area for a product side.

    The browser draws a rectangle and submits normalized ratios. They are
    converted to pixels only after ``optimize_mockup`` has stored the final
    canvas dimensions, so the saved zone always matches the optimized mockup
    used by the customer editor and the renderer.
    """

    name = forms.CharField(
        required=False,
        max_length=80,
        label="Area name",
        help_text="Shown in the customer editor. Defaults to the side name.",
    )
    full_face = forms.BooleanField(
        required=False,
        label="Use the entire face",
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
                "Draw a printable area or enable “Use the entire face”."
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

    def build_zone(self, product_view):
        """Return an unsaved ``CustomizationZone`` for the optimized side."""

        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            name = f"{product_view.name} artwork"

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

        return CustomizationZone(
            product_view=product_view,
            name=name,
            x=x,
            y=y,
            width=width,
            height=height,
            rotation=self.cleaned_data.get("rotation") or 0,
            allow_rotation=self.cleaned_data.get("allow_rotation", True),
            allow_scaling=self.cleaned_data.get("allow_scaling", True),
            max_file_size_mb=(
                self.cleaned_data.get("max_file_size_mb")
                or settings.CUSTOMIZATION_MAX_UPLOAD_MB
            ),
            aspect_ratio_locked=self.cleaned_data.get("aspect_ratio_locked", False),
        )
