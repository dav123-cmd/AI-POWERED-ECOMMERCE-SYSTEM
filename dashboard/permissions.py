"""
ShopAI — Dashboard Role-Based Access Control
Wraps Django's staff check with the optional, more granular StaffRole
permission system. A staff user with no StaffRole row defaults to full
access (RBAC narrows access only when explicitly configured).
"""
from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def dashboard_permission_required(perm=None):
    """
    Decorator for dashboard views.
    @dashboard_permission_required()          → any staff member
    @dashboard_permission_required('orders')  → staff with 'orders' permission
                                                 (or any staff if no StaffRole assigned)
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not (user.is_staff or user.is_superuser):
                return render(request, 'dashboard/permission_denied.html', {
                    'reason': 'You need staff access to view the admin dashboard.'
                }, status=403)

            if perm and not user.is_superuser:
                role = getattr(user, 'staff_role', None)
                if role is not None and role.is_active and not role.has_permission(perm):
                    return render(request, 'dashboard/permission_denied.html', {
                        'reason': f'Your role ("{role.get_role_display()}") does not include "{perm}" access.',
                        'perm': perm,
                    }, status=403)

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_staff_role(user):
    """Convenience helper for templates/views — returns StaffRole or None."""
    return getattr(user, 'staff_role', None)
