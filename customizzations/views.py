from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import ProductCustomization


@login_required
def list_customizations(request):
    customizations = ProductCustomization.objects.filter(user=request.user).order_by("-created_at")
    return render(
        request,
        "customizzations/list.html",
        {"customizations": customizations},
    )
