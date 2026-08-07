"""
ShopAI — M-Pesa STK Push Service (Safaricom Daraja API)
"""
import requests
import base64
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from .models import Payment


def _get_access_token():
    url  = 'https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    if settings.MPESA_ENVIRONMENT == 'production':
        url = 'https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials'
    # Basic validation for credentials to give clearer error messages
    if not settings.MPESA_CONSUMER_KEY or not settings.MPESA_CONSUMER_SECRET:
        raise RuntimeError('MPESA_CONSUMER_KEY or MPESA_CONSUMER_SECRET not configured')
    resp = requests.get(url, auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET), timeout=10)
    data = resp.json()
    token = data.get('access_token')
    if not token:
        raise RuntimeError(f'Failed to obtain M-Pesa access token: {data}')
    return token


def _get_password():
    ts       = datetime.now().strftime('%Y%m%d%H%M%S')
    raw      = settings.MPESA_SHORTCODE + settings.MPESA_PASSKEY + ts
    password = base64.b64encode(raw.encode()).decode()
    return password, ts


def stk_push(order, phone_number):
    """
    Initiate STK Push — sends payment prompt to customer's phone.
    Phone format: 2547XXXXXXXX
    """
    token         = _get_access_token()
    password, ts  = _get_password()
    amount        = int(order.total)
    # Allow overriding the callback URL from settings (useful for production/ngrok)
    callback_url = getattr(settings, 'MPESA_CALLBACK_URL', '') or f'https://yourdomain.com/payments/mpesa/callback/'
    base_url      = 'https://sandbox.safaricom.co.ke' if settings.MPESA_ENVIRONMENT == 'sandbox' \
                    else 'https://api.safaricom.co.ke'

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password':          password,
        'Timestamp':         ts,
        'TransactionType':   'CustomerPayBillOnline',
        'Amount':            amount,
        'PartyA':            phone_number,
        'PartyB':            settings.MPESA_SHORTCODE,
        'PhoneNumber':       phone_number,
        'CallBackURL':       callback_url,
        'AccountReference':  order.order_number,
        'TransactionDesc':   f'Payment for ShopAI order {order.order_number}',
    }

    resp = requests.post(
        f'{base_url}/mpesa/stkpush/v1/processrequest',
        json    = payload,
        headers = {'Authorization': f'Bearer {token}'},
    )
    data = resp.json()

    db_payment = Payment.objects.create(
        order              = order,
        user               = order.user,
        method             = 'mpesa',
        amount             = order.total,
        currency           = 'KES',
        mpesa_phone        = phone_number,
        mpesa_checkout_id  = data.get('CheckoutRequestID', ''),
        gateway_payment_id = data.get('CheckoutRequestID', ''),
        gateway_response   = data,
    )

    if data.get('ResponseCode') == '0':
        return {'success': True, 'checkout_id': data['CheckoutRequestID'], 'payment': db_payment}
    return {'success': False, 'error': data.get('errorMessage', 'STK Push failed'), 'payment': db_payment}


def handle_mpesa_callback(data):
    """Process M-Pesa callback from Safaricom."""
    body      = data.get('Body', {}).get('stkCallback', {})
    checkout_id = body.get('CheckoutRequestID')
    result_code = body.get('ResultCode')

    try:
        payment = Payment.objects.get(mpesa_checkout_id=checkout_id)
        payment.gateway_response = data

        if result_code == 0:
            # Success — extract receipt
            meta  = body.get('CallbackMetadata', {}).get('Item', [])
            meta_dict = {i['Name']: i.get('Value') for i in meta}
            payment.status         = 'completed'
            payment.completed_at   = timezone.now()
            payment.mpesa_receipt  = meta_dict.get('MpesaReceiptNumber', '')
            payment.save()
            payment.order.payment_status = 'paid'
            payment.order.status         = 'confirmed'
            payment.order.save(update_fields=['payment_status', 'status'])
        else:
            payment.status         = 'failed'
            payment.failure_reason = body.get('ResultDesc', '')
            payment.save()
        return payment
    except Payment.DoesNotExist:
        return None


def query_stk_status(checkout_id):
    """Query STK push transaction status."""
    token        = _get_access_token()
    password, ts = _get_password()
    base_url     = 'https://sandbox.safaricom.co.ke' if settings.MPESA_ENVIRONMENT == 'sandbox' \
                   else 'https://api.safaricom.co.ke'
    resp = requests.post(
        f'{base_url}/mpesa/stkpushquery/v1/query',
        json = {
            'BusinessShortCode': settings.MPESA_SHORTCODE,
            'Password': password, 'Timestamp': ts,
            'CheckoutRequestID': checkout_id,
        },
        headers = {'Authorization': f'Bearer {token}'},
    )
    return resp.json()
