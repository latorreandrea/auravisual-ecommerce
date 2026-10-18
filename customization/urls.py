from django.urls import path

from . import views

app_name = "customization"

urlpatterns = [
    path("", views.draft_list, name="list"),
    path("product/<slug:slug>/", views.editor, name="editor"),
    path("drafts/save/", views.draft_save, name="draft_save"),
    path("drafts/<uuid:draft_id>/", views.draft_detail, name="draft_detail"),
    path("drafts/<uuid:draft_id>/delete/", views.draft_delete, name="draft_delete"),
    path("drafts/<uuid:draft_id>/payload/", views.draft_payload, name="draft_payload"),
    path("webhooks/order-paid/", views.order_paid_webhook, name="order_paid_webhook"),
]
