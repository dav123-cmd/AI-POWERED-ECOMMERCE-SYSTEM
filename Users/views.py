from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from .forms import (RegisterForm, LoginForm, ProfileUpdateForm,
                    AddressForm, PasswordChangeForm,
                    PasswordResetRequestForm, PasswordResetConfirmForm)
from .models import User, Address, EmailVerificationToken, PasswordResetToken
from .utils import send_verification_email, send_password_reset_email, send_welcome_email
from products.models import  FloatingProduct
# Create your views here.

def home(request):
    floating_products = FloatingProduct.objects.filter(is_active=True)
    big_card = floating_products.filter(card_type='big').first()
    small_card = floating_products.filter(card_type='small').first()
    context = {
        
        'big_card': big_card,
        'small_card': small_card,
    }

    return render(request,"products/home.html",context)

def register(request):
    if request.user.is_authenticated:
        return redirect('products:home')
    form = RegisterForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        send_verification_email(user, request)
        send_welcome_email(user)
        messages.success(request, 'Account created! Please check your email to verify.')
        return redirect('users:login')
    return render(request, 'users/register.html', {'form': form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('products:home')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        if not form.cleaned_data.get('remember'):
            request.session.set_expiry(0)
        messages.success(request, f'Welcome back, {user.get_short_name()}! ')
        return redirect(request.GET.get('next', 'products:home'))
    return render(request, 'users/login.html', {'form': form})


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('products:home')


def verify_email(request, token):
    try:
        obj = EmailVerificationToken.objects.select_related('user').get(token=token)
        if not obj.is_valid():
            messages.error(request, 'Verification link has expired. Request a new one.')
            return redirect('users:login')
        obj.user.is_verified = True
        obj.user.save(update_fields=['is_verified'])
        obj.delete()
        messages.success(request, 'Email verified! You can now sign in. ')
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'Invalid verification link.')
    return redirect('users:login')


@login_required
def resend_verification(request):
    if request.user.is_verified:
        messages.info(request, 'Your email is already verified.')
    else:
        send_verification_email(request.user, request)
        messages.success(request, 'Verification email resent! Check your inbox.')
    return redirect('users:profile')


def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        user  = User.objects.get(email=email)
        send_password_reset_email(user, request)
        messages.success(request, 'Password reset link sent to your email.')
        return redirect('users:login')
    return render(request, 'users/password_reset.html', {'form': form})


def password_reset_confirm(request, token):
    reset = get_object_or_404(PasswordResetToken, token=token)
    if not reset.is_valid():
        messages.error(request, 'This reset link has expired.')
        return redirect('users:password_reset')
    form = PasswordResetConfirmForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        reset.user.set_password(form.cleaned_data['new_password1'])
        reset.user.save()
        reset.used = True
        reset.save()
        messages.success(request, 'Password reset successfully. Please sign in.')
        return redirect('users:login')
    return render(request, 'users/password_reset_confirm.html', {'form': form})


@login_required
def profile(request):
    addresses = request.user.addresses.all()
    return render(request, 'users/profile.html', {'addresses': addresses})

@login_required
def edit_profile(request):
    # Ensure request.FILES is present to catch the multipart image data stream
    form = ProfileUpdateForm(request.POST or None, request.FILES or None, instance=request.user)
    
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('users:profile')
        else:
            # Diagnostic flag: checking if it reached validation failure
            print("Form Errors:", form.errors) 
            
    return render(request, 'users/edit_profile.html', {'form': form})


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password changed successfully!')
            return redirect('users:profile')
    else:
        form = PasswordChangeForm(request.user)
        
    return render(request, 'users/change_password.html', {'form': form})


@login_required
def add_address(request):
    form = AddressForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, 'Address added!')
        return redirect('users:profile')
    return render(request, 'users/address_form.html', {'form': form, 'title': 'Add Address'})


@login_required
def edit_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    form = AddressForm(request.POST or None, instance=address)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Address updated!')
        return redirect('users:profile')
    return render(request, 'users/address_form.html', {'form': form, 'title': 'Edit Address'})


@login_required
def delete_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        address.delete()
        messages.success(request, 'Address deleted.')
    return redirect('users:profile')


import requests
from django.conf import settings
from django.http import JsonResponse

def fetch_api_data(request):
    url = f"{settings.EXTERNAL_API_URL}endpoint/"
    headers = {"Authorization": f"Bearer {settings.EXTERNAL_API_KEY}"}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status() # Raises an error for bad responses (4xx, 5xx)
        data = response.json()
        return JsonResponse(data)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": str(e)}, status=500)
