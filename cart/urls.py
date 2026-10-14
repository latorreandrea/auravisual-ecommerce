from django.urls import path

from .views import add_to_cart, cart_detail, clear_cart, remove_from_cart

app_name = "cart"

urlpatterns = [
    path("", cart_detail, name="detail"),
    path("add/<int:product_id>/", add_to_cart, name="add"),
    path("remove/<int:product_id>/", remove_from_cart, name="remove"),
    path("clear/", clear_cart, name="clear"),
]
