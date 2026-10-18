from django.shortcuts import render

from .models import Product


def product_list(request):
    products = Product.objects.filter(is_active=True).order_by("title")
    return render(request, "products/list.html", {"products": products})
