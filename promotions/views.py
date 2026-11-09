"""Staff pages for the quantity promotions.

These views mirror what the Django admin does for the same models and reuse
``promotions.forms``, so the ladder rules cannot drift between the two surfaces.
Every view is staff-only, guarded the same way as ``products.views``.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.models import Product

from .forms import PromotionForm, PromotionTierStoreFormSet
from .models import Promotion

STATUS_CHOICES = (
    ("all", "All promotions"),
    ("active", "Active"),
    ("inactive", "Inactive"),
)


def _require_staff(user):
    if not user.is_staff:
        raise PermissionDenied


def _ladder_rows(promotion):
    """Price breaks plus the saving each one gives against the base price."""

    base_price = promotion.product.base_price
    rows = []
    for tier in promotion.tiers.all():
        gross = base_price * tier.quantity
        saving = gross - tier.price
        rows.append(
            {
                "tier": tier,
                "gross": gross,
                "saving": saving,
                "saving_percent": int(round(saving / gross * 100)) if gross else 0,
            }
        )
    return rows


def _best_tier(promotion):
    tiers = list(promotion.tiers.all())
    return min(tiers, key=lambda tier: tier.unit_price) if tiers else None


def _product_prefill(request):
    """Initial data for ``?product=<id>``, used by the staff dashboard."""

    raw_product_id = request.GET.get("product")
    if not raw_product_id:
        return {}
    try:
        product = Product.objects.get(pk=int(raw_product_id))
    except (TypeError, ValueError, Product.DoesNotExist):
        return {}
    return {"product": product.pk, "name": f"{product.title} bundle"}


@login_required
def promotion_list(request):
    _require_staff(request.user)

    query = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or "all"
    promotions = Promotion.objects.select_related("product").prefetch_related("tiers")
    if query:
        promotions = promotions.filter(
            Q(name__icontains=query) | Q(product__title__icontains=query)
        )
    if status == "active":
        promotions = promotions.filter(is_active=True)
    elif status == "inactive":
        promotions = promotions.filter(is_active=False)
    else:
        status = "all"

    promotions = list(promotions)
    for promotion in promotions:
        promotion.best_tier = _best_tier(promotion)

    return render(
        request,
        "promotions/list.html",
        {
            "promotions": promotions,
            "query": query,
            "status": status,
            "status_choices": STATUS_CHOICES,
            "total_promotions": Promotion.objects.count(),
            "active_promotions": Promotion.objects.filter(is_active=True).count(),
        },
    )


def _edit_promotion(request, promotion, template, initial=None):
    """Render and save the promotion form plus its ladder of price breaks."""

    if request.method == "POST":
        form = PromotionForm(request.POST, instance=promotion)
        # ``is_valid()`` copies the cleaned product onto the instance, which is
        # what the ladder validation compares every break against.
        form_valid = form.is_valid()
        formset = PromotionTierStoreFormSet(
            request.POST,
            instance=form.instance,
            prefix="tiers",
        )
        formset_valid = formset.is_valid()
        if form_valid and formset_valid:
            with transaction.atomic():
                promotion = form.save()
                formset.instance = promotion
                formset.save()
            messages.success(request, f'"{promotion.name}" was saved.')
            return redirect("promotions:detail", pk=promotion.pk)
        messages.error(request, "Please correct the highlighted fields and try again.")
    else:
        form = PromotionForm(instance=promotion, initial=initial)
        formset = PromotionTierStoreFormSet(instance=promotion, prefix="tiers")

    has_ladder = bool(promotion.pk)
    return render(
        request,
        template,
        {
            "promotion": promotion,
            "form": form,
            "tier_formset": formset,
            "ladder_rows": _ladder_rows(promotion) if has_ladder else [],
            "best_tier": _best_tier(promotion) if has_ladder else None,
        },
    )


@login_required
def promotion_create(request):
    _require_staff(request.user)
    return _edit_promotion(
        request,
        Promotion(),
        "promotions/create.html",
        initial=_product_prefill(request),
    )


@login_required
def promotion_detail(request, pk):
    _require_staff(request.user)
    promotion = get_object_or_404(
        Promotion.objects.select_related("product"),
        pk=pk,
    )
    return _edit_promotion(request, promotion, "promotions/detail.html")


@login_required
@require_POST
def promotion_delete(request, pk):
    _require_staff(request.user)
    promotion = get_object_or_404(Promotion.objects.select_related("product"), pk=pk)
    name = promotion.name
    product_title = promotion.product.title
    promotion.delete()
    messages.success(
        request,
        f'"{name}" was deleted: "{product_title}" is back to its base price.',
    )
    return redirect("promotions:list")
