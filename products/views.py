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

from auravisual_ecommerce.pagination import paginate
from promotions.models import Promotion
from promotions.services import attach_promotion_badges

from .forms import (
    DEFAULT_AREA_RATIOS,
    MAX_PRODUCT_VIEWS,
    SideAreaForm,
    ProductCreateForm,
    ProductEditForm,
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
    """The catalogue, with the staff actions grafted on for the shopkeeper.

    Customers always get the published products, whatever the query string says.
    Staff can flip the same page to the hidden products (``?status=hidden``) and
    get edit/visibility shortcuts on every card, so a deactivated product can be
    fixed and published again without leaving the shop.
    """

    is_staff = request.user.is_staff
    show_hidden = is_staff and request.GET.get("status") == "hidden"

    if show_hidden:
        queryset = Product.objects.filter(is_active=False)
    else:
        queryset = Product.objects.filter(is_active=True)
    queryset = queryset.prefetch_related(
        Prefetch(
            "views",
            queryset=ProductView.objects.order_by("sort_order", "id"),
        )
    ).order_by("title")

    # Pagination runs in SQL (one COUNT plus a LIMIT/OFFSET page), so the
    # catalogue never loads the whole table: see auravisual_ecommerce.pagination.
    page_obj, page_context = paginate(request, queryset, settings.PRODUCTS_PAGE_SIZE)
    products = _attach_gallery_views(list(page_obj.object_list))
    # One query for every promotion on the page: cards show the best break.
    attach_promotion_badges(products)

    context = {
        "products": products,
        "total_products": page_obj.paginator.count,
        **page_context,
    }
    if is_staff:
        # The staff map is attached in place (one query for the whole page).
        _attach_staff_promotions(products)
        context.update(
            {
                "show_hidden": show_hidden,
                "hidden_product_count": Product.objects.filter(
                    is_active=False
                ).count(),
            }
        )
    return render(request, "products/list.html", context)


def _attach_staff_promotions(products):
    """Attach the promotion of each card, one query for the whole page.

    ``attach_promotion_badges`` only exposes the badge text of the best *active*
    promotion; the staff actions also need the record (and a link) for a product
    whose promotion is inactive, so the map is built here instead.
    """

    promotions_by_product = {}
    for promotion in Promotion.objects.filter(
        product_id__in=[product.pk for product in products]
    ).order_by("pk"):
        current = promotions_by_product.get(promotion.product_id)
        if current is None or (promotion.is_active and not current.is_active):
            promotions_by_product[promotion.product_id] = promotion

    for product in products:
        product.staff_promotion = promotions_by_product.get(product.pk)
    return products


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
def edit_product(request, slug):
    """Staff page: edit the product details that are not part of the wizard.

    Sides and printable areas stay in the wizard (on creation) and in the Django
    admin, so this page only touches the fields a shopkeeper changes day to day:
    title, description, price, stock and visibility.
    """

    if not request.user.is_staff:
        raise PermissionDenied

    product = get_object_or_404(
        Product.objects.prefetch_related("views", "promotions__tiers"),
        slug=slug,
    )

    if request.method == "POST":
        form = ProductEditForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, f'"{product.title}" was updated.')
            return redirect("products:list")
    else:
        form = ProductEditForm(instance=product)

    promotions = list(product.promotions.all())
    promotion = next(
        (candidate for candidate in promotions if candidate.is_active),
        promotions[0] if promotions else None,
    )

    return render(
        request,
        "products/edit_product.html",
        {
            "product": product,
            "form": form,
            "promotion": promotion,
            "side_count": len(product.views.all()),
        },
    )


@login_required
def create_product(request):
    """Staff wizard: product details, one or more sides and their print areas."""

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

    area_forms = []
    for index in range(len(view_formset.forms)):
        if is_post:
            area_forms.append(SideAreaForm(request.POST, prefix=f"area-{index}"))
        else:
            area_forms.append(
                SideAreaForm(prefix=f"area-{index}", initial=DEFAULT_AREA_RATIOS)
            )

    product_valid = product_form.is_valid()
    views_valid = view_formset.is_valid()
    areas_valid = True
    customizable_sides = 0

    if is_post:
        for index, view_form in enumerate(view_formset.forms):
            if not view_form.has_changed():
                # Empty extra/min-num forms are reported by the formset itself.
                continue
            area_form = area_forms[index]
            if view_form.is_valid():
                area_form.canvas_width = view_form.instance.canvas_width_px
                area_form.canvas_height = view_form.instance.canvas_height_px
            if not area_form.is_valid():
                areas_valid = False
            elif area_form.cleaned_data.get("customizable"):
                customizable_sides += 1

        if product_valid and views_valid and areas_valid and not customizable_sides:
            # A product with only fixed sides can never be customized: reject it
            # here instead of shipping a product whose editor is empty.
            areas_valid = False
            area_forms[0].add_error(
                None,
                "Mark at least one side as customizable so customers can "
                "personalize the product.",
            )

    if is_post and product_valid and views_valid and areas_valid:
        with transaction.atomic():
            product = product_form.save()
            saved_sides = 0
            customizable_sides = 0

            for index, view_form in enumerate(view_formset.forms):
                if not view_form.has_changed():
                    continue
                product_view = view_form.save(commit=False)
                product_view.product = product
                saved_sides += 1
                product_view.sort_order = saved_sides
                # The drawn area (or the fixed-side flag) lives on the side.
                area_forms[index].apply_to(product_view)
                product_view.save()
                if product_view.is_customizable:
                    customizable_sides += 1

        messages.success(
            request,
            f'"{product.title}" was created with {saved_sides} '
            f'{"side" if saved_sides == 1 else "sides"} '
            f"({customizable_sides} customizable).",
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
                index < len(area_forms) and area_forms[index].errors
            ):
                active_face = index
                break

    if is_post and _wants_json(request):
        errors = {}
        non_field_errors = []
        _collect_form_errors(product_form, errors, non_field_errors)
        for view_form in view_formset.forms:
            _collect_form_errors(view_form, errors, non_field_errors)
        for area_form in area_forms:
            _collect_form_errors(area_form, errors, non_field_errors)
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
            "area_form": area_forms[index],
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
            "empty_area_form": SideAreaForm(
                prefix="area-__prefix__",
                initial=DEFAULT_AREA_RATIOS,
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
                or any(area.errors for area in area_forms)
            ),
        },
    )
