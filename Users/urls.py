from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
# Namespace for reversing URLs from templates
app_name = 'users'



urlpatterns = [
    path('', views.home, name='home'),
    path('register/',                          views.register,                 name='register'),
    path('login/',                             views.login_view,               name='login'),
    path('logout/',                            views.logout_view,              name='logout'),
    path('verify-email/<uuid:token>/',         views.verify_email,             name='verify_email'),
    path('resend-verification/',               views.resend_verification,      name='resend_verification'),
    path('password-reset/',                    views.password_reset_request,   name='password_reset'),
    path('reset-password/<uuid:token>/',       views.password_reset_confirm,   name='password_reset_confirm'),
    path('profile/',                           views.profile,                  name='profile'),
    path('profile/edit/',                      views.edit_profile,             name='edit_profile'),
    path('profile/change-password/',           views.change_password,          name='change_password'),
    path('profile/addresses/add/',             views.add_address,              name='add_address'),
    path('profile/addresses/<int:pk>/edit/',   views.edit_address,             name='edit_address'),
    path('profile/addresses/<int:pk>/delete/', views.delete_address,           name='delete_address'),

]