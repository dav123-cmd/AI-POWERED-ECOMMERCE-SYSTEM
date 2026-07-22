from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('',                                    views.dashboard_home,        name='home'),
    path('orders/',                             views.orders_panel,          name='orders'),
    path('orders/<str:order_number>/status/',   views.update_order_status,   name='update_order_status'),
    path('products/',                           views.products_panel,        name='products'),
    path('products/<str:product_id>/toggle/',   views.toggle_product_status, name='toggle_product'),
    path('pricing/',                            views.pricing_panel,         name='pricing'),
    path('users/',                              views.users_panel,           name='users'),
    path('users/<uuid:user_id>/toggle-staff/',  views.toggle_user_staff,     name='toggle_user_staff'),
    path('ai-models/',                          views.ai_models_panel,       name='ai_models'),
    path('ai-models/retrain/',                  views.retrain_model,         name='retrain_model'),
    path('activity/',                           views.activity_log_view,     name='activity'),
]
