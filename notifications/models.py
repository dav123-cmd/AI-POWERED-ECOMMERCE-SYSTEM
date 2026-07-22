"""
ShopAI — Notifications Models
In-app notification center + email/push delivery tracking.
"""
from django.db import models
from django.conf import settings
from django.urls import reverse
import uuid


class Notification(models.Model):
    """
    A single in-app notification for a user.
    Covers order updates, payments, reviews, AI alerts, promos, and system messages.
    """
    CATEGORY = [
        ('order',     'Order'),
        ('payment',   'Payment'),
        ('shipping',  'Shipping'),
        ('promo',     'Promotion'),
        ('review',    'Review'),
        ('wishlist',  'Wishlist'),
        ('chat',      'Chat / Support'),
        ('ai',        'AI Insight'),
        ('account',   'Account'),
        ('system',    'System'),
    ]
    LEVEL = [
        ('info',    'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger',  'Danger'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='notifications')
    category    = models.CharField(max_length=10, choices=CATEGORY, default='system')
    level       = models.CharField(max_length=10, choices=LEVEL, default='info')

    title       = models.CharField(max_length=150)
    message     = models.TextField(blank=True)
    icon        = models.CharField(max_length=10, blank=True)   # emoji icon
    link        = models.CharField(max_length=300, blank=True)  # where clicking takes you

    # Generic relation info (order number, product id, etc.) for building links / context
    object_type = models.CharField(max_length=50, blank=True)   # e.g. 'order', 'product', 'review'
    object_id   = models.CharField(max_length=64, blank=True)

    is_read     = models.BooleanField(default=False)
    read_at     = models.DateTimeField(null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'[{self.category}] {self.title} → {self.user}'

    def mark_read(self):
        if not self.is_read:
            from django.utils import timezone
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])

    @property
    def time_ago(self):
        from django.utils import timezone
        from django.utils.timesince import timesince
        return timesince(self.created_at, timezone.now())


class NotificationPreference(models.Model):
    """Per-user channel preferences for each notification category."""
    user            = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                           related_name='notification_prefs')
    # In-app is always on; these control email/push add-ons
    email_orders    = models.BooleanField(default=True)
    email_promos    = models.BooleanField(default=True)
    email_reviews   = models.BooleanField(default=True)
    email_ai        = models.BooleanField(default=False)
    push_enabled    = models.BooleanField(default=False)
    digest_frequency= models.CharField(
        max_length=10,
        choices=[('instant','Instant'),('daily','Daily Digest'),('weekly','Weekly Digest'),('off','Off')],
        default='instant',
    )
    updated_at      = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Prefs({self.user})'


class NotificationDelivery(models.Model):
    """Tracks email/push delivery attempts for a notification (for debugging + analytics)."""
    CHANNEL = [('email','Email'),('push','Push'),('sms','SMS')]
    STATUS  = [('pending','Pending'),('sent','Sent'),('failed','Failed')]

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='deliveries')
    channel      = models.CharField(max_length=10, choices=CHANNEL)
    status       = models.CharField(max_length=10, choices=STATUS, default='pending')
    error        = models.CharField(max_length=300, blank=True)
    sent_at      = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.channel} → {self.status}'
