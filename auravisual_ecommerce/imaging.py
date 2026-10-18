"""Shared Pillow helpers used by product mockups and customer uploads."""

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError

ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}

EXIF_ORIENTATION_TAG = 0x0112
# EXIF orientations 5-8 rotate the image by 90 or 270 degrees, which swaps its
# stored width and height. Browsers apply that rotation automatically, so the
# server must use the same dimensions or the saved artwork would be distorted.
TRANSPOSED_ORIENTATIONS = {5, 6, 7, 8}


def image_orientation(image):
    try:
        orientation = image.getexif().get(EXIF_ORIENTATION_TAG, 1) or 1
        return int(orientation)
    except (AttributeError, OSError, SyntaxError, TypeError, ValueError):
        return 1


def oriented_dimensions(image):
    """Return ``(width, height)`` as displayed after EXIF orientation."""

    width, height = image.size
    if image_orientation(image) in TRANSPOSED_ORIENTATIONS:
        return height, width
    return width, height


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
            if image_format not in allowed_formats:
                raise ValidationError(
                    f"Unsupported {label} format. Use PNG, JPEG or WebP."
                )
            # verify() must run before any exif/dimension access loads pixels.
            image.verify()

        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            width, height = oriented_dimensions(image)

        if width <= 0 or height <= 0:
            raise ValidationError(f"The uploaded {label} has invalid dimensions.")
        if width * height > max_pixels:
            raise ValidationError(
                f"The {label} is too large ({width}x{height} pixels). "
                "Please resize it before uploading."
            )
    except ValidationError:
        raise
    except Image.DecompressionBombError as exc:
        raise ValidationError(
            f"The {label} has too many pixels. Please resize it before uploading."
        ) from exc
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
