"""Shared Pillow helpers used by product mockups and customer uploads."""

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}


def bytes_to_mb(num_bytes):
    return f"{num_bytes / (1024 * 1024):g} MB"


def upload_size(uploaded_file):
    size = getattr(uploaded_file, "size", None)
    if size is not None:
        return int(size)
    try:
        position = uploaded_file.tell()
        uploaded_file.seek(0, 2)
        size = uploaded_file.tell()
        uploaded_file.seek(position)
        return int(size)
    except (AttributeError, OSError, ValueError):
        return 0


def validate_image_upload(
    uploaded_file,
    *,
    max_bytes,
    max_pixels,
    allowed_formats=ALLOWED_IMAGE_FORMATS,
    label="image",
):
    """Validate size, real format and pixel count before Pillow processes a file.

    Returns a dict with ``format``, ``width``, ``height`` and ``size``.
    The caller is responsible for seeking the file back to the beginning before
    reading it again (this helper always restores position 0 on success).
    """

    if uploaded_file is None:
        raise ValidationError(f"Please choose a {label}.")

    size = upload_size(uploaded_file)
    if size <= 0:
        raise ValidationError(f"The uploaded {label} is empty.")
    if size > max_bytes:
        raise ValidationError(
            f"The {label} must be {bytes_to_mb(max_bytes)} or smaller "
            f"(received {bytes_to_mb(size)})."
        )

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image_format = (image.format or "").upper()
            width, height = image.size

            if image_format not in allowed_formats:
                raise ValidationError(
                    f"Unsupported {label} format. Use PNG, JPEG or WebP."
                )
            if width <= 0 or height <= 0:
                raise ValidationError(f"The uploaded {label} has invalid dimensions.")
            if width * height > max_pixels:
                raise ValidationError(
                    f"The {label} is too large ({width}x{height} pixels). "
                    "Please resize it before uploading."
                )
            image.verify()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise ValidationError(
            f"The uploaded {label} is not a valid image. Use PNG, JPEG or WebP."
        ) from exc
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError, ValueError):
            pass

    return {"format": image_format, "width": width, "height": height, "size": size}


def image_has_alpha(image):
    return image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def open_rgba(source):
    """Open a file-like source, apply EXIF orientation and return an RGBA image."""

    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        return image.convert("RGBA")
