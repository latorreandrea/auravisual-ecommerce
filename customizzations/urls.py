from django.urls import path

from .views import list_customizations

app_name = "customizzations"

urlpatterns = [
    path("", list_customizations, name="list"),
]
