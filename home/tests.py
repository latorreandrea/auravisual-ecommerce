import io
import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ShippingAddress
from cart.models import Cart, CartItem
from customization.models import CustomizationDraft
from orders.models import Order
from products.models import Product, ProductView

User = get_user_model()


class HomePageTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            title="NFC business card",
            description="A reusable card that opens your profile with one tap.",
            base_price=Decimal("39.00"),
            stock_quantity=12,
        )

    def test_anonymous_home_shows_the_catalogue_and_account_entry_points(self):
        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Make every product unmistakably yours.")
        self.assertContains(response, "NFC business card")
        self.assertContains(response, "how-it-works")
        self.assertContains(response, "file-guide")
        self.assertContains(response, "Sign in to start customizing")
        self.assertContains(response, "View in catalogue")
        self.assertContains(response, "Create an account")
        self.assertContains(response, f'{reverse("account_signup")}?next=/')
        self.assertNotContains(response, "Pick up where you left off")

    def test_home_features_the_first_view_with_a_mockup(self):
        ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image="products/mockups/nfc-front.webp",
            canvas_width_px=800,
            canvas_height_px=600,
        )

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Featured product")
        self.assertContains(response, "products/mockups/nfc-front.webp")

    def test_hero_shows_the_latest_project(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image="products/mockups/nfc-front.webp",
            canvas_width_px=800,
            canvas_height_px=600,
            print_x=200,
            print_y=150,
            print_width=400,
            print_height=300,
        )
        older = CustomizationDraft.objects.create(
            user=user,
            product=self.product,
            name="Older project",
            configuration_json={"views": []},
        )
        latest = CustomizationDraft.objects.create(
            user=user,
            product=self.product,
            name="Newest project",
            configuration_json={"views": []},
        )
        CustomizationDraft.objects.filter(pk=older.pk).update(
            updated_at=timezone.now() - timedelta(days=2)
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["latest_draft"].pk, latest.pk)
        self.assertContains(response, "Your latest project")
        self.assertContains(response, "Newest project")
        self.assertContains(response, "Continue customizing")
        self.assertContains(response, 'data-tilt-max="14"')
        self.assertNotContains(response, "home-hero-product-meta")
        self.assertContains(
            response,
            f'{reverse("customization:editor", kwargs={"slug": self.product.slug})}?draft={latest.pk}',
        )
        self.assertContains(response, "Pick up where you left off")

    def test_workspace_lists_at_most_eight_projects(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        for index in range(10):
            CustomizationDraft.objects.create(
                user=user,
                product=self.product,
                name=f"Project {index}",
                configuration_json={"views": []},
            )
        self.client.force_login(user)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(len(response.context["recent_drafts"]), 8)

    def test_workspace_cards_are_compact_and_only_the_preview_tilts(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        CustomizationDraft.objects.create(
            user=user,
            product=self.product,
            name="Business card mockup",
            configuration_json={"views": []},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home:index"))
        html = response.content.decode()

        # The card is a flat container: the caption below stays readable while
        # the miniature alone reacts to the pointer.
        self.assertIn('<article class="home-project-card">', html)
        self.assertNotIn('class="home-project-card tilt-card"', html)
        self.assertRegex(html, r'class="home-project-tilt tilt-card"\s+data-tilt')
        self.assertContains(response, "Business card mockup")
        self.assertContains(response, self.product.title)
        self.assertContains(response, "home-project-price")
        self.assertContains(response, "&euro; 39.00")

    def test_catalogue_section_only_shows_the_newest_products(self):
        newer_products = []
        for index in range(7):
            newer_products.append(
                Product.objects.create(
                    title=f"Fresh product {index}",
                    description="Another customizable product.",
                    base_price=Decimal("19.00"),
                    stock_quantity=3,
                )
            )
        # The product from setUp is the oldest one in the catalogue.
        Product.objects.filter(pk=self.product.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )
        for offset, product in enumerate(newer_products):
            Product.objects.filter(pk=product.pk).update(
                created_at=timezone.now() - timedelta(days=offset)
            )

        response = self.client.get(reverse("home:index"))

        titles = [product.title for product in response.context["products"]]
        self.assertEqual(len(titles), 6)
        self.assertEqual(titles[0], "Fresh product 0")
        self.assertEqual(titles[-1], "Fresh product 5")
        self.assertNotIn(self.product.title, titles)
        self.assertNotContains(response, "Fresh product 6")
        # The section always points at the paginated catalogue.
        self.assertContains(response, f'href="{reverse("products:list")}"')
        self.assertContains(response, "Browse the full catalogue")
        self.assertContains(response, "Showing the 6 newest products.")

    def test_home_projects_without_drafts_use_the_empty_state(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        self.client.force_login(user)

        response = self.client.get(reverse("home:index"))

        self.assertIsNone(response.context["latest_draft"])
        self.assertContains(response, "Design it once. See it instantly.")
        self.assertContains(response, "No projects yet")
        self.assertContains(response, "Start customizing")

    def test_home_ships_the_tilt_interactions(self):
        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "data-tilt")
        self.assertContains(response, 'data-tilt-max="10"')
        self.assertContains(response, "vanilla-tilt@1.8.1")
        self.assertContains(response, "js/card-tilt.js")
        # The glare overlay lit the transparent padding around the mockups, so
        # it would visually detach the card from the hero panel.
        self.assertNotContains(response, "data-tilt-glare")
        # The hero relies on the badge and the preview only.
        self.assertNotContains(response, "home-hero-product-meta")

    def test_staff_home_exposes_the_product_creation_shortcut(self):
        staff = User.objects.create_user(
            username="staff",
            password="s3cret-pass",
            is_staff=True,
        )
        self.client.force_login(staff)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{reverse("products:create")}"')

    def test_authenticated_home_suggests_products_from_the_latest_order(self):
        user = User.objects.create_user(username="returning", password="s3cret-pass")
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        address = ShippingAddress.objects.create(
            user=user,
            full_name="Returning Customer",
            line_1="1 Main Street",
            city="Copenhagen",
            postal_code="1000",
            country="Denmark",
        )
        Order.objects.create(user=user, cart=cart, shipping_address=address)

        self.client.force_login(user)
        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "From your latest order")
        self.assertContains(response, "Customize again")
        self.assertContains(response, self.product.title)

    def test_navbar_login_form_keeps_the_next_url_on_the_login_page(self):
        next_url = self.product.get_absolute_url()

        response = self.client.get(reverse("account_login"), {"next": next_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<input type="hidden" name="next" value="{next_url}">',
        )


def _png_bytes(size=(200, 200), color=(255, 255, 255, 255)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class HomeCardPreviewTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, True)
        media_override = override_settings(MEDIA_ROOT=self.media_root)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.user = User.objects.create_user(
            username="card-artist", password="s3cret-pass"
        )
        self.client.force_login(self.user)
        self.product = Product.objects.create(
            title="NFC business card",
            description="A reusable card that opens your profile with one tap.",
            base_price=Decimal("39.00"),
            stock_quantity=12,
        )
        self.view = ProductView.objects.create(
            product=self.product,
            name="Front",
            sort_order=1,
            mockup_image=SimpleUploadedFile(
                "mockup.png",
                _png_bytes(),
                content_type="image/png",
            ),
            canvas_width_px=200,
            canvas_height_px=200,
            print_x=50,
            print_y=50,
            print_width=100,
            print_height=100,
        )

    def _save_asset(self):
        saved_path = default_storage.save(
            "customization/drafts/home-card/assets/art.png",
            ContentFile(_png_bytes((80, 40), (200, 30, 30, 255))),
        )
        return saved_path, default_storage.url(saved_path)

    def _configuration(self, asset_path, asset_url):
        return {
            "views": [
                {
                    "product_view_id": self.view.pk,
                    "view_name": self.view.name,
                    "image": {
                        "asset_path": asset_path,
                        "asset_url": asset_url,
                        "original_name": "art.png",
                        "natural_width": 80,
                        "natural_height": 40,
                        "transform": {
                            "x": 50,
                            "y": 50,
                            "width": 100,
                            "height": 50,
                            "rotation": 15,
                        },
                    },
                }
            ]
        }

    def _make_draft(self, preview=False, missing_preview=False):
        asset_path, asset_url = self._save_asset()
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            configuration_json=self._configuration(asset_path, asset_url),
        )
        if preview:
            draft.preview_webp_url.save(
                "preview.webp",
                ContentFile(b"preview"),
                save=True,
            )
        elif missing_preview:
            draft.preview_webp_url = "customization/previews/missing/preview.webp"
            draft.save(update_fields=["preview_webp_url"])
        return draft

    def _product_from_response(self, response):
        return next(
            product
            for product in response.context["products"]
            if product.pk == self.product.pk
        )

    def test_project_card_uses_the_saved_preview_while_the_catalogue_stays_base(self):
        draft = self._make_draft(preview=True)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        # The project miniature shows the customer's own render...
        project = response.context["recent_drafts"][0]
        self.assertEqual(project.card_preview_url, draft.preview_webp_url.url)
        self.assertTrue(project.card_uses_preview)
        self.assertEqual(project.card_layers, [])
        self.assertContains(response, draft.preview_webp_url.url)
        # ...while the catalogue teaser always previews the base product.
        product = self._product_from_response(response)
        self.assertEqual(product.card_preview_url, "")
        self.assertFalse(product.card_uses_preview)
        self.assertEqual(product.card_layers, [])
        self.assertEqual(product.card_mockup_url, self.view.mockup_image.url)
        self.assertEqual(response.context["featured_product"].card_preview_url, "")

    def test_project_card_falls_back_to_svg_layers_without_a_preview(self):
        self._make_draft()

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        project = response.context["recent_drafts"][0]
        self.assertEqual(project.card_preview_url, "")
        self.assertFalse(project.card_uses_preview)
        self.assertEqual(len(project.card_layers), 1)

        layer = project.card_layers[0]
        self.assertEqual(layer["zone_x"], 50.0)
        self.assertEqual(layer["zone_y"], 50.0)
        self.assertEqual(layer["zone_width"], 100.0)
        self.assertEqual(layer["zone_height"], 100.0)
        self.assertEqual(layer["x"], 50.0)
        self.assertEqual(layer["y"], 50.0)
        self.assertEqual(layer["width"], 100.0)
        self.assertEqual(layer["height"], 50.0)
        self.assertEqual(layer["rotation"], 15.0)
        self.assertEqual(layer["center_x"], 100.0)
        self.assertEqual(layer["center_y"], 75.0)

        self.assertContains(response, "home-card-composite")
        self.assertContains(response, 'viewBox="0 0 200 200"')
        self.assertContains(response, "rotate(15.0 100.0 75.0)")
        self.assertContains(response, layer["asset_url"])
        self.assertContains(response, "home-preview-clip-draft")
        # The catalogue card keeps using the untouched mockup.
        product = self._product_from_response(response)
        self.assertEqual(product.card_preview_url, "")
        self.assertEqual(product.card_layers, [])
        self.assertNotContains(response, "home-preview-clip-product")
        self.assertEqual(response.context["featured_product"].card_layers, [])

    def test_project_card_ignores_a_preview_file_that_no_longer_exists(self):
        self._make_draft(missing_preview=True)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        project = response.context["recent_drafts"][0]
        self.assertEqual(project.card_preview_url, "")
        self.assertEqual(len(project.card_layers), 1)
        self.assertNotContains(
            response, "customization/previews/missing/preview.webp"
        )

    def test_catalogue_card_uses_the_mockup_when_no_draft_exists(self):
        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        product = self._product_from_response(response)
        self.assertEqual(product.card_preview_url, "")
        self.assertEqual(product.card_layers, [])
        self.assertEqual(product.card_mockup_url, self.view.mockup_image.url)
        self.assertContains(response, self.view.mockup_image.url)
        self.assertNotContains(response, "home-card-composite")

    def test_catalogue_cards_never_borrow_a_customer_draft(self):
        older = self._make_draft(preview=True)
        newer = self._make_draft(preview=True)
        CustomizationDraft.objects.filter(pk=older.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )

        response = self.client.get(reverse("home:index"))

        # The catalogue always shows the base product...
        product = self._product_from_response(response)
        self.assertNotEqual(older.preview_webp_url.url, newer.preview_webp_url.url)
        self.assertEqual(product.card_preview_url, "")
        self.assertEqual(product.card_mockup_url, self.view.mockup_image.url)
        # ...while the workspace lists the project touched most recently first.
        self.assertEqual(response.context["recent_drafts"][0].pk, newer.pk)

    def test_anonymous_home_never_exposes_saved_previews(self):
        draft = self._make_draft(preview=True)
        self.client.logout()

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        product = self._product_from_response(response)
        self.assertEqual(product.card_preview_url, "")
        self.assertEqual(product.card_layers, [])
        self.assertEqual(product.card_mockup_url, self.view.mockup_image.url)
        self.assertNotContains(response, draft.preview_webp_url.url)

    def test_malformed_saved_configuration_only_affects_the_project_card(self):
        draft = self._make_draft()
        draft.configuration_json = {
            "views": [
                "not-a-view",
                {
                    "product_view_id": self.view.pk,
                    "image": {"asset_path": "", "transform": "not-a-transform"},
                },
                {
                    "product_view_id": self.view.pk,
                    "image": {"asset_path": "customization/drafts/gone/art.png"},
                },
            ]
        }
        draft.save(update_fields=["configuration_json"])

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        project = response.context["recent_drafts"][0]
        self.assertEqual(project.card_layers, [])
        product = self._product_from_response(response)
        self.assertEqual(product.card_layers, [])
        self.assertEqual(product.card_mockup_url, self.view.mockup_image.url)
