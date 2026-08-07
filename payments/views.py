from django.shortcuts import render

# Create your views here.
"""
ShopAI — Payments Views
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone

from orders.models import Order
from .models import Payment, Refund, Invoice
from .stripe_service import create_payment_intent, confirm_payment, handle_webhook, process_refund as stripe_refund
from .paypal_service import create_paypal_order, execute_paypal_payment
from .mpesa_service import stk_push, handle_mpesa_callback, query_stk_status
from .invoice_service import create_and_save_invoice
from django.conf import settings


# ── PAYMENT PAGE ──────────────────────────────────────────

def payment_page(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if order.payment_status == 'paid':
        return redirect('payments:success', order_number=order_number)

    requested_method = request.GET.get('method')
    if requested_method in ['stripe', 'paypal', 'mpesa'] and order.payment_method != requested_method:
        order.payment_method = requested_method
        order.save(update_fields=['payment_method'])

    context = {'order': order, 'stripe_public_key': settings.STRIPE_PUBLIC_KEY}

    if order.payment_method == 'stripe':
        intent, payment = create_payment_intent(order)
        context['client_secret'] = intent['client_secret']
        context['payment'] = payment

    elif order.payment_method == 'paypal':
        return_url = request.build_absolute_uri(f'/payments/paypal/execute/?order={order_number}')
        cancel_url = request.build_absolute_uri(f'/payments/cancel/{order_number}/')
        try:
            approval_url, payment = create_paypal_order(order, return_url, cancel_url)
            return redirect(approval_url)
        except Exception as e:
            messages.error(request, f'PayPal error: {str(e)}')
            return redirect('orders:checkout')

    elif order.payment_method == 'mpesa':
        context['mpesa'] = True

    return render(request, 'payments/payment_page.html', context)


# ── STRIPE ────────────────────────────────────────────────

@require_POST
def stripe_confirm(request):
    """Called after Stripe.js confirms the payment."""
    data      = json.loads(request.body)
    intent_id = data.get('payment_intent_id')
    payment   = confirm_payment(intent_id)
    if payment and payment.status == 'completed':
        return JsonResponse({'success': True, 'redirect': f'/payments/success/{payment.order.order_number}/'})
    return JsonResponse({'success': False, 'error': 'Payment failed. Please try again.'})


@csrf_exempt
def stripe_webhook(request):
    """Stripe webhook endpoint."""
    event = handle_webhook(request.body, request.META.get('HTTP_STRIPE_SIGNATURE', ''))
    if event is None:
        return HttpResponseBadRequest()
    return HttpResponse(status=200)


# ── PAYPAL ────────────────────────────────────────────────

def paypal_execute(request):
    """PayPal redirects here after approval."""
    payment_id   = request.GET.get('paymentId')
    payer_id     = request.GET.get('PayerID')
    order_number = request.GET.get('order')
    payment      = execute_paypal_payment(payment_id, payer_id)
    if payment:
        messages.success(request, 'Payment successful! ')
        return redirect('payments:success', order_number=order_number)
    messages.error(request, 'PayPal payment failed.')
    return redirect('payments:failed', order_number=order_number)


# ── M-PESA ────────────────────────────────────────────────

@require_POST
def mpesa_initiate(request, order_number):
    """Initiate M-Pesa STK push."""
    order  = get_object_or_404(Order, order_number=order_number)
    phone  = request.POST.get('mpesa_phone', '').strip().replace(' ', '').replace('+', '')
    # Normalize: 0712345678 → 254712345678
    if phone.startswith('0'):
        phone = '254' + phone[1:]
    if not phone.startswith('254') or len(phone) != 12:
        return JsonResponse({'success': False, 'error': 'Invalid phone number. Use format: 0712345678'})
    result = stk_push(order, phone)
    return JsonResponse({
        'success': result['success'],
        'checkout_id': result.get('checkout_id', ''),
        'error': result.get('error', ''),
        'message': 'STK Push sent! Check your phone and enter your M-Pesa PIN.' if result['success'] else '',
    })


@require_POST
def mpesa_query(request):
    """Poll M-Pesa payment status."""
    checkout_id = request.POST.get('checkout_id')
    try:
        payment = Payment.objects.get(mpesa_checkout_id=checkout_id)
        return JsonResponse({
            'status': payment.status,
            'receipt': payment.mpesa_receipt,
            'redirect': f'/payments/success/{payment.order.order_number}/' if payment.status == 'completed' else None,
        })
    except Payment.DoesNotExist:
        return JsonResponse({'status': 'pending'})


@csrf_exempt
def mpesa_callback(request):
    """Safaricom sends payment result here."""
    try:
        data = json.loads(request.body)
        handle_mpesa_callback(data)
    except Exception:
        pass
    return HttpResponse(status=200)


# ── SUCCESS / FAILURE ─────────────────────────────────────

def payment_success(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    # Auto-generate invoice
    try:
        if not hasattr(order, 'invoice') or not order.invoice.pdf_file:
            create_and_save_invoice(order)
    except Exception:
        pass
    return render(request, 'payments/payment_success.html', {'order': order})


def payment_failed(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return render(request, 'payments/payment_failed.html', {'order': order})


def payment_cancel(request, order_number):
    messages.warning(request, 'Payment was cancelled.')
    return redirect('orders:checkout')


# ── INVOICE ───────────────────────────────────────────────

@login_required
def download_invoice(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if order.user != request.user and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('products:home')

    try:
        invoice = order.invoice
        if not invoice.pdf_file:
            create_and_save_invoice(order)
            invoice.refresh_from_db()
        response = HttpResponse(invoice.pdf_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        return response
    except Invoice.DoesNotExist:
        invoice = create_and_save_invoice(order)
        response = HttpResponse(invoice.pdf_file.read(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{invoice.invoice_number}.pdf"'
        return response


# ── REFUND REQUEST ────────────────────────────────────────

@login_required
@require_POST
def request_refund(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.payment_status != 'paid':
        return JsonResponse({'success': False, 'error': 'Order has not been paid.'})

    payment = order.payments.filter(status='completed').first()
    if not payment:
        return JsonResponse({'success': False, 'error': 'No completed payment found.'})

    reason = request.POST.get('reason', 'other')
    desc   = request.POST.get('description', '')

    if Refund.objects.filter(order=order, status__in=['pending','approved','processed']).exists():
        return JsonResponse({'success': False, 'error': 'Refund already requested.'})

    Refund.objects.create(
        payment=payment, order=order, user=request.user,
        amount=order.total, reason=reason, description=desc,
    )
    messages.success(request, 'Refund request submitted. We will process it within 3-5 business days.')
    return JsonResponse({'success': True, 'message': 'Refund request submitted successfully.'})
