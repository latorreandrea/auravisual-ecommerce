from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from customization.models import CustomizationDraft
from products.models import Product

from .context import CART_SESSION_KEY, line_key

User = get_user_model()


class CartDraftTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="cart-user", password="secret")
        self.product = Product.objects.create(
            title="Canvas Tote",
            base_price="19.90",
            stock_quantity=5,
        )
        self.client.force_login(self.user)

    def _put_draft_in_cart(self, draft):
        session = self.client.session
        session[CART_SESSION_KEY] = {
            line_key(self.product.pk, draft.pk): {
                "product_id": self.product.pk,
                "draft_id": str(draft.pk),
                "quantity": 1,
            }
        }
        session.save()

    def test_deleted_draft_is_flagged_in_the_cart(self):
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            configuration_json={},
        )
        self._put_draft_in_cart(draft)

        draft.delete()

        response = self.client.get(reverse("cart:detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This customization is no longer available.")

    def test_available_draft_is_linked_from_the_cart(self):
        draft = CustomizationDraft.objects.create(
            user=self.user,
            product=self.product,
            configuration_json={},
        )
        self._put_draft_in_cart(draft)

        response = self.client.get(reverse("cart:detail"))

        self.assertContains(response, "Customized version")
        self.assertContains(
            response,
            reverse("customization:draft_detail", kwargs={"draft_id": draft.pk}),
        )


class AnonymousCartCustomizationTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            title="Canvas Tote",
            base_price="19.90",
            stock_quantity=5,
        )
        session = self.client.session
        session[CART_SESSION_KEY] = {
            line_key(self.product.pk): {
                "product_id": self.product.pk,
                "draft_id": None,
                "quantity": 1,
            }
        }
        session.save()

    def test_anonymous_shopper_is_redirected_to_login_before_customizing(self):
        response = self.client.get(reverse("cart:detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in to customize")
        self.assertContains(response, f"{reverse('account_login')}?next=")
