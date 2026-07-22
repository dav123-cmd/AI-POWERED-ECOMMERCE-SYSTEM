"""
ShopAI — Stripe Payment Service
"""
import stripe
from django.conf import settings
from django.utils import timezone
from .models import Payment

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_payment_intent(order):
    """Create a Stripe PaymentIntent for the order."""
    amount_cents = int(order.total * 100)
    intent = stripe.PaymentIntent.create(
        amount      = amount_cents,
        currency    = 'kes',
        metadata    = {'order_id': str(order.id), 'order_number': order.order_number},
        description = f'ShopAI Order {order.order_number}',
    )
    payment = Payment.objects.create(
        order              = order,
        user               = order.user,
        method             = 'stripe',
        amount             = order.total,
        currency           = 'KES',
        gateway_payment_id = intent['id'],
        gateway_response   = {'client_secret': intent['client_secret']},
    )
    return intent, payment


def confirm_payment(payment_intent_id):
    """Retrieve and confirm a PaymentIntent."""
    intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    try:
        payment = Payment.objects.get(gateway_payment_id=payment_intent_id)
        if intent['status'] == 'succeeded':
            payment.status       = 'completed'
            payment.completed_at = timezone.now()
            payment.gateway_response = dict(intent)
            payment.save()
            # Update order
            payment.order.payment_status = 'paid'
            payment.order.status         = 'confirmed'
            payment.order.save(update_fields=['payment_status', 'status'])
        elif intent['status'] in ('canceled', 'payment_failed'):
            payment.status         = 'failed'
            payment.failure_reason = intent.get('last_payment_error', {}).get('message', '')
            payment.save()
        return payment
    except Payment.DoesNotExist:
        return None


def handle_webhook(payload, sig_header):
    """Process Stripe webhook events."""
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return None

    if event['type'] == 'payment_intent.succeeded':
        confirm_payment(event['data']['object']['id'])
    elif event['type'] == 'charge.dispute.created':
        # Handle chargeback
        pass
    return event


def process_refund(payment, amount, reason='requested_by_customer'):
    """Issue a Stripe refund."""
    refund = stripe.Refund.create(
        payment_intent = payment.gateway_payment_id,
        amount         = int(amount * 100),
        reason         = reason,
    )
    return refund
