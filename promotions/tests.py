from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from cart.context import CART_SESSION_KEY, _build_cart_summary, line_key
from products.models import Product

from .models import Promotion, PromotionTier
from .services import (
    active_promotions_for,
    attach_promotion_badges,
    best_break,
    price_line,
)

User = get_user_model()


class PromotionFixtureMixin:
    """A EUR 10.00 product with the "5 for EUR 40 / 10 for EUR 70" ladder."""

    def create_fixture(self):
        self.product = Product.objects.create(
            title="Classic Tee",
            base_price=Decimal("10.00"),
            stock_quantity=50,
        )
        self.promotion = Promotion.objects.create(
            name="T-shirt bundle",
            product=self.product,
        )
        self.tier_5 = PromotionTier.objects.create(
            promotion=self.promotion,
            quantity=5,
            price=Decimal("40.00"),
        )
        self.tier_10 = PromotionTier.objects.create(
            promotion=self.promotion,
            quantity=10,
            price=Decimal("70.00"),
        )


class PriceLineTests(PromotionFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()

    def test_quantities_below_the_lowest_break_pay_the_base_price(self):
        pricing = price_line(self.product, 4)

        self.assertEqual(pricing.net_total, Decimal("40.00"))
        self.assertEqual(pricing.discount_total, Decimal("0.00"))
        self.assertIsNone(pricing.promotion)
        self.assertFalse(pricing.has_discount)

    def test_units_above_the_break_stay_at_the_base_price(self):
        pricing = price_line(self.product, 7)

        self.assertEqual(pricing.gross_total, Decimal("70.00"))
        self.assertEqual(pricing.net_total, Decimal("60.00"))
        self.assertEqual(pricing.discount_total, Decimal("10.00"))
        self.assertEqual(pricing.promotion, self.promotion)
        self.assertEqual(pricing.tier, self.tier_5)
        self.assertEqual(pricing.extra_units, 2)
        self.assertEqual(pricing.promotion_label, "T-shirt bundle · 5 for €40.00")

    def test_exactly_on_a_break_pays_the_break_price(self):
        self.assertEqual(price_line(self.product, 10).net_total, Decimal("70.00"))

    def test_the_biggest_affordable_break_wins(self):
        pricing = price_line(self.product, 10)

        self.assertEqual(pricing.tier, self.tier_10)
        self.assertEqual(pricing.discount_total, Decimal("30.00"))

    def test_a_long_line_reuses_the_biggest_break(self):
        pricing = price_line(self.product, 25)

        self.assertEqual(pricing.net_total, Decimal("220.00"))
        self.assertEqual(pricing.extra_units, 15)

    def test_the_cheapest_break_wins_between_two_promotions(self):
        flash = Promotion.objects.create(name="Flash deal", product=self.product)
        PromotionTier.objects.create(
            promotion=flash,
            quantity=5,
            price=Decimal("35.00"),
        )

        pricing = price_line(self.product, 7)

        self.assertEqual(pricing.promotion, flash)
        self.assertEqual(pricing.net_total, Decimal("55.00"))

    def test_inactive_promotions_are_ignored(self):
        self.promotion.is_active = False
        self.promotion.save(update_fields=["is_active"])

        pricing = price_line(self.product, 10)

        self.assertEqual(pricing.net_total, Decimal("100.00"))
        self.assertFalse(pricing.has_discount)

    def test_promotions_never_apply_to_another_product(self):
        other = Product.objects.create(
            title="Canvas Tote",
            base_price=Decimal("10.00"),
            stock_quantity=5,
        )

        self.assertEqual(price_line(other, 10).net_total, Decimal("100.00"))
        self.assertEqual(active_promotions_for([other.pk]), {})

    def test_best_break_ignores_quantities_below_one(self):
        self.assertIsNone(best_break(self.product, 0))

    def test_active_promotions_are_grouped_by_product(self):
        other = Product.objects.create(
            title="Canvas Tote",
            base_price=Decimal("10.00"),
            stock_quantity=5,
        )
        grouped = active_promotions_for([self.product.pk, other.pk])

        self.assertEqual(grouped[self.product.pk], [self.promotion])
        self.assertNotIn(other.pk, grouped)
        with self.assertNumQueries(0):
            for promotion in grouped[self.product.pk]:
                list(promotion.tiers.all())
class PromotionValidationTests(PromotionFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()

    def test_a_ladder_without_breaks_is_rejected(self):
        with self.assertRaisesMessage(
            ValidationError, "Add at least one quantity/price break."
        ):
            Promotion.validate_tiers([], self.product.base_price)

    def test_a_break_that_costs_as_much_as_the_base_price_is_rejected(self):
        with self.assertRaisesMessage(ValidationError, "is not a saving"):
            Promotion.validate_tiers([(2, Decimal("25.00"))], self.product.base_price)

    def test_totals_must_grow_with_the_quantity(self):
        with self.assertRaisesMessage(ValidationError, "must be higher"):
            Promotion.validate_tiers(
                [(5, Decimal("40.00")), (10, Decimal("35.00"))],
                self.product.base_price,
            )

    def test_the_unit_price_must_drop_on_a_bigger_break(self):
        with self.assertRaisesMessage(ValidationError, "must have a lower unit price"):
            Promotion.validate_tiers(
                [(5, Decimal("40.00")), (8, Decimal("65.00"))],
                self.product.base_price,
            )

    def test_a_valid_ladder_is_returned_sorted(self):
        tiers = Promotion.validate_tiers(
            [(10, Decimal("70.00")), (5, Decimal("40.00"))],
            self.product.base_price,
        )

        self.assertEqual(tiers, [(5, Decimal("40.00")), (10, Decimal("70.00"))])

    def test_a_tier_is_checked_against_its_siblings(self):
        tier = PromotionTier(
            promotion=self.promotion,
            quantity=8,
            price=Decimal("65.00"),
        )

        with self.assertRaisesMessage(ValidationError, "must have a lower unit price"):
            tier.full_clean()

    def test_a_break_is_unique_per_promotion(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PromotionTier.objects.create(
                promotion=self.promotion,
                quantity=5,
                price=Decimal("39.00"),
            )

    def test_a_break_price_must_be_positive(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PromotionTier.objects.create(
                promotion=self.promotion,
                quantity=20,
                price=Decimal("0.00"),
            )

    def test_the_unit_price_of_a_break_is_rounded_to_cents(self):
        tier = PromotionTier(quantity=3, price=Decimal("10.00"))

        self.assertEqual(tier.unit_price, Decimal("3.33"))


class PromotionAdminTests(PromotionFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()
        self.staff = User.objects.create_user(
            username="staff-user",
            password="secret",
            is_staff=True,
        )
        # ``is_staff`` alone opens the admin index, but the model pages also
        # need the model permissions.
        self.staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label__in=("products", "promotions")
            )
        )

    def _payload(self, **overrides):
        payload = {
            "name": "Hoodie pack",
            "product": self.product.pk,
            "is_active": "on",
            "tiers-TOTAL_FORMS": "1",
            "tiers-INITIAL_FORMS": "0",
            "tiers-MIN_NUM_FORMS": "1",
            "tiers-MAX_NUM_FORMS": "1000",
            "tiers-0-quantity": "5",
            "tiers-0-price": "40.00",
        }
        payload.update(overrides)
        return payload

    def test_staff_can_create_a_promotion_with_its_breaks(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("admin:promotions_promotion_add"),
            self._payload(),
        )

        self.assertEqual(response.status_code, 302)
        promotion = Promotion.objects.get(name="Hoodie pack")
        self.assertEqual(
            list(promotion.tiers.values_list("quantity", "price")),
            [(5, Decimal("40.00"))],
        )

    def test_a_promotion_without_breaks_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("admin:promotions_promotion_add"),
            self._payload(**{"tiers-TOTAL_FORMS": "0"}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add at least one quantity/price break.")
        self.assertFalse(Promotion.objects.filter(name="Hoodie pack").exists())

    def test_a_break_that_is_not_a_saving_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("admin:promotions_promotion_add"),
            self._payload(**{"tiers-0-quantity": "2", "tiers-0-price": "25.00"}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is not a saving")
        self.assertFalse(Promotion.objects.filter(name="Hoodie pack").exists())

    def test_the_product_change_page_links_its_promotions(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("admin:products_product_change", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "T-shirt bundle")
        self.assertContains(
            response,
            reverse("admin:promotions_promotion_change", args=[self.promotion.pk]),
        )

    def test_customers_cannot_open_the_promotion_admin(self):
        customer = User.objects.create_user(username="customer", password="secret")
        self.client.force_login(customer)

        response = self.client.post(
            reverse("admin:promotions_promotion_add"),
            self._payload(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("admin:login")))
        self.assertFalse(Promotion.objects.filter(name="Hoodie pack").exists())


class PromotionStorefrontTests(PromotionFixtureMixin, TestCase):
    def setUp(self):
        self.create_fixture()

    def _cart(self, quantity, product=None):
        product = product or self.product
        return {
            line_key(product.pk): {
                "product_id": product.pk,
                "quantity": quantity,
            }
        }

    def _put_in_cart(self, quantity):
        session = self.client.session
        session[CART_SESSION_KEY] = self._cart(quantity)
        session.save()

    def test_cart_summary_keeps_the_gross_and_the_saving(self):
        summary = _build_cart_summary(self._cart(7))
        item = summary["items"][0]

        self.assertEqual(item["unit_price"], Decimal("10.00"))
        self.assertEqual(item["gross_line_total"], Decimal("70.00"))
        self.assertEqual(item["line_total"], Decimal("60.00"))
        self.assertEqual(item["discount_total"], Decimal("10.00"))
        self.assertEqual(item["extra_units"], 2)
        self.assertEqual(item["promotion_label"], "T-shirt bundle · 5 for €40.00")
        self.assertEqual(summary["subtotal"], Decimal("70.00"))
        self.assertEqual(summary["total"], Decimal("60.00"))
        self.assertEqual(summary["discount_total"], Decimal("10.00"))

    def test_cart_lines_are_priced_one_by_one(self):
        cart = {
            line_key(self.product.pk, "draft-a"): {
                "product_id": self.product.pk,
                "draft_id": "draft-a",
                "quantity": 4,
            },
            line_key(self.product.pk, "draft-b"): {
                "product_id": self.product.pk,
                "draft_id": "draft-b",
                "quantity": 4,
            },
        }

        summary = _build_cart_summary(cart)

        self.assertEqual(summary["total"], Decimal("80.00"))
        self.assertEqual(summary["discount_total"], Decimal("0.00"))

    def test_cart_pricing_costs_three_queries(self):
        with self.assertNumQueries(3):
            _build_cart_summary(self._cart(7))

    def test_cart_page_shows_the_break_and_the_saving(self):
        self._put_in_cart(7)

        response = self.client.get(reverse("cart:detail"))

        self.assertContains(response, "T-shirt bundle · 5 for €40.00")
        self.assertContains(response, "You save &euro; 10.00")
        self.assertContains(response, "&euro; 70.00")

    def test_cart_page_without_a_break_shows_no_saving(self):
        self._put_in_cart(3)

        response = self.client.get(reverse("cart:detail"))

        self.assertNotContains(response, "You save")
        self.assertContains(response, "&euro; 30.00")

    def test_catalogue_card_teases_the_best_break(self):
        response = self.client.get(reverse("products:list"))

        self.assertContains(response, "T-shirt bundle: 10 for €70.00")

    def test_home_page_card_teases_the_best_break(self):
        response = self.client.get(reverse("home:index"))

        self.assertContains(response, "T-shirt bundle: 10 for €70.00")

    def test_inactive_promotions_are_hidden_from_the_catalogue(self):
        self.promotion.is_active = False
        self.promotion.save(update_fields=["is_active"])

        response = self.client.get(reverse("products:list"))

        self.assertNotContains(response, "T-shirt bundle")

    def test_catalogue_badges_need_one_promotion_query_per_page(self):
        products = list(Product.objects.filter(pk=self.product.pk))

        with self.assertNumQueries(2):
            attach_promotion_badges(products)

        self.assertEqual(products[0].promotion_name, "T-shirt bundle")
        self.assertEqual(products[0].promotion_teaser, "10 for €70.00")

    def test_products_without_a_promotion_get_an_empty_badge(self):
        other = Product.objects.create(
            title="Canvas Tote",
            base_price=Decimal("10.00"),
            stock_quantity=5,
        )

        attach_promotion_badges([other])

        self.assertEqual(other.promotion_name, "")
        self.assertEqual(other.promotion_teaser, "")

class PromotionStaffPageTests(PromotionFixtureMixin, TestCase):
    """The staff pages of /promotions/ (the admin has its own suite above)."""

    def setUp(self):
        self.create_fixture()
        self.staff = User.objects.create_user(
            username="staff-user",
            password="secret",
            is_staff=True,
        )
        self.customer = User.objects.create_user(
            username="customer",
            password="secret",
        )
        self.second_product = Product.objects.create(
            title="Canvas Tote",
            base_price=Decimal("20.00"),
            stock_quantity=4,
        )

    def _create_payload(self, **overrides):
        payload = {
            "name": "Tote bundle",
            "product": self.second_product.pk,
            "is_active": "on",
            "tiers-TOTAL_FORMS": "2",
            "tiers-INITIAL_FORMS": "0",
            "tiers-MIN_NUM_FORMS": "1",
            "tiers-MAX_NUM_FORMS": "1000",
            "tiers-0-quantity": "3",
            "tiers-0-price": "50.00",
            "tiers-1-quantity": "6",
            "tiers-1-price": "90.00",
        }
        payload.update(overrides)
        return payload

    def _edit_payload(self, **overrides):
        payload = {
            "name": "T-shirt bundle",
            "product": self.product.pk,
            "is_active": "on",
            "tiers-TOTAL_FORMS": "2",
            "tiers-INITIAL_FORMS": "2",
            "tiers-MIN_NUM_FORMS": "1",
            "tiers-MAX_NUM_FORMS": "1000",
            "tiers-0-id": str(self.tier_5.pk),
            "tiers-0-quantity": "5",
            "tiers-0-price": "38.00",
            "tiers-1-id": str(self.tier_10.pk),
            "tiers-1-quantity": "10",
            "tiers-1-price": "70.00",
        }
        payload.update(overrides)
        return payload

    def _pages(self):
        return (
            reverse("promotions:list"),
            reverse("promotions:create"),
            reverse("promotions:detail", args=[self.promotion.pk]),
        )

    def test_anonymous_visitors_are_sent_to_the_login_page(self):
        for url in self._pages():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("account_login"), response["Location"])

    def test_customers_are_refused(self):
        self.client.force_login(self.customer)

        for url in self._pages():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

        response = self.client.post(
            reverse("promotions:delete", args=[self.promotion.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Promotion.objects.filter(pk=self.promotion.pk).exists())

    def test_the_list_shows_the_ladder_and_the_status(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("promotions:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "T-shirt bundle")
        self.assertContains(response, "5 for EUR 40.00")
        self.assertContains(response, "Classic Tee")

    def test_the_list_can_be_searched_and_filtered(self):
        self.client.force_login(self.staff)

        by_name = self.client.get(reverse("promotions:list"), {"q": "canvas"})
        self.assertNotContains(by_name, "T-shirt bundle")
        self.assertContains(by_name, "No promotion matches this filter")

        inactive = self.client.get(reverse("promotions:list"), {"status": "inactive"})
        self.assertNotContains(inactive, "T-shirt bundle")

        active = self.client.get(reverse("promotions:list"), {"status": "active"})
        self.assertContains(active, "T-shirt bundle")



    def test_staff_can_create_a_promotion_with_its_ladder(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("promotions:create"),
            self._create_payload(),
        )

        promotion = Promotion.objects.get(name="Tote bundle")
        self.assertRedirects(
            response,
            reverse("promotions:detail", args=[promotion.pk]),
        )
        self.assertEqual(promotion.product, self.second_product)
        self.assertEqual(
            list(promotion.tiers.values_list("quantity", "price")),
            [(3, Decimal("50.00")), (6, Decimal("90.00"))],
        )

    def test_the_product_query_parameter_prefills_the_new_promotion(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("promotions:create"),
            {"product": self.second_product.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'<option value="{self.second_product.pk}" selected>',
        )
        self.assertContains(response, 'value="Canvas Tote bundle"')
        # The product of the existing promotion is flagged in the select.
        self.assertContains(response, "already promoted")

    def test_a_ladder_that_is_not_a_saving_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("promotions:create"),
            self._create_payload(**{"tiers-0-price": "100.00"}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is not a saving")
        self.assertFalse(Promotion.objects.filter(name="Tote bundle").exists())

    def test_a_ladder_without_breaks_is_rejected(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("promotions:create"),
            self._create_payload(
                **{
                    "tiers-TOTAL_FORMS": "1",
                    "tiers-0-quantity": "",
                    "tiers-0-price": "",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add at least one quantity/price break")
        self.assertFalse(Promotion.objects.filter(name="Tote bundle").exists())

    def test_staff_can_edit_a_break_and_delete_another(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("promotions:detail", args=[self.promotion.pk]),
            self._edit_payload(**{"tiers-1-DELETE": "on"}),
        )

        self.assertRedirects(
            response,
            reverse("promotions:detail", args=[self.promotion.pk]),
        )
        self.promotion.refresh_from_db()
        self.assertEqual(self.promotion.name, "T-shirt bundle")
        self.assertEqual(self.promotion.tiers.count(), 1)
        self.assertEqual(self.promotion.tiers.get().price, Decimal("38.00"))

    def test_the_detail_page_shows_the_saved_ladder_and_the_delete_dialog(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("promotions:detail", args=[self.promotion.pk])
        )

        self.assertContains(response, "Saved ladder")
        self.assertContains(response, "20% cheaper")
        self.assertContains(response, "30% cheaper")
        self.assertContains(response, "delete-promotion-modal")

    def test_staff_can_delete_a_promotion(self):
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("promotions:delete", args=[self.promotion.pk])
        )

        self.assertRedirects(response, reverse("promotions:list"))
        self.assertFalse(Promotion.objects.filter(pk=self.promotion.pk).exists())
        # The product goes back to its base price everywhere.
        self.assertEqual(price_line(self.product, 5).net_total, Decimal("50.00"))

    def test_deleting_requires_a_post(self):
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse("promotions:delete", args=[self.promotion.pk])
        )

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Promotion.objects.filter(pk=self.promotion.pk).exists())
