from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
        self.assertContains(response, "Make every card and stand unmistakably yours.")
        self.assertContains(response, "NFC business card")
        self.assertContains(response, "how-it-works")
        self.assertContains(response, "file-guide")
        self.assertContains(response, "Sign in to customize")
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

    def test_authenticated_home_shows_the_latest_saved_designs(self):
        user = User.objects.create_user(username="artist", password="s3cret-pass")
        draft = CustomizationDraft.objects.create(
            user=user,
            product=self.product,
            configuration_json={"views": []},
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pick up where you left off")
        self.assertContains(response, "Continue editing")
        self.assertContains(
            response,
            f'{reverse("customization:editor", kwargs={"slug": self.product.slug})}?draft={draft.pk}',
        )
        self.assertNotContains(response, "No saved designs yet")

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
