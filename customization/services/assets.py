"""Validation and storage of customer-uploaded customization assets."""

import io
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage

from auravisual_ecommerce.imaging import bytes_to_mb, upload_size, validate_image_upload

EXTENSION_BY_FORMAT = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}


def validate_total_upload_size(files):
    limit = settings.CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB * 1024 * 1024
    total = sum(upload_size(uploaded_file) for uploaded_file in files)
    if total > limit:
        raise ValidationError(
            f"The images uploaded in one request must weigh {bytes_to_mb(limit)} or less "
            f"(received {bytes_to_mb(total)})."
        )
    return total


def validate_asset_file(uploaded_file, zone):
    return validate_image_upload(
        uploaded_file,
        max_bytes=zone.effective_max_file_size_mb * 1024 * 1024,
        max_pixels=settings.CUSTOMIZATION_MAX_IMAGE_PIXELS,
        label="image",
    )


def is_draft_asset_path(draft, path):
    root = f"customization/drafts/{draft.pk}/assets/"
    return bool(path) and path.startswith(root) and ".." not in path


def save_asset(draft, uploaded_file, image_info):
    extension = EXTENSION_BY_FORMAT.get(image_info["format"], ".img")
    path = f"customization/drafts/{draft.pk}/assets/{uuid4().hex}{extension}"
    uploaded_file.seek(0)
    saved_path = default_storage.save(path, uploaded_file)
    return saved_path, default_storage.url(saved_path)


def asset_dimensions(path):
    with default_storage.open(path, "rb") as stored_file:
        payload = stored_file.read()

    try:
        with Image.open(io.BytesIO(payload)) as image:
            return image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("A previously uploaded image is no longer readable.") from exc
