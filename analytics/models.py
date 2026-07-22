"""
ShopAI — Analytics Models
Stores aggregated metrics for fast dashboard rendering.
"""
from django.db import models
from django.conf import settings


class DailySalesSnapshot(models.Model):
    """Pre-aggregated daily sales data for Chart.js rendering."""
    date            = models.DateField(unique=True, db_index=True)
    total_revenue   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    order_count     = models.PositiveIntegerField(default=0)
    units_sold      = models.PositiveIntegerField(default=0)
    avg_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    new_customers   = models.PositiveIntegerField(default=0)
    refund_amount   = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.date} — KES {self.total_revenue}'


class SalesForecast(models.Model):
    """LSTM-generated sales forecasts."""
    forecast_date   = models.DateField(db_index=True)
    predicted_revenue = models.DecimalField(max_digits=14, decimal_places=2)
    lower_bound     = models.DecimalField(max_digits=14, decimal_places=2)
    upper_bound     = models.DecimalField(max_digits=14, decimal_places=2)
    confidence      = models.FloatField(default=0.8)
    model_version   = models.CharField(max_length=50, blank=True)
    generated_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering        = ['forecast_date']
        unique_together = ['forecast_date', 'model_version']

    def __str__(self):
        return f'Forecast {self.forecast_date}: KES {self.predicted_revenue}'


class ProductAnalytics(models.Model):
    """Per-product analytics snapshot (rebuilt daily)."""
    product         = models.OneToOneField('products.Product', on_delete=models.CASCADE,
                                           related_name='analytics')
    views_7d        = models.PositiveIntegerField(default=0)
    views_30d       = models.PositiveIntegerField(default=0)
    revenue_7d      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    revenue_30d     = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    conversion_rate = models.FloatField(default=0.0)   # purchases / views
    return_rate     = models.FloatField(default=0.0)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-revenue_30d']

    def __str__(self):
        return f'Analytics: {self.product.name}'


class UserBehaviorEvent(models.Model):
    """Lightweight event tracking for user behavior analytics."""
    EVENTS = [
        ('page_view',   'Page View'),
        ('search',      'Search'),
        ('product_view','Product View'),
        ('add_cart',    'Add to Cart'),
        ('checkout',    'Checkout Start'),
        ('purchase',    'Purchase'),
    ]
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=40, blank=True)
    event       = models.CharField(max_length=20, choices=EVENTS)
    page        = models.CharField(max_length=300, blank=True)
    metadata    = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['event', 'created_at'])]
