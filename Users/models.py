from django.db import models

# Create your models here.
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('Email address is required'))
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        return self.create_user(email, password, **extra_fields)


def avatar_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'avatars/{instance.id}/{uuid.uuid4()}.{ext}'


class User(AbstractBaseUser, PermissionsMixin):
    id            = models.UUIDField(primary_key=True, 
                                     default=uuid.uuid4, editable=False)
    email         = models.EmailField(unique=True, db_index=True)
    username = None
    first_name    = models.CharField(max_length=80)
    last_name     = models.CharField(max_length=80)
    phone         = models.CharField(max_length=20, blank=True)
    avatar        = models.ImageField(upload_to=avatar_upload_path, null=True, blank=True)
    is_active     = models.BooleanField(default=True)
    is_staff      = models.BooleanField(default=False)
    is_verified   = models.BooleanField(default=False)
    bio           = models.TextField(blank=True, max_length=500)
    date_of_birth = models.DateField(null=True, blank=True)
    gender        = models.CharField(max_length=10, blank=True,
                                     choices=[('M','Male'),('F','Female'),('O','Other')])
    preferred_categories = models.JSONField(default=list, blank=True)
    ai_profile_data      = models.JSONField(default=dict, blank=True)
    date_joined   = models.DateTimeField(default=timezone.now)
    last_login    = models.DateTimeField(null=True, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = UserManager()

    class Meta:
        verbose_name_plural = 'users'
        ordering = ['-date_joined']

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    @property
    def wishlist_count(self):
        return self.wishlist_items.count() if hasattr(self, 'wishlist_items') else 0

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        name = self.get_full_name()
        return f'https://ui-avatars.com/api/?name={name}&background=c9a84c&color=0a0a0f&bold=true'


class Address(models.Model):
    TYPES = [('shipping','Shipping'),('billing','Billing')]
    user          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label         = models.CharField(max_length=50, default='Home')
    address_type  = models.CharField(max_length=10, choices=TYPES, default='shipping')
    full_name     = models.CharField(max_length=120)
    phone         = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True)
    city          = models.CharField(max_length=100)
    state         = models.CharField(max_length=100)
    country       = models.CharField(max_length=100, default='Kenya')
    postal_code   = models.CharField(max_length=20, blank=True)
    is_default    = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f'{self.label} - {self.full_name}, {self.city}'

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, address_type=self.address_type, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class EmailVerificationToken(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name='verification_token')
    token      = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return timezone.now() < self.expires_at


class PasswordResetToken(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_tokens')
    token      = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used       = models.BooleanField(default=False)

    def is_valid(self):
        return not self.used and timezone.now() < self.expires_at

