from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import CustomizationZoneForm, ProductCreateForm, ProductViewForm
from .models import Product


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("title")
    return render(request, "products/list.html", {"products": products})


@login_required
def create_product(request):
    """Staff quick-create flow: one product, its first view and one print area."""

    if not request.user.is_staff:
        raise PermissionDenied

    product_form = ProductCreateForm(request.POST or None, prefix="product")
    view_form = ProductViewForm(
        request.POST or None,
        request.FILES or None,
        prefix="view",
    )
    zone_form = CustomizationZoneForm(request.POST or None, prefix="zone")
    zone_form.instance.product_view = view_form.instance

    if request.method == "POST":
        if product_form.is_valid() and view_form.is_valid() and zone_form.is_valid():
            with transaction.atomic():
                product = product_form.save()
                product_view = view_form.save(commit=False)
                product_view.product = product
                product_view.save()

                zone = zone_form.save(commit=False)
                zone.product_view = product_view
                zone.save()

            messages.success(
                request,
                f'"{product.title}" was created. Add more views or print areas in the Admin.',
            )
            return redirect("products:list")

    return render(
        request,
        "products/create_product.html",
        {
            "product_form": product_form,
            "view_form": view_form,
            "zone_form": zone_form,
            "max_upload_mb": settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        },
    )
