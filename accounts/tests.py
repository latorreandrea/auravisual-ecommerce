from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class AuthenticationAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="artist",
            email="artist@example.com",
            password="s3cret-pass",
        )

    def login_url(self, next_url):
        return f"{reverse('account_login')}?{urlencode({'next': next_url})}"

    def test_customization_login_page_invites_registration(self):
        next_url = reverse("customization:list")

        response = self.client.get(self.login_url(next_url))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in to customize")
        self.assertContains(response, "New here? Create a free account")
        self.assertContains(response, "Create a free account")
        self.assertContains(response, 'name="next"')
        self.assertContains(response, f'href="{reverse("account_signup")}?next=')

    def test_regular_login_page_has_no_customization_invite(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, "Sign in to customize")
        self.assertNotContains(response, "New here? Create a free account")

    def test_login_redirects_to_customization_next_url(self):
        next_url = reverse("customization:list")

        response = self.client.post(
            reverse("account_login"),
            {
                "login": "artist",
                "password": "s3cret-pass",
                "next": next_url,
            },
        )

        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_signup_page_preserves_customization_context(self):
        next_url = reverse("customization:list")

        response = self.client.get(
            f"{reverse('account_signup')}?{urlencode({'next': next_url})}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create your account")
        self.assertContains(
            response,
            "Sign up to customize products and keep your designs saved to your account.",
        )
        self.assertContains(response, 'name="next"')
        self.assertContains(response, f'href="{reverse("account_login")}?next=')

    def test_signup_redirects_to_customization_next_url(self):
        next_url = reverse("customization:list")
        payload = {
            "email": "new-artist@example.com",
            "username": "new-artist",
            "password1": "V3ry-Str0ng-Pass!",
            "password2": "V3ry-Str0ng-Pass!",
            "next": next_url,
        }

        response = self.client.post(reverse("account_signup"), payload)

        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="new-artist").exists())


class AdminAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer",
            password="s3cret-pass",
        )
        self.staff_user = User.objects.create_user(
            username="manager",
            password="s3cret-pass",
            is_staff=True,
        )

    def test_staff_can_open_admin_and_regular_user_cannot(self):
        self.client.force_login(self.staff_user)
        staff_response = self.client.get(reverse("admin:index"))
        self.assertEqual(staff_response.status_code, 200)

        self.client.force_login(self.user)
        customer_response = self.client.get(reverse("admin:index"))
        self.assertEqual(customer_response.status_code, 302)
        self.assertTrue(customer_response.url.startswith(reverse("admin:login")))

    def test_admin_link_is_only_rendered_for_staff(self):
        self.client.force_login(self.user)
        customer_response = self.client.get(reverse("products:list"))
        self.assertNotContains(customer_response, f'href="{reverse("admin:index")}"')

        self.client.force_login(self.staff_user)
        staff_response = self.client.get(reverse("products:list"))
        self.assertContains(staff_response, f'href="{reverse("admin:index")}"')
