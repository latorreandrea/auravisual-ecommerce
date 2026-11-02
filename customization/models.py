import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def _preview_upload_path(instance, filename):
    return f"customization/previews/{uuid.uuid4().hex}.webp"


def _print_upload_path(instance, filename):
    return f"customization/prints/{uuid.uuid4().hex}.zip"


class CustomizationDraft(models.Model):
    """A saved customization project for a user and a product.

    The id is a UUID because it is handed to the external cart/checkout app as
    a reference. All placement data lives in ``configuration_json`` while the
    generated preview and print files are stored on the model.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customization_drafts",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="customization_drafts",
    )
    name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Project name shown in the dashboard and in the print files.",
    )
    configuration_json = models.JSONField(default=dict, blank=True)
    preview_webp_url = models.FileField(upload_to=_preview_upload_path, blank=True)
    print_file_url = models.FileField(upload_to=_print_upload_path, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-created_at")

    def __str__(self):
        return f"{self.display_name} ({self.pk})"

    @property
    def display_name(self):
        """Project name, falling back to the product and the save date."""

        name = (self.name or "").strip()
        if name:
            return name
        if self.updated_at:
            saved_on = timezone.localtime(self.updated_at).strftime("%d/%m/%Y")
            return f"{self.product.title} · {saved_on}"
        return self.product.title

    @property
    def preview_url(self):
        return self.preview_webp_url.url if self.preview_webp_url else ""

    @property
    def print_url(self):
        return self.print_file_url.url if self.print_file_url else ""

    def asset_paths(self):
        """Storage paths of the customer images referenced by the project."""

        paths = []
        for view in (self.configuration_json or {}).get("views", []):
            path = view.get("image", {}).get("asset_path")
            if path:
                paths.append(path)
        return paths
