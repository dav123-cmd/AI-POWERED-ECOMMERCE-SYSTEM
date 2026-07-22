from django.contrib import admin
from .models import APIRequestLog

@admin.register(APIRequestLog)
class APIRequestLogAdmin(admin.ModelAdmin):
    list_display  = ('method', 'path', 'status_code', 'duration_ms', 'user', 'created_at')
    list_filter   = ('method', 'status_code')
    search_fields = ('path', 'user__email')
    readonly_fields = ('created_at',)
