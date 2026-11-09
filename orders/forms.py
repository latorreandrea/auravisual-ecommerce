from django import forms

from accounts.models import ShippingAddress
from products.forms import BootstrapFormMixin


class CheckoutForm(BootstrapFormMixin, forms.ModelForm):
    """Shipping details collected at checkout.

    A new ``ShippingAddress`` row is created for every order, so the customer's
    address history stays intact when an order is shipped to a different place.
    """

    class Meta:
        model = ShippingAddress
        fields = ("full_name", "line_1", "line_2", "city", "postal_code", "country")
        labels = {
            "full_name": "Full name",
            "line_1": "Address",
            "line_2": "Apartment, suite, etc. (optional)",
            "city": "City",
            "postal_code": "Postal code",
            "country": "Country",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "line_1": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "line_2": forms.TextInput(attrs={"autocomplete": "address-line2"}),
            "city": forms.TextInput(attrs={"autocomplete": "address-level2"}),
            "postal_code": forms.TextInput(attrs={"autocomplete": "postal-code"}),
            "country": forms.TextInput(attrs={"autocomplete": "country-name"}),
        }
