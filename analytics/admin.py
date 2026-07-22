from django.contrib import admin
from .models import DailySalesSnapshot, SalesForecast, ProductAnalytics

@admin.register(DailySalesSnapshot)
class DailySnapshotAdmin(admin.ModelAdmin):
    list_display  = ('date','total_revenue','order_count','avg_order_value','new_customers')
    ordering      = ('-date',)
    readonly_fields = ('created_at','updated_at')

@admin.register(SalesForecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display  = ('forecast_date','predicted_revenue','lower_bound','upper_bound','confidence','model_version')
    ordering      = ('forecast_date',)
    readonly_fields = ('generated_at',)

@admin.register(ProductAnalytics)
class ProductAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('product','views_7d','views_30d','revenue_7d','revenue_30d','conversion_rate')
    ordering     = ('-revenue_30d',)
