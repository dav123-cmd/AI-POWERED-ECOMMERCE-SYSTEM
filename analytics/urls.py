from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('',                    views.analytics_dashboard,  name='dashboard'),
    path('api/revenue/',        views.revenue_chart_data,   name='revenue_data'),
    path('api/categories/',     views.category_chart_data,  name='category_data'),
    path('api/forecast/',       views.forecast_data,        name='forecast_data'),
    path('api/top-products/',   views.top_products_data,    name='top_products'),
    path('api/payments/',       views.payment_chart_data,   name='payment_data'),
    path('inventory/',          views.inventory_alerts_view,name='inventory'),
    path('export/',             views.export_csv,           name='export'),
]
