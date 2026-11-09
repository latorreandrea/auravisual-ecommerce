from django.urls import path

from .views import promotion_create, promotion_delete, promotion_detail, promotion_list

app_name = "promotions"

urlpatterns = [
    path("", promotion_list, name="list"),
    path("create/", promotion_create, name="create"),
    path("<int:pk>/", promotion_detail, name="detail"),
    path("<int:pk>/delete/", promotion_delete, name="delete"),
]
