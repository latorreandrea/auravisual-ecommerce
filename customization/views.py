import hmac
import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from products.models import Product

from .models import CustomizationDraft
from .services.assets import delete_assets, validate_total_upload_size
from .services.configuration import build_configuration, load_configuration
from .services.rendering import generate_preview
from .tasks import dispatch_print_generation

logger = logging.getLogger(__name__)


def _editor_payload(product, views, draft):
    existing = {}
    if draft:
        for view_entry in (draft.configuration_json or {}).get("views", []):
            view_id = str(view_entry.get("product_view_id"))
            for zone_entry in view_entry.get("zones", []):
                existing.setdefault(view_id, {})[str(zone_entry.get("zone_id"))] = {
                    "asset_path": zone_entry.get("asset_path", ""),
                    "asset_url": zone_entry.get("asset_url", ""),
                    "original_name": zone_entry.get("original_name", ""),
                    "natural_width": zone_entry.get("natural_width", 0),
                    "natural_height": zone_entry.get("natural_height", 0),
                    "transform": zone_entry.get("transform", {}),
                }

    payload_views = []
    for view in views:
        # Views without a saved mockup resolution cannot be edited: their zone
        # coordinates would be rendered as invalid CSS percentages.
        if not view.canvas_width_px or not view.canvas_height_px:
            continue
        zones = []
        for zone in view.zones.all():
            max_bytes = zone.effective_max_file_size_mb * 1024 * 1024
            zones.append(
                {
                    "id": zone.pk,
                    "name": zone.name,
                    "x": zone.x,
                    "y": zone.y,
                    "width": zone.width,
                    "height": zone.height,
                    "rotation": zone.rotation,
                    "allow_rotation": zone.allow_rotation,
                    "allow_scaling": zone.allow_scaling,
                    "aspect_ratio_locked": zone.aspect_ratio_locked,
                    "max_file_size_mb": zone.effective_max_file_size_mb,
                    "max_upload_bytes": max_bytes,
                }
            )
        if not zones:
            continue
        payload_views.append(
            {
                "id": view.pk,
                "name": view.name,
                "mockup_url": view.mockup_image.url if view.mockup_image else "",
                "overlay_url": view.overlay_texture.url if view.overlay_texture else "",
                "canvas_width": view.canvas_width_px,
                "canvas_height": view.canvas_height_px,
                "zones": zones,
            }
        )

    return {
        "product": {"id": product.pk, "title": product.title, "slug": product.slug},
        "draft_id": str(draft.pk) if draft else "",
        "save_url": reverse("customization:draft_save"),
        "editor_url": reverse("customization:editor", kwargs={"slug": product.slug}),
        "max_upload_bytes": settings.CUSTOMIZATION_MAX_UPLOAD_MB * 1024 * 1024,
        "max_image_pixels": settings.CUSTOMIZATION_MAX_IMAGE_PIXELS,
        "views": payload_views,
        "existing": existing,
    }


@login_required
def draft_list(request):
    drafts = CustomizationDraft.objects.filter(user=request.user).select_related("product")
    return render(request, "customization/list.html", {"drafts": drafts})


@login_required
def editor(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    views = list(product.views.prefetch_related("zones"))

    draft = None
    draft_id = request.GET.get("draft")
    if draft_id:
        try:
            draft = CustomizationDraft.objects.filter(
                pk=draft_id,
                user=request.user,
                product=product,
            ).first()
        except (ValidationError, ValueError):
            draft = None
        if draft is None:
            messages.error(request, "The customization draft you tried to open was not found.")

    editor_payload = _editor_payload(product, views, draft)
    if not editor_payload["views"]:
        messages.warning(request, "This product has no customizable areas yet.")

    return render(
        request,
        "customization/editor.html",
        {
            "product": product,
            "draft": draft,
            "editor_payload": editor_payload,
        },
    )


def _editor_redirect(product, draft=None):
    url = reverse("customization:editor", kwargs={"slug": product.slug})
    if draft and not draft._state.adding:
        return redirect(f"{url}?draft={draft.pk}")
    return redirect(url)


@login_required
@require_POST
def draft_save(request):
    try:
        product_id = int(request.POST.get("product_id") or "")
    except (TypeError, ValueError):
        messages.error(request, "The selected product is not valid.")
        return redirect("products:list")

    product = get_object_or_404(Product, pk=product_id, is_active=True)

    draft = None
    draft_id = request.POST.get("draft_id")
    if draft_id:
        try:
            draft = CustomizationDraft.objects.filter(
                pk=draft_id,
                user=request.user,
            ).first()
        except (ValidationError, ValueError):
            draft = None
        if draft is None or draft.product_id != product.pk:
            messages.error(request, "The customization draft you tried to update was not found.")
            return _editor_redirect(product)

    uploaded_files = {}
    for field_name, uploaded_file in request.FILES.items():
        if not field_name.startswith("asset_"):
            continue
        try:
            zone_id = int(field_name.split("_", 1)[1])
        except (TypeError, ValueError):
            continue
        uploaded_files[zone_id] = uploaded_file

    try:
        validate_total_upload_size(request.FILES.values())
        raw = load_configuration(request.POST.get("configuration"))
        if draft is None:
            draft = CustomizationDraft(user=request.user, product=product)
        previous_asset_paths = set(draft.asset_paths())
        configuration = build_configuration(product, raw, draft, uploaded_files)
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return _editor_redirect(product, draft)

    draft.configuration_json = configuration
    # The generated files are derived from the configuration: drop them so the
    # UI never shows a preview or print file that belongs to an older design.
    draft.preview_webp_url = ""
    draft.print_file_url = ""
    draft.save()
    delete_assets(previous_asset_paths - set(draft.asset_paths()))

    try:
        generate_preview(draft)
    except Exception:
        logger.exception("Could not generate the preview for draft %s", draft.pk)
        messages.warning(
            request,
            "The customization was saved, but the preview could not be generated.",
        )

    messages.success(request, "Your customization was saved.")
    return redirect("customization:draft_detail", draft_id=draft.pk)


@login_required
def draft_detail(request, draft_id):
    draft = get_object_or_404(
        CustomizationDraft.objects.select_related("product"),
        pk=draft_id,
        user=request.user,
    )
    configuration_views = (draft.configuration_json or {}).get("views", [])
    return render(
        request,
        "customization/detail.html",
        {"draft": draft, "configuration_views": configuration_views},
    )


@login_required
@require_POST
def draft_delete(request, draft_id):
    draft = get_object_or_404(
        CustomizationDraft,
        pk=draft_id,
        user=request.user,
    )
    product = draft.product
    draft.delete()
    messages.success(request, "The customization was deleted.")
    return redirect("customization:list")


@login_required
def draft_payload(request, draft_id):
    draft = get_object_or_404(
        CustomizationDraft.objects.select_related("product"),
        pk=draft_id,
        user=request.user,
    )
    preview_url = request.build_absolute_uri(draft.preview_url) if draft.preview_url else ""
    return JsonResponse(
        {
            "id": str(draft.pk),
            "product": {
                "id": draft.product_id,
                "title": draft.product.title,
                "slug": draft.product.slug,
            },
            "preview_url": preview_url,
            "configuration": draft.configuration_json,
            "created_at": draft.created_at.isoformat(),
            "updated_at": draft.updated_at.isoformat(),
        }
    )


@csrf_exempt
@require_POST
def order_paid_webhook(request):
    secret = settings.CUSTOMIZATION_PRINT_WEBHOOK_SECRET
    if not secret:
        return JsonResponse({"detail": "The print webhook is disabled."}, status=503)

    token = request.headers.get("X-Webhook-Token", "")
    if not hmac.compare_digest(token, secret):
        return JsonResponse({"detail": "Invalid webhook token."}, status=403)

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    raw_ids = payload.get("draft_ids") if isinstance(payload, dict) else None
    if not isinstance(raw_ids, list) or not raw_ids:
        return JsonResponse({"detail": "draft_ids must be a non-empty list."}, status=400)
    if len(raw_ids) > 100:
        return JsonResponse(
            {"detail": "draft_ids cannot contain more than 100 items."}, status=400
        )

    draft_ids = []
    for raw_id in raw_ids:
        try:
            draft_ids.append(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError):
            return JsonResponse({"detail": f"Invalid draft id: {raw_id}"}, status=400)

    existing_ids = list(
        CustomizationDraft.objects.filter(pk__in=draft_ids).values_list("pk", flat=True)
    )
    dispatch_print_generation(existing_ids)

    return JsonResponse(
        {
            "queued": [str(draft_id) for draft_id in existing_ids],
            "missing": [str(draft_id) for draft_id in draft_ids if draft_id not in existing_ids],
        },
        status=202,
    )
