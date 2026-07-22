from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.admin.forms import AdminAuthenticationForm
from django import forms
from .models import User, Address, EmailVerificationToken

# 1. Define the custom form ONCE
class EmailAdminAuthenticationForm(AdminAuthenticationForm):
    username = forms.EmailField(
        label="Email", 
        widget=forms.TextInput(attrs={'autofocus': True, 'class': 'vTextField'})
    )

# 2. Assign the form to the Admin Site
admin.site.login_form = EmailAdminAuthenticationForm

# 3. Define the Admin class
@admin.register(User)
class CustomerUserAdmin(BaseUserAdmin):
    # CRITICAL: This tells Admin to use email instead of username
    username_field = 'email'
    
    list_display = ('email', 'first_name', 'last_name', 'is_verified', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_verified', 'is_active', 'gender')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    
    # Ensure NO mention of 'username' here
    fieldsets = (
        (None,          {'fields': ('email', 'password')}),
        ('Personal',    {'fields': ('first_name','last_name','phone','avatar','bio','date_of_birth','gender')}),
        ('AI Profile',  {'fields': ('preferred_categories','ai_profile_data')}),
        ('Permissions', {'fields': ('is_active','is_staff','is_superuser','is_verified','groups','user_permissions')}),
        ('Dates',       {'fields': ('date_joined','last_login')}),
    )
    
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'password')}),
    )
    
    filter_horizontal = ('groups', 'user_permissions')

# 4. Register other models
@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'full_name', 'city', 'country', 'is_default')
    list_filter = ('address_type', 'country', 'is_default')
    search_fields = ('user__email', 'full_name', 'city')

@admin.register(EmailVerificationToken)
class VerificationTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'expires_at')