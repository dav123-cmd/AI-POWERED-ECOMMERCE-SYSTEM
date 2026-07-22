from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import uuid
from .models import EmailVerificationToken, PasswordResetToken


def send_verification_email(user, request):
    token, _ = EmailVerificationToken.objects.update_or_create(
        user=user,
        defaults={
            'token': uuid.uuid4(),
            'expires_at': timezone.now() + timedelta(hours=24),
        }
    )
    verify_url = request.build_absolute_uri(f'/users/verify-email/{token.token}/')
    send_mail(
        subject='Verify your ShopAI email',
        message=f'Click to verify: {verify_url}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=render_to_string('users/emails/verify_email.html', {
            'user': user, 'verify_url': verify_url
        }),
        fail_silently=True,
    )


def send_password_reset_email(user, request):
    token = PasswordResetToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=2),
    )
    reset_url = request.build_absolute_uri(f'/users/password_reset/{token.token}/')
    send_mail(
        subject='Reset your ShopAI password',
        message=f'Click to reset: {reset_url}',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=render_to_string('users/password_reset.html', {
            'user': user, 'reset_url': reset_url
        }),
        fail_silently=True,
    )


def send_welcome_email(user):
    send_mail(
        subject='Welcome to ShopAI ',
        message=f'Hi {user.get_short_name()}, welcome to ShopAI!',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=render_to_string('users/emails/welcome.html', {'user': user}),
        fail_silently=True,
    )
