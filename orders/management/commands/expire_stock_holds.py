"""Release the stock holds that outlived their reservation window.

Today the storefront commits its stock as soon as an order is placed, so this
command has nothing to do. It becomes part of the checkout once Stripe is wired
in: a customer who opens the payment page and never pays must not keep the units
hostage. Run it from cron (or a Celery beat task) every few minutes::

    python manage.py expire_stock_holds --dry-run
    python manage.py expire_stock_holds
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from orders.models import Order
from orders.services import expired_holds, release_stock


class Command(BaseCommand):
    help = "Release stock held by orders whose payment never completed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the expired holds without touching the stock.",
        )

    def handle(self, *args, **options):
        orders = expired_holds()
        count = orders.count()
        if not count:
            self.stdout.write("No expired stock holds.")
            return

        if options["dry_run"]:
            self.stdout.write(f"{count} expired hold(s) would be released:")
            for order in orders:
                self.stdout.write(
                    f"  order #{order.pk} (reserved until {order.reserved_until})"
                )
            return

        for order in orders:
            release_stock(order)
            # The hold expired: the payment never arrived, so the order is dead.
            Order.objects.filter(pk=order.pk, payment_status=Order.PaymentStatus.UNPAID).update(
                payment_status=Order.PaymentStatus.FAILED
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Released {count} expired stock hold(s) at {timezone.now():%Y-%m-%d %H:%M}."
            )
        )
