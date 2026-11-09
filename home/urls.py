from django.urls import path

from .views import index, staff_dashboard

app_name = "home"

urlpatterns = [
    path("", index, name="index"),
    path("staff/", staff_dashboard, name="staff"),
]
