from django import forms
from django.contrib.auth import authenticate,get_user_model
from django.contrib.auth.password_validation import validate_password
from .models import User, Address


class RegisterForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'email', 'phone']

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({'password2': 'Passwords do not match.'})
        if p1:
            validate_password(p1)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    remember = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean() # Always call super().clean()
        email = cleaned_data.get('email', '').lower()
        password = cleaned_data.get('password')

        if email and password:
            # Attempt to authenticate
            user = authenticate(username=email, password=password)
            if user is None:
                raise forms.ValidationError('Invalid email or password.')
            
            if not user.is_active:
                raise forms.ValidationError('This account has been deactivated.')
            
            # Store the user object on the form instance
            self.user = user
            
        return cleaned_data

    def get_user(self):
        # Now this method is inside the class, so it can access self.user
        return getattr(self, 'user', None)

User = get_user_model()
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'bio', 'date_of_birth', 'gender', 'avatar']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'type': 'tel', 'placeholder': '+254 700 000 000'}),
            'bio': forms.Textarea(attrs={'class': 'form-input', 'rows': 3, 'placeholder': 'Tell us a bit about yourself...'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'gender': forms.Select(attrs={'class': 'form-input'}),    
            'avatar': forms.FileInput(attrs={'class': 'form-input', 'id': 'id_avatar'}),
            

        }



class AddressForm(forms.ModelForm):
    class Meta:
        model  = Address
        fields = ['label','full_name','phone','address_line1','address_line2',
                  'city','state','country','postal_code','address_type','is_default']


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password1    = forms.CharField(widget=forms.PasswordInput)
    new_password2    = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        pwd = self.cleaned_data.get('current_password')
        if not self.user.check_password(pwd):
            raise forms.ValidationError('Current password is incorrect.')
        return pwd

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password1')
        p2 = cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({'new_password2': 'Passwords do not match.'})
        if p1:
            validate_password(p1, self.user)
        return cleaned

    def save(self):
        self.user.set_password(self.cleaned_data['new_password1'])
        self.user.save()
        return self.user


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower()
        if not User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError('No active account found with this email.')
        return email


class PasswordResetConfirmForm(forms.Form):
    new_password1 = forms.CharField(widget=forms.PasswordInput)
    new_password2 = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password1')
        p2 = cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({'new_password2': 'Passwords do not match.'})
        if p1:
            validate_password(p1)
        return cleaned

# users/forms.py
from django import forms
from django.contrib.auth.forms import AuthenticationForm

class EmailAdminAuthenticationForm(AuthenticationForm):
    # Django's AuthenticationForm requires the field name to be 'username' 
    # for its internal logic, so we keep the name but change the label.
    username = forms.EmailField(label="Email Address", widget=forms.TextInput(attrs={'autofocus': True}))

    class Meta:
        # This will be used by our custom backend to authenticate via email
        fields = ['username', 'password']

