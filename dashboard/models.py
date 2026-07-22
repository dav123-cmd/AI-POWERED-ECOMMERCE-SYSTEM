"""
ShopAI — Dashboard Models
Role-based access, activity logs, saved reports.
"""
from django.db import models
from django.conf import settings


class StaffRole(models.Model):
    ROLES = [
        ('super_admin', 'Super Admin'),
        ('admin',       'Admin'),
        ('manager',     'Manager'),
        ('analyst',     'Analyst'),
        ('support',     'Support'),
    ]
    PERMISSIONS = [
        ('orders',    'Manage Orders'),
        ('products',  'Manage Products'),
        ('users',     'Manage Users'),
        ('analytics', 'View Analytics'),
        ('ai_models', 'Manage AI Models'),
        ('payments',  'View Payments'),
        ('fraud',     'Fraud Dashboard'),
        ('reviews',   'Moderate Reviews'),
    ]

    user        = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       related_name='staff_role')
    role        = models.CharField(max_length=15, choices=ROLES, default='support')
    permissions = models.JSONField(default=list)  # list of permission keys
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.email} — {self.role}'

    def has_permission(self, perm):
        if self.role == 'super_admin':
            return True
        return perm in self.permissions


class ActivityLog(models.Model):
    """Audit trail of all staff actions."""
    ACTIONS = [
        ('create', 'Created'), ('update', 'Updated'),
        ('delete', 'Deleted'), ('approve','Approved'),
        ('reject', 'Rejected'),('export', 'Exported'),
        ('login',  'Logged In'),('train', 'Trained Model'),
    ]

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, related_name='activity_logs')
    action      = models.CharField(max_length=10, choices=ACTIONS)
    model_name  = models.CharField(max_length=50, blank=True)
    object_id   = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=300, blank=True)
    details     = models.JSONField(default=dict, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.action} {self.model_name}'


class SavedReport(models.Model):
    """User-saved analytics reports."""
    name        = models.CharField(max_length=100)
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='saved_reports')
    config      = models.JSONField(default=dict)  # chart type, date range, metrics
    is_shared   = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
