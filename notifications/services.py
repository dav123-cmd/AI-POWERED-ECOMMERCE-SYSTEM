"""
ShopAI — Notification Service Layer
Other apps call notify_user() / notify_staff() rather than touching the model directly.
Keeps creation logic + email dispatch in one place.
"""
from django.conf import settings


# ── Category presets: default icon + level ───────────────

PRESETS = {
    'order':    {'icon': 'Order', 'level': 'info'},
    'payment':  {'icon': 'Payment', 'level': 'success'},
    'shipping': {'icon': 'Shipping', 'level': 'info'},
    'promo':    {'icon': 'Promo', 'level': 'info'},
    'review':   {'icon': 'Star', 'level': 'info'},
    'wishlist': {'icon': 'Wishlist', 'level': 'info'},
    'chat':     {'icon': 'Chat', 'level': 'info'},
    'ai':       {'icon': 'Brain', 'level': 'info'},
    'account':  {'icon': 'Acc', 'level': 'info'},
    'system':   {'icon': 'System', 'level': 'info'},
}


def notify_user(user, title, message='', category='system', level=None,
                 icon=None, link='', object_type='', object_id='', send_email=False):
    """
    Create an in-app notification for a single user.
    Optionally triggers an email based on user preference + send_email flag.
    """
    from .models import Notification

    preset = PRESETS.get(category, {})
    notif = Notification.objects.create(
        user        = user,
        category    = category,
        level       = level or preset.get('level', 'info'),
        title       = title,
        message     = message,
        icon        = icon or preset.get('icon', 'fas fa-bell'),
        link        = link,
        object_type = object_type,
        object_id   = str(object_id) if object_id else '',
    )

    if send_email:
        _maybe_send_email(notif)

    return notif


def notify_users(users, title, message='', category='system', **kwargs):
    """Bulk create the same notification for many users (e.g. promo blast)."""
    from .models import Notification
    preset = PRESETS.get(category, {})
    objs = [
        Notification(
            user=u, category=category,
            level=kwargs.get('level') or preset.get('level', 'info'),
            title=title, message=message,
            icon=kwargs.get('icon') or preset.get('icon', 'fas fa-bell'),
            link=kwargs.get('link', ''),
            object_type=kwargs.get('object_type', ''),
            object_id=str(kwargs.get('object_id', '')),
        ) for u in users
    ]
    return Notification.objects.bulk_create(objs)


def notify_staff(title, message='', category='system', level='warning', icon=None, link=''):
    """Notify all staff/admin users — used for fraud alerts, low stock, etc."""
    from django.contrib.auth import get_user_model
    User  = get_user_model()
    staff = User.objects.filter(is_staff=True, is_active=True)
    return notify_users(staff, title, message, category=category, level=level, icon=icon, link=link)


def _maybe_send_email(notif):
    """Dispatch an email if the user's preferences allow it for this category."""
    try:
        prefs = notif.user.notification_prefs
    except Exception:
        prefs = None

    category_field_map = {
        'order': 'email_orders', 'payment': 'email_orders', 'shipping': 'email_orders',
        'promo': 'email_promos', 'review': 'email_reviews', 'ai': 'email_ai',
    }
    field = category_field_map.get(notif.category)
    if field and prefs is not None and not getattr(prefs, field, True):
        return  # user opted out

    from .models import NotificationDelivery
    from django.core.mail import send_mail
    from django.utils import timezone

    delivery = NotificationDelivery.objects.create(notification=notif, channel='email')
    try:
        send_mail(
            subject      = f'ShopAI · {notif.title}',
            message      = notif.message or notif.title,
            from_email   = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@shopai.com'),
            recipient_list=[notif.user.email],
            fail_silently=True,
        )
        delivery.status  = 'sent'
        delivery.sent_at = timezone.now()
    except Exception as e:
        delivery.status = 'failed'
        delivery.error  = str(e)[:300]
    delivery.save()


# ── Convenience wrappers used by other apps ──────────────

def notify_order_placed(order):
    if not order.user:
        return
    notify_user(
        order.user,
        title    = f'Order {order.order_number} placed! ',
        message  = f'Your order totaling KES {order.total:,.0f} has been received and is being processed.',
        category = 'order', level='success',
        link     = f'/orders/detail/{order.order_number}/',
        object_type='order', object_id=order.order_number,
        send_email=True,
    )


def notify_order_status_changed(order):
    if not order.user:
        return
    STATUS_COPY = {
        'confirmed':  ('Order confirmed ', 'success', 'Received'),
        'processing': ('Order is being prepared ', 'info', 'Processing'),
        'shipped':    ('Your order has shipped! ', 'success', 'Shipped'),
        'delivered':  ('Order delivered ', 'success', 'Sucess'),
        'cancelled':  ('Order cancelled', 'danger', 'Cancelled'),
        'refunded':   ('Order refunded ', 'warning', 'Refunded'),
    }
    title, level, icon = STATUS_COPY.get(order.status, (f'Order status: {order.status}', 'info', 'Order'))
    notify_user(
        order.user, title=title,
        message=f'Order {order.order_number} is now "{order.get_status_display()}".',
        category='order', level=level, icon=icon,
        link=f'/orders/detail/{order.order_number}/',
        object_type='order', object_id=order.order_number,
        send_email=order.status in ('shipped', 'delivered', 'cancelled'),
    )


def notify_payment_result(payment):
    order = payment.order
    if not order.user:
        return
    if payment.status == 'completed':
        notify_user(
            order.user, title='Payment received ',
            message=f'We received your {payment.get_method_display()} payment of KES {payment.amount:,.0f}.',
            category='payment', level='success',
            link=f'/payments/success/{order.order_number}/',
            object_type='order', object_id=order.order_number,
        )
    elif payment.status == 'failed':
        notify_user(
            order.user, title='Payment failed ',
            message=f'Your payment for order {order.order_number} could not be processed. Please try again.',
            category='payment', level='danger',
            link=f'/payments/{order.order_number}/',
            object_type='order', object_id=order.order_number,
            send_email=True,
        )


def notify_review_approved(review):
    notify_user(
        review.user, title='Your review is live ',
        message=f'Your review of "{review.product.name}" has been published.',
        category='review', level='success',
        link=review.product.get_absolute_url(),
        object_type='product', object_id=str(review.product.id),
    )


def notify_back_in_stock(product, users):
    """Notify wishlist users when a product is restocked."""
    notify_users(
        users, title=f'Back in stock! ',
        message=f'"{product.name}" is available again.',
        category='wishlist', level='success',
        link=product.get_absolute_url(),
        object_type='product', object_id=str(product.id),
    )


def notify_price_drop(product, users, old_price, new_price):
    pct = round((1 - float(new_price) / float(old_price)) * 100)
    notify_users(
        users, title=f'Price drop: {product.name} ',
        message=f'Now KES {new_price:,.0f} — {pct}% off the price you saw.',
        category='promo', level='info',
        link=product.get_absolute_url(),
        object_type='product', object_id=str(product.id),
    )


def notify_chat_handoff(user, session):
    notify_user(
        user, title='Connecting you to support ',
        message='A member of our team will be with you shortly.',
        category='chat', level='info',
        link='/ai/chat/',
        object_type='chat_session', object_id=str(session.id),
    )


def notify_staff_fraud_alert(order, result):
    notify_staff(
        title=f'{result["emoji"]} Fraud risk: {order.order_number}',
        message=f'Score {result["score"]} — {result["label"]}. ' + '; '.join(result['flags'][:2]),
        category='ai', level='danger' if result['risk_level'] in ('high','critical') else 'warning',
        link=f'/payments/fraud/dashboard/',
    )


def notify_staff_low_stock(product):
    notify_staff(
        title=f'Low stock: {product.name}',
        message=f'Only {product.stock} units left (SKU {product.sku}).',
        category='system', level='warning', icon='Warning',
        link='/analytics/',
    )
