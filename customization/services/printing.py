"""Deferred generation of the print-ready files for paid customizations."""

import io
from uuid import uuid4

from PIL import Image
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .rendering import _group_items_by_view, render_view


def _flatten_on_white(image):
    flat = Image.new("RGB", image.size, "white")
    flat.paste(image, mask=image.getchannel("A"))
    return flat


def _build_print_images(draft):
    configuration = draft.configuration_json or {}
    items_by_view = _group_items_by_view(configuration)
    views = {view.pk: view for view in draft.product.views.prefetch_related("zones").all()}

    rendered = []
    for view_id, zone_items in items_by_view.items():
        view = views.get(view_id)
        if view is None or not zone_items:
            continue
        rendered.append(_flatten_on_white(render_view(view, zone_items)))

    if not rendered:
        raise ValidationError("There is nothing to print for this customization.")
    return rendered


def generate_print_file(draft, force=False):
    """Create one PNG (single view) or PDF (multiple views) at print resolution."""

    if (
        draft.print_file_url
        and not force
        and default_storage.exists(draft.print_file_url.name)
    ):
        return draft

    images = _build_print_images(draft)
    dpi = settings.CUSTOMIZATION_PRINT_DPI
    buffer = io.BytesIO()

    if len(images) == 1:
        images[0].save(buffer, format="PNG", dpi=(dpi, dpi), optimize=True)
        extension = "png"
    else:
        images[0].save(
            buffer,
            format="PDF",
            resolution=dpi,
            save_all=True,
            append_images=images[1:],
        )
        extension = "pdf"

    filename = f"{uuid4().hex}-print.{extension}"
    draft.print_file_url.save(
        filename,
        ContentFile(buffer.getvalue(), name=filename),
        save=True,
    )
    return draft
