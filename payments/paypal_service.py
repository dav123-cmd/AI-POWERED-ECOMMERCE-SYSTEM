"""
ShopAI — PayPal Payment Service
Uses PayPal REST SDK
"""
import paypalrestsdk
from django.conf import settings
from django.utils import timezone
from .models import Payment

paypalrestsdk.configure({
    'mode':         settings.PAYPAL_MODE,
    'client_id':    settings.PAYPAL_CLIENT_ID,
    'client_secret':settings.PAYPAL_CLIENT_SECRET,
})


def create_paypal_order(order, return_url, cancel_url):
    """Create a PayPal payment."""
    payment = paypalrestsdk.Payment({
        'intent': 'sale',
        'payer': {'payment_method': 'paypal'},
        'redirect_urls': {'return_url': return_url, 'cancel_url': cancel_url},
        'transactions': [{
            'item_list': {
                'items': [{
                    'name':     item.product_name,
                    'sku':      item.sku,
                    'price':    str(item.unit_price),
                    'currency': 'USD',
                    'quantity': item.quantity,
                } for item in order.items.all()]
            },
            'amount': {
                'total':    str(round(float(order.total) / 130, 2)),  # KES to USD approx
                'currency': 'USD',
            },
            'description': f'ShopAI Order {order.order_number}',
        }]
    })

    if payment.create():
        db_payment = Payment.objects.create(
            order              = order,
            user               = order.user,
            method             = 'paypal',
            amount             = order.total,
            currency           = 'KES',
            gateway_payment_id = payment.id,
            gateway_order_id   = payment.id,
        )
        approval_url = next(l.href for l in payment.links if l.rel == 'approval_url')
        return approval_url, db_payment
    else:
        raise Exception(f'PayPal error: {payment.error}')


def execute_paypal_payment(payment_id, payer_id):
    """Execute an approved PayPal payment."""
    pp_payment = paypalrestsdk.Payment.find(payment_id)
    if pp_payment.execute({'payer_id': payer_id}):
        try:
            db_payment = Payment.objects.get(gateway_payment_id=payment_id)
            db_payment.status       = 'completed'
            db_payment.completed_at = timezone.now()
            db_payment.gateway_response = {'payer_id': payer_id, 'state': pp_payment.state}
            db_payment.save()
            db_payment.order.payment_status = 'paid'
            db_payment.order.status         = 'confirmed'
            db_payment.order.save(update_fields=['payment_status', 'status'])
            return db_payment
        except Payment.DoesNotExist:
            return None
    return None
