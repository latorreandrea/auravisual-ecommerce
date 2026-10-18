"""Optimisation of admin-uploaded product mockups."""

import io
from uuid import uuid4

from PIL import Image, ImageOps
from django.conf import settings
from django.core.files.base import ContentFile

from auravisual_ecommerce.imaging import image_has_alpha, validate_image_upload


def optimize_mockup(uploaded_file):
    """Return ``(ContentFile, width, height)`` for an optimised WebP mockup.

    - real format and size are validated before decoding;
    - EXIF orientation is applied;
    - alpha is preserved (the admin can upload a transparent PNG);
    - the longest side is capped at ``PRODUCT_MOCKUP_MAX_DIMENSION``;
    - the result is converted to WebP and metadata is dropped.
    """

    max_bytes = settings.PRODUCT_MOCKUP_MAX_UPLOAD_MB * 1024 * 1024
    validate_image_upload(
        uploaded_file,
        max_bytes=max_bytes,
        max_pixels=settings.PRODUCT_MOCKUP_MAX_PIXELS,
        label="mockup image",
    )

    uploaded_file.seek(0)
    with Image.open(uploaded_file) as source:
        image = ImageOps.exif_transpose(source)
        has_alpha = image_has_alpha(image)
        image = image.convert("RGBA" if has_alpha else "RGB")

        max_dimension = settings.PRODUCT_MOCKUP_MAX_DIMENSION
        if max(image.size) > max_dimension:
            image.thumbnail(
                (max_dimension, max_dimension),
                Image.Resampling.LANCZOS,
            )

        width, height = image.size
        buffer = io.BytesIO()
        save_kwargs = {
            "format": "WEBP",
            "quality": settings.PRODUCT_MOCKUP_WEBP_QUALITY,
            "method": 6,
        }
        if has_alpha:
            save_kwargs.update({"alpha_quality": 100, "exact": True})

        try:
            image.save(buffer, **save_kwargs)
        except (OSError, ValueError):
            # Older Pillow/WebP builds may not accept the alpha options.
            image.save(
                buffer,
                format="WEBP",
                quality=settings.PRODUCT_MOCKUP_WEBP_QUALITY,
                method=6,
            )

    return (
        ContentFile(buffer.getvalue(), name=f"{uuid4().hex}.webp"),
        width,
        height,
    )
