from django.contrib import admin
from .models import Notification, NotificationPreference, NotificationDelivery

class DeliveryInline(admin.TabularInline):
    model = NotificationDelivery
    extra = 0
    readonly_fields = ('channel', 'status', 'error', 'sent_at', 'created_at')
    can_delete = False

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ('title', 'user', 'category', 'level', 'is_read', 'created_at')
    list_filter   = ('category', 'level', 'is_read')
    search_fields = ('title', 'message', 'user__email')
    readonly_fields = ('created_at', 'read_at')
    inlines       = [DeliveryInline]
    actions       = ['mark_as_read', 'mark_as_unread']

    def mark_as_read(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_read=True, read_at=timezone.now())
    mark_as_read.short_description = 'Mark selected as read'

    def mark_as_unread(self, request, queryset):
        queryset.update(is_read=False, read_at=None)
    mark_as_unread.short_description = 'Mark selected as unread'


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display  = ('user', 'email_orders', 'email_promos', 'email_reviews', 'push_enabled', 'digest_frequency')
    list_filter   = ('digest_frequency', 'push_enabled')
    search_fields = ('user__email',)


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display  = ('notification', 'channel', 'status', 'sent_at', 'created_at')
    list_filter   = ('channel', 'status')
    readonly_fields = ('created_at',)
