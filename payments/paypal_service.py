"""
ShopAI — PayPal Payment Service
Uses PayPal REST SDK
"""
import paypalrestsdk
from django.conf import settings
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP
from .models import Payment

paypalrestsdk.configure({
    'mode':         settings.PAYPAL_MODE,
    'client_id':    settings.PAYPAL_CLIENT_ID,
    'client_secret':settings.PAYPAL_CLIENT_SECRET,
})


def _format_usd(amount):
    return str(Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _build_paypal_items(order, subtotal_usd):
    items = []
    total_kes = Decimal('0')
    for item in order.items.all():
        total_kes += Decimal(item.unit_price) * item.quantity

    if total_kes == 0:
        return []

    remaining_usd = Decimal(subtotal_usd)
    line_items = []
    for item in order.items.all():
        line_kes = Decimal(item.unit_price) * item.quantity
        line_usd = (line_kes * subtotal_usd / total_kes).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        line_items.append((item, line_usd))
        remaining_usd -= line_usd

    # Adjust final line item for rounding
    if line_items and remaining_usd != 0:
        last_item, last_amount = line_items[-1]
        line_items[-1] = (last_item, last_amount + remaining_usd)

    for item, line_usd in line_items:
        unit_price = (line_usd / item.quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        items.append({
            'name':     item.product_name,
            'sku':      item.sku,
            'price':    _format_usd(unit_price),
            'currency': 'USD',
            'quantity': item.quantity,
        })
    return items


def create_paypal_order(order, return_url, cancel_url):
    """Create a PayPal payment."""
    conversion_rate = Decimal('130')
    total_usd = (Decimal(order.total) / conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    shipping_usd = (Decimal(order.shipping_fee) / conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    tax_usd = (Decimal(order.tax_amount) / conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    discount_usd = (Decimal(order.discount_amount) / conversion_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    subtotal_usd = (total_usd - shipping_usd - tax_usd).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if subtotal_usd < 0:
        subtotal_usd = Decimal('0.00')

    payment = paypalrestsdk.Payment({
        'intent': 'sale',
        'payer': {'payment_method': 'paypal'},
        'redirect_urls': {'return_url': return_url, 'cancel_url': cancel_url},
        'transactions': [{
            'item_list': {
                'items': _build_paypal_items(order, subtotal_usd)
            },
            'amount': {
                'total':    _format_usd(total_usd),
                'currency': 'USD',
                'details': {
                    'subtotal': _format_usd(subtotal_usd),
                    'shipping': _format_usd(shipping_usd),
                    'tax':      _format_usd(tax_usd),
                }
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
