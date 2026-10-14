from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Order


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "orders/list.html", {"orders": orders})
