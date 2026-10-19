import io
import shutil
import tempfile
from decimal import Decimal

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import CustomizationZoneForm
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
    def _mockup():
        image_buffer = io.BytesIO()
        Image.new("RGB", (640, 480), "white").save(image_buffer, format="PNG")
        return SimpleUploadedFile(
            "mockup.png",
            image_buffer.getvalue(),
            content_type="image/png",
        )

    def test_anonymous_users_are_redirected_to_login(self):
        response = self.client.get(reverse("products:create"))

        self.assertRedirects(
            response,
            f'{reverse("account_login")}?next={reverse("products:create")}',
        )

    def test_staff_can_open_the_create_page(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("products:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create a product")
        self.assertContains(response, 'name="product-title"')
        self.assertContains(response, 'name="view-mockup_image"')
        self.assertContains(response, 'name="zone-name"')

    def test_non_staff_users_cannot_open_the_create_page(self):
        self.client.force_login(self.customer)

        response = self.client.get(reverse("products:create"))

        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_a_product_with_its_first_view_and_zone(self):
        mockup = self._mockup()
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            {
                "product-title": "Custom NFC card",
                "product-description": "A durable card with your artwork on the front.",
                "product-base_price": "39.00",
                "product-stock_quantity": "25",
                "product-is_active": "on",
                "view-name": "Front",
                "view-sort_order": "1",
                "view-mockup_image": mockup,
                "zone-name": "Main artwork",
                "zone-x": "20",
                "zone-y": "30",
                "zone-width": "300",
                "zone-height": "200",
                "zone-rotation": "0",
                "zone-allow_rotation": "on",
                "zone-allow_scaling": "on",
                "zone-max_file_size_mb": "10",
                "zone-aspect_ratio_locked": "on",
            },
        )

        self.assertRedirects(response, reverse("products:list"))
        product = Product.objects.get(title="Custom NFC card")
        product_view = ProductView.objects.get(product=product)
        zone = CustomizationZone.objects.get(product_view=product_view)

        self.assertEqual(product.slug, "custom-nfc-card")
        self.assertEqual(product_view.canvas_width_px, 640)
        self.assertEqual(product_view.canvas_height_px, 480)
        self.assertTrue(product_view.mockup_image.name.endswith(".webp"))
        self.assertEqual(zone.name, "Main artwork")
        self.assertEqual(zone.x, 20)
        self.assertEqual(zone.width, 300)

    def test_zone_must_fit_inside_the_optimised_mockup(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("products:create"),
            {
                "product-title": "Oversized area card",
                "product-base_price": "39.00",
                "product-stock_quantity": "25",
                "product-is_active": "on",
                "view-name": "Front",
                "view-sort_order": "1",
                "view-mockup_image": self._mockup(),
                "zone-name": "Too wide",
                "zone-x": "20",
                "zone-y": "30",
                "zone-width": "700",
                "zone-height": "200",
                "zone-rotation": "0",
                "zone-allow_rotation": "on",
                "zone-allow_scaling": "on",
                "zone-max_file_size_mb": "10",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The area exceeds the mockup width.")
        self.assertFalse(Product.objects.filter(title="Oversized area card").exists())

    def test_quick_create_zone_defaults_to_the_store_upload_limit(self):
        form = CustomizationZoneForm()

        self.assertEqual(
            form.fields["max_file_size_mb"].initial,
            settings.CUSTOMIZATION_MAX_UPLOAD_MB,
        )
        self.assertIn(
            f"{settings.CUSTOMIZATION_MAX_UPLOAD_MB} MB",
            form.fields["max_file_size_mb"].help_text,
        )
