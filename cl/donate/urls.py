from django.urls import path

from cl.donate.stripe_helpers import process_stripe_callback
from cl.donate.views import payment_complete

urlpatterns = [
    path(
        "donate/complete/",
        payment_complete,
        {"template_name": "donate_complete.html"},
        name="donate_complete",
    ),
    # Stripe
    path(
        "donate/callbacks/stripe/",
        process_stripe_callback,
        name="stripe_callback",
    ),
]
