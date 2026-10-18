import io
import json
import os
import shutil
import tempfile
from decimal import Decimal

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import CustomizationZone, Product, ProductView

from .models import CustomizationDraft


def png_bytes(size=(80, 40), color=(200, 30, 30, 255)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(name="art.png", size=(80, 40), color=(200, 30, 30, 255)):
    return SimpleUploadedFile(name, png_bytes(size, color), content_type="image/png")


def jpeg_bytes(size=(40, 80), orientation=6):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, (120, 60, 200))
    exif = Image.Exif()
    exif[0x0112] = orientation
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def jpeg_upload(name="photo.jpg", size=(40, 80), orientation=6):
    return SimpleUploadedFile(
        name,
        jpeg_bytes(size, orientation),
        content_type="image/jpeg",
    )


@override_settings(
    CUSTOMIZATION_PRINT_ASYNC=False,
    CUSTOMIZATION_PRINT_WEBHOOK_SECRET="test-secret",
)
class CustomizationFlowTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        media_override = override_settings(MEDIA_ROOT=self.media_root)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.user = get_user_model().objects.create_user(
            username="artist", password="s3cret-pass"
        )
        self.client.force_login(self.user)

        self.product = Product.objects.create(
            title="Classic Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )
        self.view = ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image=SimpleUploadedFile(
                "mockup.png",
                png_bytes((200, 200), (255, 255, 255, 255)),
                content_type="image/png",
            ),
            canvas_width_px=200,
            canvas_height_px=200,
        )
        self.zone = CustomizationZone.objects.create(
            product_view=self.view,
            name="Chest",
            x=50,
            y=50,
            width=100,
            height=100,
        )

    def configuration(self, views):
        return json.dumps({"views": views})

    def save_draft(self, views, files=None, draft=None):
        payload = {
            "product_id": self.product.pk,
            "configuration": self.configuration(views),
        }
        if draft is not None:
            payload["draft_id"] = str(draft.pk)
        payload.update(files or {})
        return self.client.post(reverse("customization:draft_save"), payload)

    def zone_payload(self, view, zone, **transform):
        return {
            "product_view_id": view.pk,
            "zones": [
                {
                    "zone_id": zone.pk,
                    "transform": {
                        "x": 50,
                        "y": 50,
                        "width": 100,
                        "height": 50,
                        "rotation": 15,
                        **transform,
                    },
                }
            ],
        }

    def trigger_webhook(self, draft_ids, token="test-secret"):
        return self.client.post(
            reverse("customization:order_paid_webhook"),
            data=json.dumps({"draft_ids": [str(draft_id) for draft_id in draft_ids]}),
            content_type="application/json",
            HTTP_X_WEBHOOK_TOKEN=token,
        )

    def test_editor_payload_includes_canvas_and_limits(self):
        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(response.status_code, 200)
        editor_payload = response.context["editor_payload"]
        self.assertEqual(editor_payload["views"][0]["canvas_width"], 200)
        self.assertEqual(
            editor_payload["max_image_pixels"],
            settings.CUSTOMIZATION_MAX_IMAGE_PIXELS,
        )
        self.assertEqual(editor_payload["views"][0]["zones"][0]["id"], self.zone.pk)

    def test_save_preview_cart_print_and_delete(self):
        response = self.save_draft(
            [self.zone_payload(self.view, self.zone)],
            {f"asset_{self.zone.pk}": upload()},
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(
            response.url, reverse("customization:draft_detail", args=[draft.pk])
        )
        self.assertTrue(draft.preview_webp_url)
        self.assertTrue(os.path.exists(draft.preview_webp_url.path))
        with Image.open(draft.preview_webp_url.path) as preview:
            self.assertEqual(preview.format, "WEBP")
        self.assertLessEqual(
            os.path.getsize(draft.preview_webp_url.path),
            settings.CUSTOMIZATION_PREVIEW_MAX_BYTES,
        )

        stored_zone = draft.configuration_json["views"][0]["zones"][0]
        self.assertEqual(stored_zone["transform"]["rotation"], 15.0)
        asset_path = stored_zone["asset_path"]
        self.assertTrue(
            asset_path.startswith(f"customization/drafts/{draft.pk}/assets/")
        )
        self.assertTrue(default_storage.exists(asset_path))

        detail = self.client.get(reverse("customization:draft_detail", args=[draft.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, draft.preview_url)

        listing = self.client.get(reverse("customization:list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, self.product.title)

        add_response = self.client.post(
            reverse("cart:add", args=[self.product.pk]),
            {"draft_id": str(draft.pk)},
        )
        self.assertRedirects(add_response, reverse("cart:detail"))
        line = self.client.session["cart"][f"{self.product.pk}:{draft.pk}"]
        self.assertEqual(line["quantity"], 1)

        cart_response = self.client.get(reverse("cart:detail"))
        self.assertEqual(cart_response.status_code, 200)
        self.assertContains(cart_response, draft.preview_url)

        webhook_response = self.trigger_webhook([draft.pk])
        self.assertEqual(webhook_response.status_code, 202)
        self.assertEqual(webhook_response.json()["queued"], [str(draft.pk)])

        draft.refresh_from_db()
        self.assertTrue(draft.print_file_url)
        self.assertTrue(os.path.exists(draft.print_file_url.path))
        with Image.open(draft.print_file_url.path) as print_image:
            self.assertEqual(print_image.format, "PNG")
            self.assertEqual(print_image.size, (200, 200))

        preview_path = draft.preview_webp_url.path
        print_path = draft.print_file_url.path
        delete_response = self.client.post(
            reverse("customization:draft_delete", args=[draft.pk])
        )
        self.assertRedirects(delete_response, reverse("customization:list"))
        self.assertFalse(CustomizationDraft.objects.filter(pk=draft.pk).exists())
        self.assertFalse(os.path.exists(preview_path))
        self.assertFalse(os.path.exists(print_path))
        self.assertFalse(default_storage.exists(asset_path))

    def test_replacing_an_image_removes_the_old_asset(self):
        self.save_draft(
            [self.zone_payload(self.view, self.zone)],
            {f"asset_{self.zone.pk}": upload()},
        )
        draft = CustomizationDraft.objects.get(user=self.user)
        first_asset = draft.configuration_json["views"][0]["zones"][0]["asset_path"]
        first_preview = draft.preview_webp_url.name

        response = self.save_draft(
            [self.zone_payload(self.view, self.zone, rotation=-30)],
            {f"asset_{self.zone.pk}": upload(color=(30, 180, 90, 255))},
            draft=draft,
        )
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()

        second_asset = draft.configuration_json["views"][0]["zones"][0]["asset_path"]
        self.assertNotEqual(first_asset, second_asset)
        self.assertFalse(default_storage.exists(first_asset))
        self.assertTrue(default_storage.exists(second_asset))
        self.assertNotEqual(first_preview, draft.preview_webp_url.name)
        self.assertFalse(default_storage.exists(first_preview))
        self.assertEqual(
            draft.configuration_json["views"][0]["zones"][0]["transform"]["rotation"],
            -30.0,
        )

    def test_multi_view_customization_produces_a_pdf(self):
        second_view = ProductView.objects.create(
            product=self.product,
            name="Back",
            sort_order=2,
            mockup_image=SimpleUploadedFile(
                "back.png",
                png_bytes((200, 200), (255, 255, 255, 255)),
                content_type="image/png",
            ),
            canvas_width_px=200,
            canvas_height_px=200,
        )
        second_zone = CustomizationZone.objects.create(
            product_view=second_view,
            name="Back print",
            x=25,
            y=25,
            width=150,
            height=150,
        )

        response = self.save_draft(
            [
                self.zone_payload(self.view, self.zone),
                self.zone_payload(second_view, second_zone),
            ],
            {
                f"asset_{self.zone.pk}": upload(),
                f"asset_{second_zone.pk}": upload(
                    size=(60, 60), color=(30, 30, 200, 255)
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(len(draft.configuration_json["views"]), 2)

        webhook_response = self.trigger_webhook([draft.pk])
        self.assertEqual(webhook_response.status_code, 202)
        draft.refresh_from_db()

        self.assertTrue(draft.print_file_url.name.endswith(".pdf"))
        with open(draft.print_file_url.path, "rb") as print_file:
            self.assertTrue(print_file.read(5).startswith(b"%PDF"))

    def test_invalid_webhook_token_is_rejected(self):
        response = self.trigger_webhook([], token="wrong")
        self.assertEqual(response.status_code, 403)

    def test_exif_oriented_upload_uses_displayed_dimensions(self):
        view_payload = self.zone_payload(self.view, self.zone)
        for key in ("width", "height"):
            del view_payload["zones"][0]["transform"][key]
        response = self.save_draft(
            [view_payload],
            {f"asset_{self.zone.pk}": jpeg_upload(size=(40, 80), orientation=6)},
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        stored_zone = draft.configuration_json["views"][0]["zones"][0]
        # A 40x80 JPEG tagged with orientation 6 is displayed as 80x40.
        self.assertEqual(stored_zone["natural_width"], 80)
        self.assertEqual(stored_zone["natural_height"], 40)
        self.assertEqual(stored_zone["transform"]["width"], 80)
        self.assertEqual(stored_zone["transform"]["height"], 40)

    def test_zone_default_rotation_is_used_when_transform_omits_it(self):
        self.zone.rotation = 30
        self.zone.save(update_fields=["rotation"])
        view_payload = self.zone_payload(self.view, self.zone)
        del view_payload["zones"][0]["transform"]["rotation"]

        response = self.save_draft(
            [view_payload], {f"asset_{self.zone.pk}": upload()}
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(
            draft.configuration_json["views"][0]["zones"][0]["transform"]["rotation"],
            30.0,
        )

    def test_unsupported_image_format_is_rejected(self):
        buffer = io.BytesIO()
        Image.new("RGB", (40, 40), (10, 120, 200)).save(buffer, format="GIF")
        unsupported = SimpleUploadedFile(
            "art.gif",
            buffer.getvalue(),
            content_type="image/gif",
        )

        response = self.save_draft(
            [self.zone_payload(self.view, self.zone)],
            {f"asset_{self.zone.pk}": unsupported},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())
        self.assertFalse(default_storage.exists("customization/drafts"))

    @override_settings(CUSTOMIZATION_MAX_IMAGE_PIXELS=1000)
    def test_upload_with_too_many_pixels_is_rejected(self):
        response = self.save_draft(
            [self.zone_payload(self.view, self.zone)],
            {f"asset_{self.zone.pk}": upload(size=(80, 40))},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    @override_settings(CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB=0)
    def test_total_upload_limit_is_enforced(self):
        response = self.save_draft(
            [self.zone_payload(self.view, self.zone)],
            {f"asset_{self.zone.pk}": upload()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    def test_asset_from_another_draft_is_rejected(self):
        other_draft = CustomizationDraft.objects.create(
            user=self.user, product=self.product
        )
        foreign_path = f"customization/drafts/{other_draft.pk}/assets/foreign.png"
        default_storage.save(foreign_path, SimpleUploadedFile("x.png", png_bytes()))
        self.addCleanup(default_storage.delete, foreign_path)

        view_payload = self.zone_payload(self.view, self.zone)
        view_payload["zones"][0]["asset_path"] = foreign_path
        response = self.save_draft([view_payload], {})
        self.assertEqual(response.status_code, 302)

        self.assertEqual(CustomizationDraft.objects.count(), 1)
        self.assertTrue(CustomizationDraft.objects.filter(pk=other_draft.pk).exists())

    def test_non_string_asset_path_is_rejected(self):
        view_payload = self.zone_payload(self.view, self.zone)
        view_payload["zones"][0]["asset_path"] = 123
        response = self.save_draft([view_payload], {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    def test_view_without_resolution_is_not_editable(self):
        product = Product.objects.create(
            title="Unprepared Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )
        empty_view = ProductView.objects.create(
            product=product,
            name="Front",
            sort_order=1,
        )
        CustomizationZone.objects.create(
            product_view=empty_view,
            name="Chest",
            x=50,
            y=50,
            width=100,
            height=100,
        )

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": product.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["editor_payload"]["views"], [])
        messages = [str(message) for message in response.context["messages"]]
        self.assertIn("This product has no customizable areas yet.", messages)

    def test_empty_configuration_is_rejected(self):
        response = self.save_draft([], {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())
        self.assertEqual(
            response.url,
            reverse("customization:editor", kwargs={"slug": self.product.slug}),
        )
