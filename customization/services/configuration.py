"""Parse and validate the JSON configuration sent by the editor."""

import json
import math
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from .assets import (
    asset_dimensions,
    delete_assets,
    is_draft_asset_path,
    save_asset,
    validate_asset_file,
)

# The editor lets customers zoom up to twice the printable area; the server
# accepts the same range and clips whatever exceeds the area.
MAX_AREA_SCALE = 2.0


def load_configuration(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        raise ValidationError("The customization configuration is empty.")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError("The customization configuration is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ValidationError("The customization configuration must be an object.")
    return payload


def _as_int(value, label):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Invalid {label}.") from exc


def _as_float(value, label, default=None):
    if value is None or value == "":
        if default is not None:
            return float(default)
        raise ValidationError(f"Missing {label}.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{label} must be a finite number.")
    return number


def _fit_dimensions(natural_width, natural_height, max_width, max_height, allow_upscale=False):
    ratio = min(max_width / natural_width, max_height / natural_height)
    if not allow_upscale:
        ratio = min(ratio, 1.0)
    return max(1.0, natural_width * ratio), max(1.0, natural_height * ratio)


def _normalize_transform(raw_transform, area, natural_width, natural_height):
    raw_transform = raw_transform if isinstance(raw_transform, dict) else {}
    default_width, default_height = _fit_dimensions(
        natural_width, natural_height, area.width, area.height
    )
    max_width = float(area.width) * MAX_AREA_SCALE
    max_height = float(area.height) * MAX_AREA_SCALE

    if raw_transform.get("width") is None and raw_transform.get("scale") is not None:
        scale = _as_float(raw_transform.get("scale"), "scale", 1.0)
        width = natural_width * scale
        height = natural_height * scale
    else:
        width = _as_float(raw_transform.get("width"), "width", default_width)
        height = _as_float(raw_transform.get("height"), "height", default_height)

    if not area.allow_scaling:
        width, height = default_width, default_height

    width = min(max(width, 1.0), max_width)
    height = min(max(height, 1.0), max_height)

    if area.aspect_ratio_locked or not area.allow_scaling:
        aspect_ratio = natural_width / natural_height
        height = width / aspect_ratio
        if height > max_height:
            height = max_height
            width = height * aspect_ratio
        width = min(max(width, 1.0), max_width)

    left = float(area.x)
    top = float(area.y)
    x = _as_float(raw_transform.get("x"), "x", left + (float(area.width) - width) / 2)
    y = _as_float(raw_transform.get("y"), "y", top + (float(area.height) - height) / 2)
    # Keep the centre of the image inside the printable area, exactly like the
    # browser editor does, so zoomed-in artwork cannot be dragged away.
    center_x = min(max(x + width / 2, left), left + float(area.width))
    center_y = min(max(y + height / 2, top), top + float(area.height))
    x = center_x - width / 2
    y = center_y - height / 2

    rotation = _as_float(
        raw_transform.get("rotation"),
        "rotation",
        float(area.rotation or 0.0),
    )
    if area.allow_rotation:
        rotation = ((rotation + 180.0) % 360.0) - 180.0
    else:
        rotation = 0.0

    return {
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(width, 2),
        "height": round(height, 2),
        "scale": round(width / natural_width, 4),
        "rotation": round(rotation, 2),
    }


def build_configuration(product, raw, draft, uploaded_files):
    """Validate the payload, store new assets and return the saved configuration.

    Each customizable side carries at most one customer image, so the saved
    JSON is a flat list of ``views`` entries: ``{product_view_id, view_name,
    image}``.
    """

    views = {view.pk: view for view in product.views.all()}

    raw_views = raw.get("views")
    if not isinstance(raw_views, list) or not raw_views:
        raise ValidationError("Add at least one image to the product.")

    entries = []
    seen_views = set()

    for raw_view in raw_views:
        if not isinstance(raw_view, dict):
            raise ValidationError("Invalid view entry.")
        view_id = _as_int(raw_view.get("product_view_id"), "product view")
        view = views.get(view_id)
        if view is None:
            raise ValidationError("The selected product view does not exist.")
        area = view.print_area
        if area is None:
            raise ValidationError(f'The side "{view.name}" cannot be customized.')
        if view_id in seen_views:
            raise ValidationError(f'The side "{view.name}" appears more than once.')
        seen_views.add(view_id)

        raw_image = raw_view.get("image") or {}
        if not isinstance(raw_image, dict):
            raise ValidationError("Invalid image entry.")

        uploaded_file = uploaded_files.get(view_id)
        raw_existing_path = raw_image.get("asset_path")
        if raw_existing_path is None:
            existing_path = ""
        elif isinstance(raw_existing_path, str):
            existing_path = raw_existing_path.strip()
        else:
            raise ValidationError("Invalid existing image reference.")

        if uploaded_file is not None:
            image_info = validate_asset_file(uploaded_file, area)
            natural_width, natural_height = image_info["width"], image_info["height"]
            source = "upload"
        elif existing_path:
            if not is_draft_asset_path(draft, existing_path):
                raise ValidationError("Invalid existing image reference.")
            if not default_storage.exists(existing_path):
                raise ValidationError("A previously uploaded image is missing.")
            natural_width, natural_height = asset_dimensions(existing_path)
            image_info = None
            source = "existing"
        else:
            # No image for this side: the customer did not customize it.
            continue

        entries.append(
            {
                "view": view,
                "area": area,
                "uploaded_file": uploaded_file,
                "image_info": image_info,
                "existing_path": existing_path,
                "source": source,
                "natural_width": natural_width,
                "natural_height": natural_height,
                "raw_transform": raw_image.get("transform") or {},
                "original_name": Path(str(raw_image.get("original_name") or "")).name,
            }
        )

    if not entries:
        raise ValidationError("Add at least one image to the product.")

    # Validate every transform before writing any file, so a bad payload cannot
    # leave partially saved assets behind.
    for entry in entries:
        entry["transform"] = _normalize_transform(
            entry["raw_transform"],
            entry["area"],
            entry["natural_width"],
            entry["natural_height"],
        )

    grouped = []
    saved_asset_paths = []
    try:
        for entry in entries:
            view = entry["view"]
            if entry["source"] == "upload":
                asset_path, asset_url = save_asset(
                    draft, entry["uploaded_file"], entry["image_info"]
                )
                saved_asset_paths.append(asset_path)
                original_name = entry["original_name"] or getattr(
                    entry["uploaded_file"], "name", ""
                )
            else:
                asset_path = entry["existing_path"]
                asset_url = default_storage.url(asset_path)
                original_name = entry["original_name"]

            grouped.append(
                {
                    "product_view_id": view.pk,
                    "view_name": view.name,
                    "image": {
                        "asset_path": asset_path,
                        "asset_url": asset_url,
                        "original_name": Path(original_name or "").name,
                        "natural_width": entry["natural_width"],
                        "natural_height": entry["natural_height"],
                        "transform": entry["transform"],
                    },
                }
            )
    except Exception:
        # A storage error halfway through must not leave unreferenced uploads.
        delete_assets(saved_asset_paths)
        raise

    grouped.sort(
        key=lambda item: (
            views[item["product_view_id"]].sort_order,
            views[item["product_view_id"]].pk,
        )
    )
    return {"views": grouped}
