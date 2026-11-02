import io
import json
import os
import shutil
import tempfile
import zipfile
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from products.models import Product, ProductView

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
        self.view = self.make_view(name="Front", sort_order=1, size=(200, 200))

    def make_view(self, name, sort_order, size=(200, 200), customizable=True):
        view = ProductView.objects.create(
            product=self.product,
            name=name,
            sort_order=sort_order,
            mockup_image=SimpleUploadedFile(
                f"{name.lower()}-mockup.png",
                png_bytes(size, (255, 255, 255, 255)),
                content_type="image/png",
            ),
            canvas_width_px=size[0],
            canvas_height_px=size[1],
        )
        if customizable:
            view.print_x = size[0] * 0.25
            view.print_y = size[1] * 0.25
            view.print_width = size[0] * 0.5
            view.print_height = size[1] * 0.5
            view.save()
        return view

    def configuration(self, views):
        return json.dumps({"views": views})

    def save_draft(self, views, files=None, draft=None, name=None):
        payload = {
            "product_id": self.product.pk,
            "configuration": self.configuration(views),
        }
        if draft is not None:
            payload["draft_id"] = str(draft.pk)
        if name is not None:
            payload["name"] = name
        payload.update(files or {})
        return self.client.post(reverse("customization:draft_save"), payload)

    def view_payload(self, view, **transform):
        area = view.print_area
        return {
            "product_view_id": view.pk,
            "image": {
                "transform": {
                    "x": area.x,
                    "y": area.y,
                    "width": area.width,
                    "height": area.height / 2,
                    "rotation": 15,
                    **transform,
                },
            },
        }

    def trigger_webhook(self, draft_ids, token="test-secret"):
        return self.client.post(
            reverse("customization:order_paid_webhook"),
            data=json.dumps({"draft_ids": [str(draft_id) for draft_id in draft_ids]}),
            content_type="application/json",
            HTTP_X_WEBHOOK_TOKEN=token,
        )

    def test_editor_payload_includes_print_area_and_limits(self):
        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, 200)
        editor_payload = response.context["editor_payload"]
        payload_view = editor_payload["views"][0]
        self.assertEqual(payload_view["id"], self.view.pk)
        self.assertEqual(payload_view["canvas_width"], 200)
        self.assertEqual(payload_view["print_area"]["width"], 100.0)
        self.assertEqual(payload_view["print_area"]["height"], 100.0)
        self.assertTrue(payload_view["print_area"]["allow_scaling"])
        self.assertNotIn("zones", payload_view)
        self.assertEqual(
            editor_payload["max_image_pixels"],
            settings.CUSTOMIZATION_MAX_IMAGE_PIXELS,
        )

    def test_fixed_sides_are_not_offered_in_the_editor(self):
        fixed = self.make_view(
            name="Inside", sort_order=2, size=(200, 200), customizable=False
        )

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug})
        )
        names = [view["name"] for view in response.context["editor_payload"]["views"]]

        self.assertEqual(names, ["Front"])
        self.assertNotIn(fixed.name, names)

    def test_editor_warns_when_no_side_is_customizable(self):
        product = Product.objects.create(
            title="Plain Mug",
            base_price=Decimal("10.00"),
            stock_quantity=3,
        )
        ProductView.objects.create(
            product=product,
            name="Front",
            sort_order=1,
            mockup_image="products/mockups/front.webp",
            canvas_width_px=200,
            canvas_height_px=200,
        )

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": product.slug})
        )
        messages = [str(message) for message in response.context["messages"]]

        self.assertEqual(response.context["editor_payload"]["views"], [])
        self.assertIn(
            '"Plain Mug" has no customizable sides yet: the product is printed '
            "exactly as it is shown.",
            messages,
        )

    def test_save_preview_cart_print_and_delete(self):
        response = self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": upload()},
            name="Summer tee",
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(
            response.url, reverse("customization:draft_detail", args=[draft.pk])
        )
        self.assertEqual(draft.name, "Summer tee")
        self.assertEqual(draft.display_name, "Summer tee")
        self.assertTrue(draft.preview_webp_url)
        with Image.open(draft.preview_webp_url.path) as preview:
            self.assertEqual(preview.format, "WEBP")
            self.assertEqual(preview.size, (200, 200))
        self.assertLessEqual(
            os.path.getsize(draft.preview_webp_url.path),
            settings.CUSTOMIZATION_PREVIEW_MAX_BYTES,
        )

        stored_image = draft.configuration_json["views"][0]["image"]
        self.assertEqual(stored_image["transform"]["rotation"], 15.0)
        asset_path = stored_image["asset_path"]
        self.assertTrue(
            asset_path.startswith(f"customization/drafts/{draft.pk}/assets/")
        )
        self.assertTrue(default_storage.exists(asset_path))

        detail = self.client.get(reverse("customization:draft_detail", args=[draft.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, draft.preview_url)
        self.assertContains(detail, "Summer tee")

        listing = self.client.get(reverse("customization:list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "Summer tee")

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
        self.assertTrue(draft.print_file_url.name.endswith(".zip"))
        with zipfile.ZipFile(draft.print_file_url.path) as archive:
            self.assertEqual(archive.namelist(), ["Front.png"])
            with Image.open(io.BytesIO(archive.read("Front.png"))) as printed:
                self.assertEqual(printed.format, "PNG")
                self.assertEqual(printed.size, (200, 200))

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

    def test_project_without_name_falls_back_to_the_product_and_date(self):
        self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": upload()},
        )
        draft = CustomizationDraft.objects.get(user=self.user)

        self.assertEqual(draft.name, "")
        self.assertIn(self.product.title, draft.display_name)
        self.assertNotEqual(draft.display_name, self.product.title)

    def test_replacing_an_image_removes_the_old_asset(self):
        self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": upload()},
        )
        draft = CustomizationDraft.objects.get(user=self.user)
        first_asset = draft.configuration_json["views"][0]["image"]["asset_path"]
        first_preview = draft.preview_webp_url.name

        response = self.save_draft(
            [self.view_payload(self.view, rotation=-30)],
            {f"asset_{self.view.pk}": upload(color=(30, 180, 90, 255))},
            draft=draft,
        )
        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()

        second_asset = draft.configuration_json["views"][0]["image"]["asset_path"]
        self.assertNotEqual(first_asset, second_asset)
        self.assertFalse(default_storage.exists(first_asset))
        self.assertTrue(default_storage.exists(second_asset))
        self.assertNotEqual(first_preview, draft.preview_webp_url.name)
        self.assertFalse(default_storage.exists(first_preview))
        self.assertEqual(
            draft.configuration_json["views"][0]["image"]["transform"]["rotation"],
            -30.0,
        )

    def test_every_side_gets_one_png_in_the_zip_archive(self):
        back = self.make_view(name="Back", sort_order=2, size=(200, 120))
        fixed = self.make_view(
            name="Inside", sort_order=3, size=(120, 120), customizable=False
        )

        response = self.save_draft(
            [self.view_payload(self.view), self.view_payload(back)],
            {
                f"asset_{self.view.pk}": upload(),
                f"asset_{back.pk}": upload(size=(60, 60), color=(30, 30, 200, 255)),
            },
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(len(draft.configuration_json["views"]), 2)

        webhook_response = self.trigger_webhook([draft.pk])
        self.assertEqual(webhook_response.status_code, 202)
        draft.refresh_from_db()

        with zipfile.ZipFile(draft.print_file_url.path) as archive:
            self.assertEqual(archive.namelist(), ["Front.png", "Back.png", "Inside.png"])
            sizes = {}
            for name in archive.namelist():
                with Image.open(io.BytesIO(archive.read(name))) as printed:
                    self.assertEqual(printed.format, "PNG")
                    sizes[name] = printed.size

        self.assertEqual(sizes["Front.png"], (200, 200))
        self.assertEqual(sizes["Back.png"], (200, 120))
        self.assertEqual(sizes["Inside.png"], (120, 120))
        self.assertTrue(fixed.is_customizable is False)

    def test_preview_uses_the_first_customized_side(self):
        back = self.make_view(name="Back", sort_order=2, size=(120, 120))

        self.save_draft(
            [self.view_payload(back)],
            {f"asset_{back.pk}": upload(size=(60, 60))},
        )
        draft = CustomizationDraft.objects.get(user=self.user)

        with Image.open(draft.preview_webp_url.path) as preview:
            self.assertEqual(preview.size, (120, 120))

    def test_preview_keeps_transparency_while_print_output_stays_flat(self):
        transparent = ProductView.objects.create(
            product=self.product,
            name="Cut-out",
            sort_order=2,
            mockup_image=SimpleUploadedFile(
                "cut-out-mockup.png",
                png_bytes((200, 200), (0, 0, 0, 0)),
                content_type="image/png",
            ),
            canvas_width_px=200,
            canvas_height_px=200,
            print_x=50,
            print_y=50,
            print_width=100,
            print_height=100,
        )

        self.save_draft(
            [self.view_payload(transparent)],
            {f"asset_{transparent.pk}": upload()},
        )
        draft = CustomizationDraft.objects.get(user=self.user)

        # The preview keeps the alpha channel: workspace and catalogue cards must
        # show the cut-out mockup, not a white rectangle around it.
        with Image.open(draft.preview_webp_url.path) as preview:
            self.assertEqual(preview.format, "WEBP")
            self.assertEqual(preview.mode, "RGBA")
            self.assertEqual(preview.getpixel((0, 0))[3], 0)

        # The print archive is still flattened on white for the printing service.
        response = self.trigger_webhook([draft.pk])
        self.assertEqual(response.status_code, 202)
        draft.refresh_from_db()

        with zipfile.ZipFile(draft.print_file_url.path) as archive:
            with Image.open(io.BytesIO(archive.read("Cut-out.png"))) as printed:
                self.assertEqual(printed.mode, "RGB")
                self.assertEqual(printed.getpixel((0, 0)), (255, 255, 255))

    def test_invalid_webhook_token_is_rejected(self):
        response = self.trigger_webhook([], token="wrong")
        self.assertEqual(response.status_code, 403)

    def test_exif_oriented_upload_uses_displayed_dimensions(self):
        payload = self.view_payload(self.view)
        for key in ("width", "height"):
            del payload["image"]["transform"][key]

        response = self.save_draft(
            [payload],
            {f"asset_{self.view.pk}": jpeg_upload(size=(40, 80), orientation=6)},
        )
        self.assertEqual(response.status_code, 302)

        draft = CustomizationDraft.objects.get(user=self.user)
        image = draft.configuration_json["views"][0]["image"]
        self.assertEqual(image["natural_width"], 80)
        self.assertEqual(image["natural_height"], 40)

    def test_side_default_rotation_is_used_when_transform_omits_it(self):
        self.view.rotation = 30
        self.view.save(update_fields=["rotation"])
        payload = self.view_payload(self.view)
        del payload["image"]["transform"]["rotation"]

        self.save_draft([payload], {f"asset_{self.view.pk}": upload()})

        draft = CustomizationDraft.objects.get(user=self.user)
        self.assertEqual(
            draft.configuration_json["views"][0]["image"]["transform"]["rotation"],
            30.0,
        )

    def test_transform_is_clamped_inside_the_print_area(self):
        payload = self.view_payload(self.view, x=-500, y=-500, width=5000, height=5000)

        self.save_draft([payload], {f"asset_{self.view.pk}": upload()})

        draft = CustomizationDraft.objects.get(user=self.user)
        transform = draft.configuration_json["views"][0]["image"]["transform"]
        # The editor allows a 2x zoom, but the centre must stay inside the area.
        self.assertLessEqual(transform["width"], 200)
        self.assertLessEqual(transform["height"], 200)
        center_x = transform["x"] + transform["width"] / 2
        center_y = transform["y"] + transform["height"] / 2
        self.assertGreaterEqual(center_x, 50)
        self.assertLessEqual(center_x, 150)
        self.assertGreaterEqual(center_y, 50)
        self.assertLessEqual(center_y, 150)

    def test_unsupported_image_format_is_rejected(self):
        buffer = io.BytesIO()
        Image.new("RGB", (40, 40), (10, 120, 200)).save(buffer, format="GIF")
        unsupported = SimpleUploadedFile(
            "art.gif",
            buffer.getvalue(),
            content_type="image/gif",
        )

        response = self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": unsupported},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    @override_settings(CUSTOMIZATION_MAX_IMAGE_PIXELS=1000)
    def test_upload_with_too_many_pixels_is_rejected(self):
        response = self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": upload(size=(80, 40))},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    @override_settings(CUSTOMIZATION_MAX_TOTAL_UPLOAD_MB=0)
    def test_total_upload_limit_is_enforced(self):
        response = self.save_draft(
            [self.view_payload(self.view)],
            {f"asset_{self.view.pk}": upload()},
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

        payload = self.view_payload(self.view)
        payload["image"]["asset_path"] = foreign_path
        response = self.save_draft([payload], {})
        self.assertEqual(response.status_code, 302)

        self.assertEqual(CustomizationDraft.objects.count(), 1)
        self.assertTrue(CustomizationDraft.objects.filter(pk=other_draft.pk).exists())

    def test_non_string_asset_path_is_rejected(self):
        payload = self.view_payload(self.view)
        payload["image"]["asset_path"] = 123

        response = self.save_draft([payload], {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    def test_fixed_side_cannot_receive_an_image(self):
        fixed = self.make_view(
            name="Inside", sort_order=2, size=(120, 120), customizable=False
        )

        response = self.save_draft(
            [{"product_view_id": fixed.pk, "image": {"transform": {}}}],
            {f"asset_{fixed.pk}": upload()},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())

    def test_view_without_resolution_is_not_editable(self):
        product = Product.objects.create(
            title="Unprepared Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )
        ProductView.objects.create(
            product=product,
            name="Front",
            sort_order=1,
            print_width=100,
            print_height=100,
        )

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["editor_payload"]["views"], [])

    def test_empty_configuration_is_rejected(self):
        response = self.save_draft([], {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CustomizationDraft.objects.exists())
        self.assertEqual(
            response.url,
            reverse("customization:editor", kwargs={"slug": self.product.slug}),
        )

    def test_anonymous_customization_endpoints_redirect_to_login(self):
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            configuration_json={},
        )
        self.client.logout()
        endpoints = [
            ("get", reverse("customization:list"), {}),
            (
                "get",
                reverse("customization:editor", kwargs={"slug": self.product.slug}),
                {},
            ),
            ("get", reverse("customization:draft_detail", args=[draft.pk]), {}),
            ("get", reverse("customization:draft_payload", args=[draft.pk]), {}),
            (
                "post",
                reverse("customization:draft_save"),
                {"product_id": self.product.pk},
            ),
            ("post", reverse("customization:draft_delete", args=[draft.pk]), {}),
        ]

        for method, url, payload in endpoints:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload)
                self.assertEqual(response.status_code, 302)
                parsed = urlparse(response.url)
                self.assertEqual(parsed.path, reverse("account_login"))
                self.assertEqual(parse_qs(parsed.query)["next"], [url])

        self.assertEqual(CustomizationDraft.objects.count(), 1)

    def test_anonymous_login_redirect_invites_registration(self):
        self.client.logout()
        editor_url = reverse(
            "customization:editor", kwargs={"slug": self.product.slug}
        )

        redirect_response = self.client.get(editor_url)
        login_response = self.client.get(redirect_response.url)

        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "Sign in to customize")
        self.assertContains(login_response, "New here? Create a free account")
        self.assertContains(
            login_response, f'href="{reverse("account_signup")}?next='
        )

    def test_anonymous_webhook_stays_token_protected(self):
        self.client.logout()

        response = self.trigger_webhook([], token="wrong-token")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Invalid webhook token.")

    def test_other_user_cannot_access_or_modify_project(self):
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            name="Private project",
            configuration_json={"views": []},
        )
        other_user = get_user_model().objects.create_user(
            username="other-artist",
            password="s3cret-pass",
        )
        self.client.force_login(other_user)

        for url in (
            reverse("customization:draft_detail", args=[draft.pk]),
            reverse("customization:draft_payload", args=[draft.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

        delete_response = self.client.post(
            reverse("customization:draft_delete", args=[draft.pk])
        )
        self.assertEqual(delete_response.status_code, 404)

        editor_response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug}),
            {"draft": draft.pk},
        )
        self.assertEqual(editor_response.status_code, 200)
        self.assertIsNone(editor_response.context["draft"])

        save_response = self.save_draft([], draft=draft)
        self.assertEqual(save_response.status_code, 302)
        self.assertTrue(CustomizationDraft.objects.filter(pk=draft.pk).exists())
        self.assertEqual(CustomizationDraft.objects.count(), 1)

    def test_project_list_only_shows_the_users_own_projects(self):
        CustomizationDraft.objects.create(
            user=self.user, product=self.product, name="Mine"
        )
        other_user = get_user_model().objects.create_user(
            username="other-artist",
            password="s3cret-pass",
        )
        CustomizationDraft.objects.create(
            user=other_user, product=self.product, name="Theirs"
        )

        response = self.client.get(reverse("customization:list"))

        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")

    def test_project_list_is_paginated(self):
        for index in range(3):
            CustomizationDraft.objects.create(
                user=self.user,
                product=self.product,
                name=f"Project {index}",
            )

        with self.settings(PROJECTS_PAGE_SIZE=2):
            first_page = self.client.get(reverse("customization:list"))
            second_page = self.client.get(reverse("customization:list"), {"page": 2})
            out_of_range = self.client.get(
                reverse("customization:list"), {"page": 999}
            )
            invalid = self.client.get(reverse("customization:list"), {"page": "abc"})

        self.assertEqual(first_page.context["page_obj"].number, 1)
        self.assertEqual(len(first_page.context["drafts"]), 2)
        self.assertEqual(second_page.context["page_obj"].number, 2)
        self.assertEqual(len(second_page.context["drafts"]), 1)
        # A missing or broken ?page= never turns into a 404.
        self.assertEqual(out_of_range.status_code, 200)
        self.assertEqual(out_of_range.context["page_obj"].number, 2)
        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(invalid.context["page_obj"].number, 1)
        self.assertContains(first_page, 'rel="next"')
        self.assertContains(second_page, 'rel="prev"')
        self.assertContains(first_page, "Page 1 of 2")

    def test_project_list_shows_no_pagination_when_everything_fits(self):
        CustomizationDraft.objects.create(
            user=self.user, product=self.product, name="Only project"
        )

        response = self.client.get(reverse("customization:list"))

        self.assertFalse(response.context["is_paginated"])
        self.assertNotContains(response, "list-pagination")

    def test_staff_see_the_deactivate_action_in_the_editor(self):
        staff = get_user_model().objects.create_user(
            username="staff",
            password="s3cret-pass",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff actions")
        self.assertContains(response, "Deactivate product")
        self.assertContains(response, 'id="deactivate-product-modal"')
        self.assertContains(
            response,
            reverse("products:deactivate", kwargs={"slug": self.product.slug}),
        )
        self.assertContains(
            response,
            "Sides, printable areas, saved projects and uploaded files are kept.",
        )

    def test_customers_do_not_see_the_deactivate_action(self):
        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Deactivate product")
        self.assertNotContains(response, "deactivate-product-modal")

    def test_staff_see_the_deactivate_action_without_customizable_sides(self):
        product = Product.objects.create(
            title="Unprepared Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )
        ProductView.objects.create(
            product=product,
            name="Front",
            sort_order=1,
            mockup_image="products/mockups/front.webp",
            canvas_width_px=200,
            canvas_height_px=200,
        )
        staff = get_user_model().objects.create_user(
            username="staff",
            password="s3cret-pass",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(
            reverse("customization:editor", kwargs={"slug": product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "This product is sold exactly as shown: it has no customizable sides yet."
        )
        self.assertContains(response, "Deactivate product")
        self.assertContains(
            response,
            reverse("products:deactivate", kwargs={"slug": product.slug}),
        )

    def test_deactivated_product_hides_its_projects_until_reactivated(self):
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            name="Archived project",
            configuration_json={"views": []},
        )
        self.product.is_active = False
        self.product.save(update_fields=["is_active", "updated_at"])

        listing = self.client.get(reverse("customization:list"))
        detail = self.client.get(
            reverse("customization:draft_detail", args=[draft.pk])
        )
        payload = self.client.get(
            reverse("customization:draft_payload", args=[draft.pk])
        )

        self.assertNotContains(listing, "Archived project")
        self.assertEqual(detail.status_code, 404)
        self.assertEqual(payload.status_code, 404)

        self.product.is_active = True
        self.product.save(update_fields=["is_active", "updated_at"])

        listing = self.client.get(reverse("customization:list"))
        self.assertContains(listing, "Archived project")
