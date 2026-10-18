"""Server-side compositing of mockups, customer images and preview generation."""

import io
from uuid import uuid4

from PIL import Image, ImageChops, ImageDraw, ImageOps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

RESAMPLING = getattr(Image, "Resampling", Image).LANCZOS
# Pillow's affine transform (used by rotate with expand=True) only accepts
# NEAREST, BILINEAR or BICUBIC resampling.
ROTATION_RESAMPLING = getattr(Image, "Resampling", Image).BICUBIC


def _load_storage_image(path):
    with default_storage.open(path, "rb") as stored_file:
        payload = stored_file.read()
    with Image.open(io.BytesIO(payload)) as image:
        return ImageOps.exif_transpose(image).convert("RGBA")


def _load_field_image(field_file):
    with field_file.storage.open(field_file.name, "rb") as stored_file:
        payload = stored_file.read()
    with Image.open(io.BytesIO(payload)) as image:
        return ImageOps.exif_transpose(image).convert("RGBA")


def _group_items_by_view(configuration):
    grouped = {}
    for view_entry in (configuration or {}).get("views", []):
        view_id = view_entry.get("product_view_id")
        if view_id:
            grouped[view_id] = view_entry.get("zones", [])
    return grouped


def render_view(view, zone_items, target_width=None):
    """Render one product view at mockup resolution (or scaled for a preview)."""

    canvas_width = view.canvas_width_px or 0
    canvas_height = view.canvas_height_px or 0
    if not canvas_width or not canvas_height:
        raise ValidationError(f'The mockup "{view.name}" has no canvas dimensions.')

    scale = 1.0
    if target_width and canvas_width > target_width:
        scale = target_width / canvas_width

    output_width = max(1, round(canvas_width * scale))
    output_height = max(1, round(canvas_height * scale))

    base = _load_field_image(view.mockup_image).resize(
        (output_width, output_height), RESAMPLING
    )
    canvas = Image.new("RGBA", (output_width, output_height), (255, 255, 255, 0))
    canvas.alpha_composite(base)

    zones = {zone.pk: zone for zone in view.zones.all()}

    for item in zone_items:
        zone = zones.get(item.get("zone_id"))
        asset_path = item.get("asset_path")
        if zone is None or not asset_path:
            continue
        if not default_storage.exists(asset_path):
            continue

        transform = item.get("transform") or {}
        try:
            x = float(transform.get("x", zone.x))
            y = float(transform.get("y", zone.y))
            width = float(transform.get("width", zone.width))
            height = float(transform.get("height", zone.height))
            rotation = float(transform.get("rotation", 0))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue

        image = _load_storage_image(asset_path).resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            RESAMPLING,
        )
        if rotation:
            # CSS/JS rotations are clockwise; Pillow rotates counter-clockwise.
            image = image.rotate(
                -rotation, expand=True, resample=ROTATION_RESAMPLING
            )

        center_x = (x + width / 2) * scale
        center_y = (y + height / 2) * scale
        left = round(center_x - image.width / 2)
        top = round(center_y - image.height / 2)

        layer = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))
        layer.paste(image, (left, top), image)

        # Clip the transformed image to the area chosen by the admin.
        mask = Image.new("L", (output_width, output_height), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle(
            [
                round(zone.x * scale),
                round(zone.y * scale),
                round((zone.x + zone.width) * scale),
                round((zone.y + zone.height) * scale),
            ],
            fill=255,
        )
        alpha = ImageChops.multiply(layer.getchannel("A"), mask)
        layer.putalpha(alpha)
        canvas = Image.alpha_composite(canvas, layer)

    if view.overlay_texture:
        overlay = _load_field_image(view.overlay_texture).resize(
            (output_width, output_height), RESAMPLING
        )
        canvas = Image.alpha_composite(canvas, overlay)

    return canvas


def _encode_webp(image, quality):
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6, alpha_quality=100)
    return buffer.getvalue()


def _build_preview_sheet(draft, preview_width=900):
    configuration = draft.configuration_json or {}
    items_by_view = _group_items_by_view(configuration)
    views = {view.pk: view for view in draft.product.views.prefetch_related("zones").all()}

    rendered = []
    for view_id, zone_items in items_by_view.items():
        view = views.get(view_id)
        if view is None or not zone_items:
            continue
        target_width = min(preview_width, view.canvas_width_px or preview_width)
        rendered.append(render_view(view, zone_items, target_width=target_width))

    if not rendered:
        raise ValidationError("There is nothing to render for this customization.")
    if len(rendered) == 1:
        return rendered[0]

    gap = 16
    width = max(image.width for image in rendered)
    height = sum(image.height for image in rendered) + gap * (len(rendered) - 1)
    sheet = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    top = 0
    for image in rendered:
        left = (width - image.width) // 2
        sheet.alpha_composite(image, (left, top))
        top += image.height + gap
    return sheet


def generate_preview(draft):
    """Render and store the combined WebP preview, keeping it below the cap."""

    preview = _build_preview_sheet(draft)
    max_bytes = settings.CUSTOMIZATION_PREVIEW_MAX_BYTES
    quality = settings.CUSTOMIZATION_PREVIEW_WEBP_QUALITY
    payload = _encode_webp(preview, quality)

    attempts = 0
    while len(payload) > max_bytes and attempts < 12:
        attempts += 1
        if quality > 60:
            quality = max(60, quality - 10)
        else:
            preview = preview.resize(
                (max(1, round(preview.width * 0.85)), max(1, round(preview.height * 0.85))),
                RESAMPLING,
            )
        payload = _encode_webp(preview, quality)

    filename = f"{uuid4().hex}.webp"
    draft.preview_webp_url.save(
        filename,
        ContentFile(payload, name=filename),
        save=True,
    )
    return draft
