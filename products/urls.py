from django.urls import path

from .views import create_product, product_list

app_name = "products"

urlpatterns = [
    path("create/", create_product, name="create"),
    path("", product_list, name="list"),
]
