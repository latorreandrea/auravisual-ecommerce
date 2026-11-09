from django.urls import path

from .views import checkout, order_list

app_name = "orders"

urlpatterns = [
    path("checkout/", checkout, name="checkout"),
    path("", order_list, name="list"),
]
