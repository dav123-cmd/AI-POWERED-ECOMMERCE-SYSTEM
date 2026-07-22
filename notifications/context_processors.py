"""
Injects unread notification count + recent notifications into every template context.
Registered in settings.py TEMPLATES['OPTIONS']['context_processors'].
"""

def notifications(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'unread_notifications': 0, 'recent_notifications': []}

    try:
        qs = request.user.notifications.all()
        unread = qs.filter(is_read=False).count()
        recent = list(qs[:6])
        return {'unread_notifications': unread, 'recent_notifications': recent}
    except Exception:
        return {'unread_notifications': 0, 'recent_notifications': []}
