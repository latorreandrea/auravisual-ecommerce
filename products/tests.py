import io
import json
import shutil
import tempfile
from decimal import Decimal

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from customization.models import CustomizationDraft

from .forms import DEFAULT_AREA_RATIOS, PrintAreaForm
from .models import CustomizationZone, Product, ProductView

User = get_user_model()


class ProductCustomizationAccessTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            title="Classic Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )

    def test_anonymous_visitors_are_invited_to_sign_in_to_customize(self):
        response = self.client.get(reverse("products:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in to customize")
        self.assertNotContains(response, f'href="{self.product.get_absolute_url()}"')
        self.assertContains(response, f"{reverse('account_login')}?next=")
        self.assertNotContains(response, f'href="{reverse("customization:list")}"')

    def test_authenticated_users_open_the_editor_from_the_shop(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        self.client.force_login(user)

        response = self.client.get(reverse("products:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customize")
        self.assertNotContains(response, "Sign in to customize")
        self.assertContains(response, f'href="{self.product.get_absolute_url()}"')
        self.assertContains(response, f'href="{reverse("customization:list")}"')


class StaffProductCreateViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff",
            password="s3cret-pass",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username="customer",
            password="s3cret-pass",
        )

    @staticmethod
    def _mockup(size=(640, 480), color="white", name="mockup.png"):
        image_buffer = io.BytesIO()
        Image.new("RGB", size, color).save(image_buffer, format="PNG")
        return SimpleUploadedFile(
            name,
            image_buffer.getvalue(),
            content_type="image/png",
        )

    def _payload(self, faces, product=None):
        data = {
            "views-TOTAL_FORMS": str(len(faces)),
            "views-INITIAL_FORMS": "0",
            "views-MIN_NUM_FORMS": "1",
            "views-MAX_NUM_FORMS": "8",
            "product-title": "Custom NFC card",
            "product-description": "A durable card with your artwork.",
            "product-base_price": "39.00",
            "product-stock_quantity": "25",
            "product-is_active": "on",
        }
        data.update(product or {})

        for index, face in enumerate(faces):
            name = face.get("name", f"Side {index + 1}")
            data[f"views-{index}-name"] = name
            if not face.get("omit_mockup"):
                data[f"views-{index}-mockup_image"] = face.get(
                    "mockup"
                ) or self._mockup(name=f"mockup-{index}.png")
            data[f"zone-{index}-name"] = face.get(
                "zone_name", f"{name} artwork"
            )
            if face.get("full_face"):
                data[f"zone-{index}-full_face"] = "on"
            else:
                ratios = face.get("ratios", DEFAULT_AREA_RATIOS)
                for key in ("x_ratio", "y_ratio", "width_ratio", "height_ratio"):
                    data[f"zone-{index}-{key}"] = str(ratios[key])
            data[f"zone-{index}-rotation"] = str(face.get("rotation", 0))
            if face.get("allow_rotation", True):
                data[f"zone-{index}-allow_rotation"] = "on"
            if face.get("allow_scaling", True):
                data[f"zone-{index}-allow_scaling"] = "on"
            data[f"zone-{index}-max_file_size_mb"] = str(
                face.get("max_file_size_mb", settings.CUSTOMIZATION_MAX_UPLOAD_MB)
            )
            if face.get("aspect_ratio_locked"):
                data[f"zone-{index}-aspect_ratio_locked"] = "on"

        return data


    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.get(reverse("products:create"))

        self.assertRedirects(
            response,
            f'{reverse("account_login")}?next={reverse("products:create")}',
        )

    def test_non_staff_users_cannot_open_the_create_page(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse("products:create"))

        self.assertEqual(response.status_code, 403)

    def test_staff_see_the_three_step_wizard_with_one_face(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("products:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a product")
        self.assertContains(response, 'data-wizard-step="1"')
        self.assertContains(response, 'data-wizard-step="2"')
        self.assertContains(response, 'data-wizard-step="3"')
        self.assertContains(response, 'data-face-panel')
        self.assertContains(response, 'name="views-TOTAL_FORMS"')
        self.assertContains(response, 'name="views-0-mockup_image"')
        self.assertContains(response, 'name="zone-0-x_ratio"')
        self.assertContains(response, "Add side")
        self.assertContains(response, "Printable area")
        self.assertContains(response, "Use the entire face")
        self.assertNotContains(response, "Overlay texture")
        self.assertNotContains(response, "overlay_texture")
        self.assertEqual(response.context["view_formset"].total_form_count(), 1)
        self.assertEqual(response.context["active_step"], 1)

    def test_product_view_has_no_overlay_texture_field(self):
        field_names = {field.name for field in ProductView._meta.get_fields()}

        self.assertNotIn("overlay_texture", field_names)

    def test_staff_can_create_a_product_with_one_side_and_one_zone(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            self._payload([{"name": "Front"}]),
        )

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(title="Custom NFC card")
        product_view = ProductView.objects.get(product=product)
        zone = CustomizationZone.objects.get(product_view=product_view)

        self.assertEqual(product.slug, "custom-nfc-card")
        self.assertEqual(product.stock_quantity, 25)
        self.assertTrue(product.is_active)
        self.assertEqual(product_view.name, "Front")
        self.assertEqual(product_view.sort_order, 1)
        self.assertEqual(product_view.canvas_width_px, 640)
        self.assertEqual(product_view.canvas_height_px, 480)
        self.assertTrue(product_view.mockup_image.name.endswith(".webp"))
        self.assertEqual(zone.name, "Front artwork")
        self.assertAlmostEqual(zone.x, 64)
        self.assertAlmostEqual(zone.y, 48)
        self.assertAlmostEqual(zone.width, 512)
        self.assertAlmostEqual(zone.height, 384)
        self.assertEqual(product_view.zones.count(), 1)

    def test_staff_can_create_front_and_back_with_one_zone_each(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            self._payload(
                [
                    {"name": "Front"},
                    {
                        "name": "Back",
                        "mockup": self._mockup(
                            size=(400, 300), color="black", name="back.png"
                        ),
                        "full_face": True,
                    },
                ]
            ),
        )

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(title="Custom NFC card")
        views = list(product.views.order_by("sort_order"))

        self.assertEqual([view.name for view in views], ["Front", "Back"])
        self.assertEqual([view.sort_order for view in views], [1, 2])
        self.assertEqual(views[0].zones.count(), 1)
        self.assertEqual(views[1].zones.count(), 1)
        self.assertEqual(views[1].canvas_width_px, 400)
        self.assertEqual(views[1].canvas_height_px, 300)

        back_zone = views[1].zones.get()
        self.assertEqual(back_zone.x, 0)
        self.assertEqual(back_zone.y, 0)
        self.assertEqual(back_zone.width, 400)
        self.assertEqual(back_zone.height, 300)

    @override_settings(PRODUCT_MOCKUP_MAX_DIMENSION=320)
    def test_ratios_are_converted_after_the_mockup_is_resized(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            self._payload(
                [
                    {
                        "name": "Front",
                        "ratios": {
                            "x_ratio": 0.25,
                            "y_ratio": 0.25,
                            "width_ratio": 0.5,
                            "height_ratio": 0.5,
                        },
                    }
                ]
            ),
        )

        self.assertRedirects(response, reverse("products:list"))
        product_view = ProductView.objects.get()
        zone = product_view.zones.get()

        self.assertEqual(product_view.canvas_width_px, 320)
        self.assertEqual(product_view.canvas_height_px, 240)
        self.assertEqual(zone.x, 80)
        self.assertEqual(zone.y, 60)
        self.assertEqual(zone.width, 160)
        self.assertEqual(zone.height, 120)


    def test_zone_must_fit_inside_the_optimized_mockup(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            self._payload(
                [
                    {
                        "name": "Front",
                        "ratios": {
                            "x_ratio": 0.8,
                            "y_ratio": 0.1,
                            "width_ratio": 0.4,
                            "height_ratio": 0.8,
                        },
                    }
                ]
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The printable area exceeds the mockup width.")
        self.assertEqual(response.context["active_step"], 2)
        self.assertFalse(Product.objects.filter(title="Custom NFC card").exists())

    def test_at_least_one_side_is_required(self):
        self.client.force_login(self.staff)
        data = self._payload([])
        data["views-TOTAL_FORMS"] = "0"

        response = self.client.post(reverse("products:create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least 1")
        self.assertEqual(response.context["active_step"], 2)
        self.assertFalse(Product.objects.filter(title="Custom NFC card").exists())

    def test_more_than_eight_sides_are_rejected(self):
        self.client.force_login(self.staff)
        faces = [{"name": f"Side {index + 1}"} for index in range(9)]

        response = self.client.post(
            reverse("products:create"),
            self._payload(faces),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at most 8")
        self.assertFalse(Product.objects.filter(title="Custom NFC card").exists())

    def test_product_errors_route_to_step_one(self):
        self.client.force_login(self.staff)
        data = self._payload([{"name": "Front"}])
        data["product-title"] = ""

        response = self.client.post(reverse("products:create"), data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertEqual(response.context["active_step"], 1)
        self.assertFalse(Product.objects.filter(base_price="39.00").exists())

    def test_advanced_zone_settings_and_catalogue_visibility_are_saved(self):
        self.client.force_login(self.staff)
        data = self._payload(
            [
                {
                    "name": "Front",
                    "zone_name": "Chest print",
                    "rotation": 15,
                    "allow_scaling": False,
                    "max_file_size_mb": 4,
                    "aspect_ratio_locked": True,
                }
            ],
            product={
                "product-title": "Hidden product",
                "product-stock_quantity": "7",
            },
        )
        data.pop("product-is_active")

        response = self.client.post(reverse("products:create"), data)

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(title="Hidden product")
        zone = CustomizationZone.objects.get()

        self.assertEqual(product.stock_quantity, 7)
        self.assertFalse(product.is_active)
        self.assertEqual(zone.name, "Chest print")
        self.assertEqual(zone.rotation, 15)
        self.assertTrue(zone.allow_rotation)
        self.assertFalse(zone.allow_scaling)
        self.assertEqual(zone.max_file_size_mb, 4)
        self.assertTrue(zone.aspect_ratio_locked)

    def test_print_area_form_defaults_to_the_store_upload_limit(self):
        form = PrintAreaForm()

        self.assertEqual(
            form.fields["max_file_size_mb"].initial,
            settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        )
        self.assertEqual(
            form.fields["max_file_size_mb"].max_value,
            settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        )
        self.assertIn(
            f"{settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB",
            form.fields["max_file_size_mb"].help_text,
        )


    def test_invalid_ajax_submission_returns_structured_errors_and_saves_nothing(self):
        self.client.force_login(self.staff)
        data = self._payload([{"name": "Front", "omit_mockup": True}])

        response = self.client.post(
            reverse("products:create"),
            data,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 422)
        payload = json.loads(response.content)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["step"], 2)
        self.assertEqual(payload["face_index"], 0)
        self.assertIn("views-0-mockup_image", payload["errors"])
        self.assertFalse(Product.objects.filter(title="Custom NFC card").exists())

    def test_successful_ajax_submission_returns_the_redirect_url(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            self._payload([{"name": "Front"}]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["redirect_url"], reverse("products:list"))
        self.assertTrue(Product.objects.filter(title="Custom NFC card").exists())


class ProductListGalleryTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    @staticmethod
    def _mockup(filename):
        buffer = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(buffer, format="PNG")
        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type="image/png",
        )

    def setUp(self):
        self.product = Product.objects.create(
            title="Gallery card",
            base_price=Decimal("29.00"),
            stock_quantity=3,
        )
        self.empty_product = Product.objects.create(
            title="Empty gallery card",
            base_price=Decimal("19.00"),
            stock_quantity=2,
        )

        ProductView.objects.create(
            product=self.product,
            name="No mockup",
            sort_order=0,
        )
        ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image=self._mockup("front.png"),
            canvas_width_px=640,
            canvas_height_px=480,
        )
        ProductView.objects.create(
            product=self.product,
            name="Back",
            sort_order=2,
            mockup_image=self._mockup("back.png"),
            canvas_width_px=640,
            canvas_height_px=480,
        )
        ProductView.objects.create(
            product=self.product,
            name="Left side",
            sort_order=3,
            mockup_image=self._mockup("left.png"),
            canvas_width_px=640,
            canvas_height_px=480,
        )

    def test_gallery_uses_ordered_views_with_mockups_and_prefetches_them(self):
        response = self.client.get(reverse("products:list"))

        self.assertEqual(response.status_code, 200)
        products = {product.pk: product for product in response.context["products"]}
        product = products[self.product.pk]

        self.assertIn("views", product._prefetched_objects_cache)
        self.assertEqual(
            [view.name for view in product.gallery_views],
            ["Front", "Back", "Left side"],
        )
        self.assertEqual(products[self.empty_product.pk].gallery_views, [])
        self.assertNotIn("No mockup", response.content.decode())

    def test_gallery_renders_accessible_navigation_in_sort_order(self):
        response = self.client.get(reverse("products:list"))
        html = response.content.decode()

        self.assertContains(response, "data-gallery-dot=", count=3)
        self.assertContains(
            response,
            f'aria-controls="product-gallery-{self.product.pk}"',
            count=5,
        )
        self.assertContains(response, 'aria-label="Show Front"')
        self.assertContains(response, 'aria-label="Show Back"')
        self.assertContains(response, 'aria-label="Show Left side"')
        self.assertContains(response, "1 / 3")
        self.assertContains(response, "js/product-gallery.js")
        self.assertRegex(
            html,
            r'aria-label="2 of 3: Back"\s+aria-hidden="true"',
        )

        front_position = html.index('alt="Gallery card - Front"')
        back_position = html.index('alt="Gallery card - Back"')
        left_position = html.index('alt="Gallery card - Left side"')
        self.assertLess(front_position, back_position)
        self.assertLess(back_position, left_position)

    def test_first_gallery_image_is_eager_and_the_rest_are_lazy(self):
        response = self.client.get(reverse("products:list"))
        html = response.content.decode()

        self.assertRegex(
            html,
            r'alt="Gallery card - Front"[^>]*loading="eager"',
        )
        self.assertRegex(
            html,
            r'alt="Gallery card - Back"[^>]*loading="lazy"',
        )
        self.assertRegex(
            html,
            r'alt="Gallery card - Left side"[^>]*loading="lazy"',
        )

    def test_placeholder_is_rendered_when_no_side_has_a_mockup(self):
        response = self.client.get(reverse("products:list"))

        self.assertContains(response, "Mockup coming soon", count=1)

    def test_single_side_renders_as_a_static_image_without_controls(self):
        self.product.views.exclude(name="Front").delete()

        response = self.client.get(reverse("products:list"))

        self.assertContains(response, "data-gallery-slide", count=1)
        self.assertNotContains(response, "data-gallery-prev")
        self.assertNotContains(response, "data-gallery-next")
        self.assertNotContains(response, "data-gallery-dot=")
        self.assertRegex(
            response.content.decode(),
            r'data-gallery-label>Front</span>',
        )


class StaffProductDeactivateViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff",
            password="s3cret-pass",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username="customer",
            password="s3cret-pass",
        )
        self.product = Product.objects.create(
            title="Classic Tee",
            base_price=Decimal("25.00"),
            stock_quantity=5,
        )
        self.product_view = ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image="products/mockups/front.webp",
            canvas_width_px=200,
            canvas_height_px=200,
        )
        self.zone = CustomizationZone.objects.create(
            product_view=self.product_view,
            name="Chest",
            x=50,
            y=50,
            width=100,
            height=100,
        )
        self.draft = CustomizationDraft.objects.create(
            user=self.customer,
            product=self.product,
            configuration_json={"views": []},
        )

    def deactivate_url(self):
        return reverse(
            "products:deactivate",
            kwargs={"slug": self.product.slug},
        )

    def test_staff_soft_deletes_without_removing_related_data(self):
        self.client.force_login(self.staff)

        response = self.client.post(self.deactivate_url(), follow=True)

        self.assertRedirects(response, reverse("products:list"))
        self.assertContains(response, "was deactivated")
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(ProductView.objects.filter(pk=self.product_view.pk).exists())
        self.assertTrue(CustomizationZone.objects.filter(pk=self.zone.pk).exists())
        self.assertTrue(CustomizationDraft.objects.filter(pk=self.draft.pk).exists())

    def test_non_staff_users_cannot_deactivate_products(self):
        self.client.force_login(self.customer)

        response = self.client.post(self.deactivate_url())

        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.post(self.deactivate_url())

        self.assertRedirects(
            response,
            f'{reverse("account_login")}?next={self.deactivate_url()}',
        )

    def test_only_post_is_allowed(self):
        self.client.force_login(self.staff)

        response = self.client.get(self.deactivate_url())

        self.assertEqual(response.status_code, 405)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_active)

    def test_deactivating_an_inactive_product_is_idempotent(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.staff)

        response = self.client.post(self.deactivate_url(), follow=True)

        self.assertRedirects(response, reverse("products:list"))
        self.assertContains(response, "is already inactive.")
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

    def test_inactive_product_is_hidden_from_catalogue_and_editor(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active", "updated_at"])
        self.client.force_login(self.customer)

        catalogue = self.client.get(reverse("products:list"))
        editor = self.client.get(
            reverse(
                "customization:editor",
                kwargs={"slug": self.product.slug},
            )
        )

        self.assertNotContains(catalogue, self.product.title)
        self.assertEqual(editor.status_code, 404)

    def test_unknown_product_returns_404(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:deactivate", kwargs={"slug": "missing"})
        )

        self.assertEqual(response.status_code, 404)
