"""Parse and validate the JSON configuration sent by the editor."""

import json
import math
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from .assets import (
    asset_dimensions,
    is_draft_asset_path,
    save_asset,
    validate_asset_file,
)


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


def _normalize_transform(raw_transform, zone, natural_width, natural_height):
    raw_transform = raw_transform if isinstance(raw_transform, dict) else {}
    default_width, default_height = _fit_dimensions(
        natural_width, natural_height, zone.width, zone.height
    )

    if raw_transform.get("width") is None and raw_transform.get("scale") is not None:
        scale = _as_float(raw_transform.get("scale"), "scale", 1.0)
        width = natural_width * scale
        height = natural_height * scale
    else:
        width = _as_float(raw_transform.get("width"), "width", default_width)
        height = _as_float(raw_transform.get("height"), "height", default_height)

    if not zone.allow_scaling:
        width, height = default_width, default_height

    width = min(max(width, 1.0), float(zone.width))
    height = min(max(height, 1.0), float(zone.height))

    if zone.aspect_ratio_locked or not zone.allow_scaling:
        aspect_ratio = natural_width / natural_height
        height = width / aspect_ratio
        if height > zone.height:
            height = float(zone.height)
            width = height * aspect_ratio
        width = min(max(width, 1.0), float(zone.width))

    max_x = max(float(zone.x), float(zone.x) + float(zone.width) - width)
    max_y = max(float(zone.y), float(zone.y) + float(zone.height) - height)
    x = _as_float(raw_transform.get("x"), "x", float(zone.x) + (zone.width - width) / 2)
    y = _as_float(raw_transform.get("y"), "y", float(zone.y) + (zone.height - height) / 2)
    x = min(max(x, float(zone.x)), max_x)
    y = min(max(y, float(zone.y)), max_y)

    rotation = _as_float(raw_transform.get("rotation"), "rotation", 0.0)
    if zone.allow_rotation:
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
    """Validate the payload, store new assets and return the normalized config."""

    views = {
        view.pk: view
        for view in product.views.prefetch_related("zones").all()
    }
    zones = {
        zone.pk: zone
        for view in views.values()
        for zone in view.zones.all()
    }

    raw_views = raw.get("views")
    if not isinstance(raw_views, list) or not raw_views:
        raise ValidationError("Add at least one image to the product.")

    entries = []
    seen_zones = set()

    for raw_view in raw_views:
        if not isinstance(raw_view, dict):
            raise ValidationError("Invalid view entry.")
        view_id = _as_int(raw_view.get("product_view_id"), "product view")
        view = views.get(view_id)
        if view is None:
            raise ValidationError("The selected product view does not exist.")

        raw_zones = raw_view.get("zones") or []
        if not isinstance(raw_zones, list):
            raise ValidationError("Invalid zones entry.")

        for raw_zone in raw_zones:
            if not isinstance(raw_zone, dict):
                raise ValidationError("Invalid zone entry.")
            zone_id = _as_int(raw_zone.get("zone_id"), "zone")
            zone = zones.get(zone_id)
            if zone is None or zone.product_view_id != view.pk:
                raise ValidationError("The selected customization area does not exist.")
            if zone_id in seen_zones:
                raise ValidationError(f'The area "{zone.name}" appears more than once.')
            seen_zones.add(zone_id)

            uploaded_file = uploaded_files.get(zone_id)
            existing_path = (raw_zone.get("asset_path") or "").strip()

            if uploaded_file is not None:
                image_info = validate_asset_file(uploaded_file, zone)
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
                # Empty area: the user did not customize it.
                continue

            entries.append(
                {
                    "view": view,
                    "zone": zone,
                    "uploaded_file": uploaded_file,
                    "image_info": image_info,
                    "existing_path": existing_path,
                    "source": source,
                    "natural_width": natural_width,
                    "natural_height": natural_height,
                    "raw_transform": raw_zone.get("transform") or {},
                    "original_name": Path(str(raw_zone.get("original_name") or "")).name,
                }
            )

    if not entries:
        raise ValidationError("Add at least one image to the product.")

    grouped = {}
    for entry in entries:
        view = entry["view"]
        zone = entry["zone"]

        if entry["source"] == "upload":
            asset_path, asset_url = save_asset(draft, entry["uploaded_file"], entry["image_info"])
            original_name = entry["original_name"] or getattr(entry["uploaded_file"], "name", "")
        else:
            asset_path = entry["existing_path"]
            asset_url = default_storage.url(asset_path)
            original_name = entry["original_name"]

        transform = _normalize_transform(
            entry["raw_transform"],
            zone,
            entry["natural_width"],
            entry["natural_height"],
        )

        view_entry = grouped.setdefault(
            view.pk,
            {
                "product_view_id": view.pk,
                "view_name": view.name,
                "zones": [],
            },
        )
        view_entry["zones"].append(
            {
                "zone_id": zone.pk,
                "zone_name": zone.name,
                "asset_path": asset_path,
                "asset_url": asset_url,
                "original_name": Path(original_name or "").name,
                "natural_width": entry["natural_width"],
                "natural_height": entry["natural_height"],
                "transform": transform,
            }
        )

    ordered = sorted(
        grouped.values(),
        key=lambda item: (
            views[item["product_view_id"]].sort_order,
            views[item["product_view_id"]].pk,
        ),
    )
    return {"views": ordered}

    x = min(max(x, float(zone.x)), max_x)
    y = min(max(y, float(zone.y)), max_y)

    rotation = _as_float(raw_transform.get("rotation"), "rotation", 0.0)
    if zone.allow_rotation:
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
