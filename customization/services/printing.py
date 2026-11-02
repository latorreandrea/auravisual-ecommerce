"""Deferred generation of the print-ready archive for paid customizations."""

import io
import re
import zipfile
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .rendering import configuration_views, flatten_on_white, render_view

INVALID_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9 _-]+")


def _side_filename(view, used_names):
    """A readable, unique file name for one printed side."""

    base = INVALID_FILENAME_CHARS.sub("", view.name or "").strip()
    base = re.sub(r"\s+", " ", base) or f"side-{view.sort_order}"
    candidate = base
    suffix = 2
    while candidate.lower() in used_names:
        candidate = f"{base} ({suffix})"
        suffix += 1
    used_names.add(candidate.lower())
    return f"{candidate}.png"


def _build_print_entries(draft):
    """Return ``(filename, image)`` for every side that must be printed.

    Fixed sides are printed exactly as their mockup; customizable sides are
    printed only when the customer added an image to them.
    """

    views_by_id = {view.pk: view for view in draft.product.views.all()}
    entries_by_view = {
        entry.get("product_view_id"): entry
        for entry in configuration_views(draft.configuration_json)
    }

    printed = []
    used_names = set()
    for view_id, view in views_by_id.items():
        entry = entries_by_view.get(view_id)
        if entry is None and view.is_customizable:
            continue
        image = flatten_on_white(render_view(view, entry))
        printed.append((_side_filename(view, used_names), image))

    if not printed:
        raise ValidationError("There is nothing to print for this customization.")
    return printed


def generate_print_file(draft, force=False):
    """Create one ZIP archive that holds a print-resolution PNG per side.

    CardPresso consumes the archive directly, so the store never keeps loose
    print files around: one draft maps to exactly one stored object.
    """

    if (
        draft.print_file_url
        and not force
        and default_storage.exists(draft.print_file_url.name)
    ):
        return draft

    entries = _build_print_entries(draft)
    dpi = settings.CUSTOMIZATION_PRINT_DPI

    buffer = io.BytesIO()
    # PNGs are already compressed: ZIP_STORED keeps the archive fast to build.
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for filename, image in entries:
            payload = io.BytesIO()
            image.save(payload, format="PNG", dpi=(dpi, dpi), optimize=True)
            archive.writestr(filename, payload.getvalue())

    filename = f"{uuid4().hex}.zip"
    draft.print_file_url.save(
        filename,
        ContentFile(buffer.getvalue(), name=filename),
        save=True,
    )
    return draft
