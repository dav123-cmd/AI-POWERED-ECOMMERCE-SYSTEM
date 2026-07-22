from django.urls import path
from . import views, fraud_views

app_name = 'payments'

urlpatterns = [
    # Payment flow
    path('<str:order_number>/',                      views.payment_page,        name='page'),
    path('success/<str:order_number>/',              views.payment_success,     name='success'),
    path('failed/<str:order_number>/',               views.payment_failed,      name='failed'),
    path('cancel/<str:order_number>/',               views.payment_cancel,      name='cancel'),
    # Stripe
    path('stripe/confirm/',                          views.stripe_confirm,      name='stripe_confirm'),
    path('stripe/webhook/',                          views.stripe_webhook,      name='stripe_webhook'),
    # PayPal
    path('paypal/execute/',                          views.paypal_execute,      name='paypal_execute'),
    # M-Pesa
    path('mpesa/initiate/<str:order_number>/',       views.mpesa_initiate,      name='mpesa_initiate'),
    path('mpesa/query/',                             views.mpesa_query,         name='mpesa_query'),
    path('mpesa/callback/',                          views.mpesa_callback,      name='mpesa_callback'),
    # Invoice
    path('invoice/<str:order_number>/download/',     views.download_invoice,    name='download_invoice'),
    # Refund
    path('refund/<str:order_number>/',               views.request_refund,      name='request_refund'),
    # Fraud
    path('fraud/dashboard/',                         fraud_views.fraud_dashboard,      name='fraud_dashboard'),
    path('fraud/analyze/<str:order_number>/',        fraud_views.analyze_order_view,   name='analyze_order'),
    path('fraud/retrain/',                           fraud_views.retrain_fraud_model,  name='retrain_fraud'),
    path('fraud/bulk-analyze/',                      fraud_views.bulk_analyze,         name='bulk_analyze'),
]
