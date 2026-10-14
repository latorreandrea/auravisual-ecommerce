from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import ShippingAddress
from orders.models import Order


@login_required
def profile(request):
    addresses = ShippingAddress.objects.filter(user=request.user).order_by("-created_at")
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    context = {
        "addresses": addresses,
        "orders": orders,
    }
    return render(request, "accounts/profile.html", context)
