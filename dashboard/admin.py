from django.contrib import admin
from .models import StaffRole, ActivityLog, SavedReport

@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ('user','role','is_active','created_at')
    list_filter  = ('role','is_active')
    search_fields= ('user__email',)

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user','action','model_name','object_repr','created_at')
    list_filter  = ('action','model_name')
    readonly_fields = ('created_at',)

@admin.register(SavedReport)
class SavedReportAdmin(admin.ModelAdmin):
    list_display = ('name','created_by','is_shared','created_at')
    list_filter  = ('is_shared',)
    readonly_fields = ('created_at',)
