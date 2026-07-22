from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
import json
from decimal import Decimal
from .models import Cart, CartItem, Order, OrderItem, OrderStatusHistory, Coupon
from .cart_utils import get_or_create_cart
from products.models import Product, ProductVariant


# ── CART ─────────────────────────────────────────────────

def cart_view(request):
    cart = get_or_create_cart(request)
    items = cart.items.select_related('product', 'variant').prefetch_related('product__images')
    return render(request, 'orders/cart.html', {
        'cart': cart, 'items': items,
        'shipping_threshold': 2000,
        'shipping_fee': 0 if cart.total >= 2000 else 200,
    })


@require_POST
def cart_add(request):
    try:
        data       = json.loads(request.body)
        product_id = data.get('product_id')
        quantity   = int(data.get('quantity', 1))
        variant_id = data.get('variant_id')

        product = get_object_or_404(Product, id=product_id, is_active=True)
        variant = None
        if variant_id:
            variant = get_object_or_404(ProductVariant, id=variant_id, product=product)

        if not product.is_in_stock:
            return JsonResponse({'success': False, 'error': 'Product is out of stock.'})

        cart = get_or_create_cart(request)
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant,
            defaults={'quantity': quantity}
        )
        if not created:
            item.quantity = min(item.quantity + quantity, product.stock or 99)
            item.save()

        return JsonResponse({
            'success': True,
            'message': f'"{product.name}" added to cart!',
            'cart_count': cart.items_count,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
def cart_update(request):
    try:
        data     = json.loads(request.body)
        item_id  = data.get('item_id')
        quantity = int(data.get('quantity', 1))
        cart     = get_or_create_cart(request)
        item     = get_object_or_404(CartItem, id=item_id, cart=cart)

        if quantity <= 0:
            item.delete()
            msg = 'Item removed from cart.'
        else:
            item.quantity = quantity
            item.save()
            msg = 'Cart updated.'

        return JsonResponse({
            'success': True, 'message': msg,
            'cart_count': cart.items_count,
            'cart_total': float(cart.total),
            'subtotal': float(cart.subtotal),
            'item_total': float(item.line_total) if quantity > 0 else 0,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_POST
def cart_remove(request, item_id):
    cart = get_or_create_cart(request)
    item = get_object_or_404(CartItem, id=item_id, cart=cart)
    item.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'cart_count': cart.items_count, 'cart_total': float(cart.total)})
    messages.success(request, 'Item removed from cart.')
    return redirect('orders:cart')


@require_POST
def apply_coupon(request):
    code = request.POST.get('coupon_code', '').strip().upper()
    cart = get_or_create_cart(request)
    try:
        coupon = Coupon.objects.get(code=code)
        if not coupon.is_valid():
            return JsonResponse({'success': False, 'error': 'Coupon is expired or invalid.'})
        if cart.subtotal < coupon.min_order_value:
            return JsonResponse({'success': False, 'error': f'Minimum order value is KES {coupon.min_order_value}.'})
        cart.coupon = coupon
        cart.save()
        discount = coupon.calculate_discount(cart.subtotal)
        return JsonResponse({'success': True, 'message': f'Coupon applied! You save KES {discount:.0f}.',
                             'discount': float(discount), 'new_total': float(cart.total)})
    except Coupon.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid coupon code.'})


@require_POST
def remove_coupon(request):
    cart = get_or_create_cart(request)
    cart.coupon = None
    cart.save()
    return JsonResponse({'success': True, 'new_total': float(cart.total)})


# ── CHECKOUT ──────────────────────────────────────────────

def checkout(request):
    cart = get_or_create_cart(request)
    if not cart.items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('orders:cart')

    shipping_fee =Decimal('0') if cart.total >= Decimal('2000') else Decimal('200')
    tax_rate     = Decimal('0.16')  # 16% VAT Kenya
    tax_amount   = cart.total * tax_rate
    grand_total  = cart.total + shipping_fee + tax_amount

    addresses = []
    if request.user.is_authenticated:
        addresses = request.user.addresses.filter(address_type='shipping')

    if request.method == 'POST':
        return _process_checkout(request, cart, shipping_fee, tax_amount, grand_total)

    return render(request, 'orders/checkout.html', {
        'cart': cart,
        'items': cart.items.select_related('product').prefetch_related('product__images'),
        'addresses': addresses,
        'shipping_fee': shipping_fee,
        'tax_amount': tax_amount,
        'grand_total': grand_total,
        'stripe_public_key': __import__('django.conf', fromlist=['settings']).settings.STRIPE_PUBLIC_KEY,
    })


@transaction.atomic
def _process_checkout(request, cart, shipping_fee, tax_amount, grand_total):
    p = request.POST
    try:
        order = Order.objects.create(
            user           = request.user if request.user.is_authenticated else None,
            email          = p.get('email') or (request.user.email if request.user.is_authenticated else ''),
            phone          = p.get('phone', ''),
            shipping_name  = p.get('shipping_name', ''),
            shipping_line1 = p.get('shipping_line1', ''),
            shipping_line2 = p.get('shipping_line2', ''),
            shipping_city  = p.get('shipping_city', ''),
            shipping_state = p.get('shipping_state', ''),
            shipping_country=p.get('shipping_country', 'Kenya'),
            shipping_postal= p.get('shipping_postal', ''),
            subtotal       = cart.subtotal,
            discount_amount= cart.discount_amount,
            shipping_fee   = shipping_fee,
            tax_amount     = tax_amount,
            total          = grand_total,
            coupon_code    = cart.coupon.code if cart.coupon else '',
            notes          = p.get('notes', ''),
            payment_method = p.get('payment_method', ''),
        )
        for item in cart.items.select_related('product', 'variant'):
            OrderItem.objects.create(
                order        = order,
                product      = item.product,
                product_name = item.product.name,
                variant_info = f'{item.variant.name}: {item.variant.value}' if item.variant else '',
                sku          = item.product.sku,
                quantity     = item.quantity,
                unit_price   = item.unit_price,
                total_price  = item.line_total,
            )
            # Decrement stock
            Product.objects.filter(pk=item.product.pk).update(
                stock=max(item.product.stock - item.quantity, 0),
                purchase_count=item.product.purchase_count + item.quantity
            )
        OrderStatusHistory.objects.create(order=order, status='pending', note='Order placed')
        if cart.coupon:
            Coupon.objects.filter(pk=cart.coupon.pk).update(usage_count=cart.coupon.usage_count + 1)
        cart.items.all().delete()
        cart.coupon = None
        cart.save()
        request.session['last_order_id'] = str(order.id)
        return redirect('orders:order_summary', order_number=order.order_number)
    except Exception as e:
        messages.error(request, f'Order failed: {str(e)}')
        return redirect('orders:checkout')


def order_summary(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if order.user and order.user != request.user and not request.user.is_staff:
        messages.error(request, 'Access denied.')
        return redirect('products:home')
    return render(request, 'orders/order_summary.html', {
        'order': order,
        'items': order.items.select_related('product'),
    })


# ── ORDER HISTORY ─────────────────────────────────────────

@login_required
def order_history(request):
    orders = request.user.orders.prefetch_related('items').order_by('-created_at')
    return render(request, 'orders/order_history.html', {'orders': orders})


@login_required
def order_detail(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    return render(request, 'orders/order_detail.html', {
        'order': order,
        'items': order.items.select_related('product').prefetch_related('product__images'),
        'history': order.status_history.all(),
    })


@login_required
@require_POST
def cancel_order(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    if order.is_cancellable:
        order.status = 'cancelled'
        order.save()
        OrderStatusHistory.objects.create(order=order, status='cancelled',
                                           note='Cancelled by customer', changed_by=request.user)
        messages.success(request, f'Order #{order.order_number} has been cancelled.')
    else:
        messages.error(request, 'This order cannot be cancelled.')
    return redirect('orders:order_detail', order_number=order_number)


def track_order(request):
    order = None
    if request.method == 'POST':
        number = request.POST.get('order_number', '').strip()
        email  = request.POST.get('email', '').strip()
        try:
            order = Order.objects.get(order_number=number, email=email)
        except Order.DoesNotExist:
            messages.error(request, 'Order not found. Check your order number and email.')
    return render(request, 'orders/track_order.html', {'order': order})
