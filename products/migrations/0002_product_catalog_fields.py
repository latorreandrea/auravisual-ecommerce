from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    used = set()
    for product in Product.objects.order_by("pk"):
        base = slugify(product.title)[:120] or "product"
        slug = base
        suffix = 2
        while slug in used:
            slug = f"{base}-{suffix}"
            suffix += 1
        used.add(slug)
        Product.objects.filter(pk=product.pk).update(slug=slug)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="product",
            old_name="name",
            new_name="title",
        ),
        migrations.RenameField(
            model_name="product",
            old_name="price",
            new_name="base_price",
        ),
        migrations.AddField(
            model_name="product",
            name="slug",
            field=models.SlugField(blank=True, default="", max_length=140),
            preserve_default=False,
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="slug",
            field=models.SlugField(blank=True, max_length=140, unique=True),
        ),
        migrations.AlterModelOptions(
            name="product",
            options={"ordering": ("title",)},
        ),
    ]
