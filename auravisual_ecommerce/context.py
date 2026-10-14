"""Template context processors for the AuraVisual Ecommerce project."""

from django.conf import settings


def asset_version(request):
    """Expose ``ASSET_VERSION`` so static assets can be cache-busted.

    Templates use it as ``{% static 'css/style.css' %}?v={{ ASSET_VERSION }}``.
    """
    return {"ASSET_VERSION": settings.ASSET_VERSION}
