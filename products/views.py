from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    DEFAULT_AREA_RATIOS,
    MAX_PRODUCT_VIEWS,
    PrintAreaForm,
    ProductCreateForm,
    ProductViewFormSet,
)
from .models import Product, ProductView


def _wants_json(request):
    return (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )


def _collect_form_errors(form, errors, non_field_errors):
    for field_name, field_errors in form.errors.items():
        messages_list = [str(error) for error in field_errors]
        if field_name == "__all__":
            non_field_errors.extend(messages_list)
        else:
            errors[form.add_prefix(field_name)] = messages_list


def _initial_face_name(index):
    return ("Front", "Back")[index] if index < 2 else f"Side {index + 1}"


def _zone_initial(name):
    return {"name": name, **DEFAULT_AREA_RATIOS}


def _attach_gallery_views(products):
    """Expose the ordered, non-empty side mockups used by the catalogue cards.

    ``views`` is prefetched by ``product_list`` so this helper only reads from
    the per-product cache and never issues an extra query.
    """

    eager_gallery_assigned = False
    for product in products:
        product.gallery_views = [
            view for view in product.views.all() if view.mockup_image
        ]
        for index, view in enumerate(product.gallery_views):
            view.gallery_eager = not eager_gallery_assigned and index == 0
            if view.gallery_eager:
                eager_gallery_assigned = True
    return products


def product_list(request):
    products = list(
        Product.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch(
                "views",
                queryset=ProductView.objects.order_by("sort_order", "id"),
            )
        )
        .order_by("title")
    )
    _attach_gallery_views(products)
    return render(request, "products/list.html", {"products": products})


@login_required
@require_POST
def deactivate_product(request, slug):
    """Staff-only soft delete: hide a product without removing its data."""

    if not request.user.is_staff:
        raise PermissionDenied

    product = get_object_or_404(Product, slug=slug)
    if product.is_active:
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        messages.success(
            request,
            f'"{product.title}" was deactivated and is no longer visible in the shop.',
        )
    else:
        messages.success(request, f'"{product.title}" is already inactive.')

    return redirect("products:list")


@login_required
def create_product(request):
    """Staff wizard: product details, one or more sides and one zone per side."""

    if not request.user.is_staff:
        raise PermissionDenied

    is_post = request.method == "POST"
    product_form = ProductCreateForm(request.POST or None, prefix="product")
    formset_kwargs = {
        "instance": Product(),
        "prefix": "views",
        "data": request.POST or None,
        "files": request.FILES or None,
    }
    if not is_post:
        formset_kwargs["initial"] = [{"name": _initial_face_name(0)}]
    view_formset = ProductViewFormSet(**formset_kwargs)

    zone_forms = []
    for index in range(len(view_formset.forms)):
        if is_post:
            zone_forms.append(PrintAreaForm(request.POST, prefix=f"zone-{index}"))
        else:
            face_name = (
                view_formset.forms[index].initial.get("name")
                or _initial_face_name(index)
            )
            zone_forms.append(
                PrintAreaForm(
                    prefix=f"zone-{index}",
                    initial=_zone_initial(f"{face_name} artwork"),
                )
            )

    product_valid = product_form.is_valid()
    views_valid = view_formset.is_valid()
    zones_valid = True

    if is_post:
        for index, view_form in enumerate(view_formset.forms):
            if not view_form.has_changed():
                # Empty extra/min-num forms are reported by the formset itself.
                continue
            zone_form = zone_forms[index]
            if view_form.is_valid():
                zone_form.canvas_width = view_form.instance.canvas_width_px
                zone_form.canvas_height = view_form.instance.canvas_height_px
            if not zone_form.is_valid():
                zones_valid = False

    if is_post and product_valid and views_valid and zones_valid:
        with transaction.atomic():
            product = product_form.save()
            saved_sides = 0

            for index, view_form in enumerate(view_formset.forms):
                if not view_form.has_changed():
                    continue
                product_view = view_form.save(commit=False)
                product_view.product = product
                saved_sides += 1
                product_view.sort_order = saved_sides
                product_view.save()

                zone_forms[index].build_zone(product_view).save()

        messages.success(
            request,
            f'"{product.title}" was created with {saved_sides} '
            f'{"side" if saved_sides == 1 else "sides"} and one printable area per side.',
        )
        if _wants_json(request):
            return JsonResponse(
                {"ok": True, "redirect_url": reverse("products:list")}
            )
        return redirect("products:list")

    active_step = 1
    if is_post and product_form.errors:
        active_step = 1
    elif is_post:
        active_step = 2

    active_face = 0
    if is_post:
        for index, view_form in enumerate(view_formset.forms):
            if view_form.errors or (
                index < len(zone_forms) and zone_forms[index].errors
            ):
                active_face = index
                break

    if is_post and _wants_json(request):
        errors = {}
        non_field_errors = []
        _collect_form_errors(product_form, errors, non_field_errors)
        for view_form in view_formset.forms:
            _collect_form_errors(view_form, errors, non_field_errors)
        for zone_form in zone_forms:
            _collect_form_errors(zone_form, errors, non_field_errors)
        non_field_errors.extend(
            str(error) for error in view_formset.non_form_errors()
        )
        return JsonResponse(
            {
                "ok": False,
                "step": active_step,
                "face_index": active_face,
                "message": "Please correct the highlighted fields and try again.",
                "errors": errors,
                "non_field_errors": list(dict.fromkeys(non_field_errors)),
            },
            status=422,
        )

    face_rows = [
        {
            "index": index,
            "view_form": view_form,
            "zone_form": zone_forms[index],
            "is_active": index == active_face,
        }
        for index, view_form in enumerate(view_formset.forms)
    ]

    return render(
        request,
        "products/create_product.html",
        {
            "product_form": product_form,
            "view_formset": view_formset,
            "face_rows": face_rows,
            "empty_zone_form": PrintAreaForm(
                prefix="zone-__prefix__",
                initial=_zone_initial(""),
            ),
            "active_step": active_step,
            "active_face": active_face,
            "max_views": MAX_PRODUCT_VIEWS,
            "max_upload_mb": settings.CUSTOMIZATION_MAX_UPLOAD_MB,
            "mockup_upload_limit_mb": settings.PRODUCT_MOCKUP_MAX_UPLOAD_MB,
            "has_errors": is_post
            and bool(
                product_form.errors
                or view_formset.errors
                or view_formset.non_form_errors()
                or any(zone.errors for zone in zone_forms)
            ),
        },
    )
