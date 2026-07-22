"""
Gives every dashboard template access to the current staff member's role
and live badge counts (pending orders, fraud flags, pending reviews, low
stock) without each view needing to recompute them — powers the shared
sidebar partial and its permission-gated nav links.
"""


def staff_nav(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not (user.is_staff or user.is_superuser):
        return {}

    from .permissions import get_staff_role
    from .models import StaffRole

    role = get_staff_role(user)

    def can(perm):
        if user.is_superuser or role is None:
            return True
        return role.is_active and role.has_permission(perm)

    perm_keys = [p[0] for p in StaffRole.PERMISSIONS]
    dash_perms = {perm: can(perm) for perm in perm_keys}

    badges = {'pending_orders': 0, 'fraud_flagged': 0, 'pending_reviews': 0, 'low_stock_count': 0}
    try:
        from orders.models import Order
        from reviews.models import Review
        from products.models import Product
        from django.db.models import F

        badges['pending_orders']  = Order.objects.filter(status='pending').count()
        badges['fraud_flagged']   = Order.objects.filter(fraud_score__gte=0.10, payment_status='paid').count()
        badges['pending_reviews'] = Review.objects.filter(is_approved=False, is_flagged=False).count()
        badges['low_stock_count'] = Product.objects.filter(
            is_active=True, track_inventory=True, stock__gt=0, stock__lte=F('low_stock_threshold')
        ).count()
    except Exception:
        pass

    return {
        'dash_role':   role,
        'dash_perms':  dash_perms,
        'dash_badges': badges,
    }
