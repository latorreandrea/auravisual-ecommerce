"""Delete generated customization files together with their draft."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import CustomizationDraft

GENERATED_FIELDS = ("preview_webp_url", "print_file_url")


def _delete(storage, name):
    if not name:
        return
    try:
        if storage.exists(name):
            storage.delete(name)
    except (OSError, ValueError):
        pass


@receiver(pre_save, sender=CustomizationDraft)
def remember_replaced_generated_files(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    for field_name in GENERATED_FIELDS:
        old_name = getattr(previous, field_name).name
        new_name = getattr(instance, field_name).name
        if old_name and old_name != new_name:
            setattr(instance, f"_old_{field_name}_name", old_name)


@receiver(post_save, sender=CustomizationDraft)
def delete_replaced_generated_files(sender, instance, **kwargs):
    for field_name in GENERATED_FIELDS:
        attribute = f"_old_{field_name}_name"
        old_name = getattr(instance, attribute, None)
        if old_name:
            _delete(CustomizationDraft._meta.get_field(field_name).storage, old_name)
            delattr(instance, attribute)


@receiver(post_delete, sender=CustomizationDraft)
def delete_draft_files(sender, instance, **kwargs):
    for field_name in GENERATED_FIELDS:
        field_file = getattr(instance, field_name)
        _delete(field_file.storage, field_file.name)

    asset_storage = CustomizationDraft._meta.get_field("preview_webp_url").storage
    for path in instance.asset_paths():
        _delete(asset_storage, path)
