"""Keep media storage in sync when product mockups are replaced or removed."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import ProductView

FILE_FIELDS = ("mockup_image", "overlay_texture")


def _delete_file(field, name):
    if not name:
        return
    storage = field.storage
    try:
        if storage.exists(name):
            storage.delete(name)
    except (OSError, ValueError):
        # Storage cleanup must never break a model save/delete.
        pass


@receiver(pre_save, sender=ProductView)
def remember_replaced_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    for field_name in FILE_FIELDS:
        old_name = getattr(previous, field_name).name
        new_name = getattr(instance, field_name).name
        if old_name and old_name != new_name:
            setattr(instance, f"_old_{field_name}_name", old_name)


@receiver(post_save, sender=ProductView)
def delete_replaced_files(sender, instance, **kwargs):
    for field_name in FILE_FIELDS:
        attribute = f"_old_{field_name}_name"
        old_name = getattr(instance, attribute, None)
        if old_name:
            _delete_file(ProductView._meta.get_field(field_name), old_name)
            delattr(instance, attribute)


@receiver(post_delete, sender=ProductView)
def delete_files_on_delete(sender, instance, **kwargs):
    for field_name in FILE_FIELDS:
        _delete_file(
            ProductView._meta.get_field(field_name),
            getattr(instance, field_name).name,
        )
