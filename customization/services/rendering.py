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
# Rotated artwork is rendered at twice the size and then downscaled, which
# removes the stair-stepping BICUBIC leaves on hard edges.
ROTATION_SUPERSAMPLE = 2


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


def flatten_on_white(image):
    """Drop transparency by compositing the image on a white background.

    Only the print pipeline uses this (``customization.services.printing``): the
    printing service expects opaque PNGs. Previews keep their alpha channel so a
    cut-out mockup stays transparent in the workspace and catalogue cards.
    """

    flat = Image.new("RGB", image.size, "white")
    flat.paste(image, mask=image.getchannel("A"))
    return flat


def configuration_views(configuration):
    """Return the saved per-side entries that actually carry an image."""

    entries = (configuration or {}).get("views", [])
    if not isinstance(entries, list):
        return []
    selected = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        image = entry.get("image")
        if isinstance(image, dict) and image.get("asset_path"):
            selected.append(entry)
    return selected


def _render_artwork(asset_path, target_width, target_height, rotation):
    """Load, resize and rotate one customer image (clockwise, like the editor)."""

    image = _load_storage_image(asset_path)
    target_width = max(1, round(target_width))
    target_height = max(1, round(target_height))

    if not rotation:
        return image.resize((target_width, target_height), RESAMPLING)

    factor = ROTATION_SUPERSAMPLE
    big = image.resize((target_width * factor, target_height * factor), RESAMPLING)
    # CSS/JS rotations are clockwise; Pillow rotates counter-clockwise.
    big = big.rotate(-rotation, expand=True, resample=ROTATION_RESAMPLING)
    return big.resize(
        (max(1, round(big.width / factor)), max(1, round(big.height / factor))),
        RESAMPLING,
    )


def render_view(view, image_entry=None, target_width=None):
    """Render one product side at mockup resolution (or scaled for a preview).

    ``image_entry`` is the saved configuration entry of the side. Fixed sides
    have no entry: their mockup is returned as it is.
    """

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

    area = view.print_area
    image_data = (image_entry or {}).get("image") or {}
    asset_path = image_data.get("asset_path")
    if area is None or not asset_path:
        return canvas

    try:
        if not default_storage.exists(asset_path):
            return canvas
    except (OSError, ValueError):
        return canvas

    transform = image_data.get("transform") or {}
    try:
        x = float(transform.get("x", area.x))
        y = float(transform.get("y", area.y))
        width = float(transform.get("width", area.width))
        height = float(transform.get("height", area.height))
        rotation = float(transform.get("rotation", 0))
    except (TypeError, ValueError):
        return canvas
    if width <= 0 or height <= 0:
        return canvas

    image = _render_artwork(asset_path, width * scale, height * scale, rotation)

    center_x = (x + width / 2) * scale
    center_y = (y + height / 2) * scale
    left = round(center_x - image.width / 2)
    top = round(center_y - image.height / 2)

    layer = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))
    layer.paste(image, (left, top), image)

    # Clip the transformed image to the printable area chosen by the admin.
    mask = Image.new("L", (output_width, output_height), 0)
    ImageDraw.Draw(mask).rectangle(
        [
            round(area.x * scale),
            round(area.y * scale),
            round((area.x + area.width) * scale),
            round((area.y + area.height) * scale),
        ],
        fill=255,
    )
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return Image.alpha_composite(canvas, layer)


def _encode_webp(image, quality):
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6, alpha_quality=100)
    return buffer.getvalue()


def _build_primary_preview(draft, max_width=None):
    """Render the first customized side (by ``sort_order``) of the project.

    The returned image keeps its alpha channel: transparent mockups must stay
    transparent in the WebP preview shown by the workspace and catalogue cards.
    """

    max_width = max_width or settings.CUSTOMIZATION_PREVIEW_MAX_WIDTH
    views = {view.pk: view for view in draft.product.views.all()}

    for entry in configuration_views(draft.configuration_json):
        view = views.get(entry.get("product_view_id"))
        if view is None:
            continue
        target_width = min(max_width, view.canvas_width_px or max_width)
        rendered = render_view(view, entry, target_width=target_width)
        return rendered

    raise ValidationError("There is nothing to render for this customization.")


def generate_preview(draft):
    """Render and store the WebP preview of the main side, below the byte cap."""

    preview = _build_primary_preview(draft)
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
