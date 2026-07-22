"""
ShopAI API — Request logging middleware.
Only touches the database for paths under /api/, so the main storefront
takes zero overhead from this. Failures here never break the response.
"""
import time


class APIRequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_api = request.path.startswith('/api/')
        start  = time.monotonic() if is_api else None

        response = self.get_response(request)

        if is_api:
            try:
                from .models import APIRequestLog
                APIRequestLog.objects.create(
                    user        = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None,
                    method      = request.method,
                    path        = request.path[:300],
                    status_code = response.status_code,
                    duration_ms = int((time.monotonic() - start) * 1000),
                    ip_address  = request.META.get('REMOTE_ADDR'),
                )
            except Exception:
                pass

        return response
