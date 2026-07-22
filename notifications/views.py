"""
ShopAI — Notifications Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_GET
from .models import Notification, NotificationPreference


@login_required
def index(request):
    """Full notification center page."""
    qs       = request.user.notifications.all()
    category = request.GET.get('category', '')
    only_unread = request.GET.get('unread') == '1'

    if category:
        qs = qs.filter(category=category)
    if only_unread:
        qs = qs.filter(is_read=False)

    paginator = Paginator(qs, 20)
    page      = paginator.get_page(request.GET.get('page', 1))

    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)

    return render(request, 'notifications/index.html', {
        'notifications': page,
        'page_obj':      page,
        'unread_count':  request.user.notifications.filter(is_read=False).count(),
        'categories':    Notification.CATEGORY,
        'current_category': category,
        'only_unread':   only_unread,
        'prefs':         prefs,
    })


@login_required
@require_GET
def dropdown_feed(request):
    """AJAX — recent notifications for the navbar bell dropdown."""
    qs = request.user.notifications.all()[:8]
    data = [{
        'id':         str(n.id),
        'title':      n.title,
        'message':    n.message,
        'icon':       n.icon,
        'level':      n.level,
        'link':       n.link,
        'is_read':    n.is_read,
        'time_ago':   n.time_ago,
    } for n in qs]
    return JsonResponse({
        'success': True,
        'notifications': data,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def mark_read(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.mark_read()
    return JsonResponse({
        'success': True,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def mark_all_read(request):
    from django.utils import timezone
    request.user.notifications.filter(is_read=False).update(is_read=True, read_at=timezone.now())
    return JsonResponse({'success': True, 'unread_count': 0})


@login_required
@require_POST
def delete_notification(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.delete()
    return JsonResponse({
        'success': True,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def clear_all(request):
    request.user.notifications.all().delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def update_preferences(request):
    """Update email/push notification preferences."""
    prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
    prefs.email_orders     = request.POST.get('email_orders') == 'on'
    prefs.email_promos     = request.POST.get('email_promos') == 'on'
    prefs.email_reviews    = request.POST.get('email_reviews') == 'on'
    prefs.email_ai         = request.POST.get('email_ai') == 'on'
    prefs.push_enabled     = request.POST.get('push_enabled') == 'on'
    prefs.digest_frequency = request.POST.get('digest_frequency', 'instant')
    prefs.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Preferences saved.'})
    messages.success(request, 'Notification preferences updated.')
    return redirect('notifications:index')


@login_required
def go_to_notification(request, notification_id):
    """Mark read then redirect to the linked page (used by email links / non-JS fallback)."""
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.mark_read()
    return redirect(notif.link or 'notifications:index')
