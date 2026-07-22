"""
ShopAI API — Models
No new business data lives here (the API wraps existing apps' models).
This is a lightweight log of API usage, useful for the docs/portfolio
story ("here's real traffic shape") and for spotting abusive clients.
"""
from django.db import models
from django.conf import settings


class APIRequestLog(models.Model):
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='api_requests')
    method      = models.CharField(max_length=10)
    path        = models.CharField(max_length=300, db_index=True)
    status_code = models.PositiveSmallIntegerField()
    duration_ms = models.PositiveIntegerField(default=0)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.method} {self.path} → {self.status_code}'
