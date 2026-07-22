"""
ShopAI — Analytics Views
"""
import json
import csv
import datetime
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_GET, require_http_methods
from django.utils import timezone
from django.db.models import Sum, Q

# Internal app imports
from orders.models import Order, OrderItem
from .models import DailySalesSnapshot, SalesForecast
from .aggregator import (
    get_revenue_metrics, get_daily_revenue_series,
    get_top_products, get_category_breakdown,
    get_inventory_alerts, get_customer_metrics,
    get_payment_breakdown, get_conversion_funnel
)
from .forecasting import generate_forecast, save_forecasts


@staff_member_required
@require_http_methods(["GET"])
def analytics_dashboard(request):
    """Main analytics dashboard view."""
    # 1. Read timeframe parameter (matches template selectors ?days=7, ?days=30)
    days_param = int(request.GET.get('days', 30))
    
    # 2. Collect base analytics periods
    now = timezone.now()
    start_date = (now - datetime.timedelta(days=days_param)).date()
    end_date = now.date()

    metrics = get_revenue_metrics(days_param)
    customers = get_customer_metrics(days_param)
    alerts = get_inventory_alerts()
    
    # 3. Calculate metrics directly expected by template stats object
    units_sold = OrderItem.objects.filter(
        order__payment_status='paid', 
        order__created_at__date__gte=start_date
    ).aggregate(total_units=Sum('quantity'))['total_units'] or 0

    pending_orders = Order.objects.filter(
        Q(payment_status='pending') | Q(status='pending')
    ).count()

    # Construct the stats container matching template property names
    stats_context = {
        'period_start': start_date.strftime('%b %d, %Y'),
        'period_end': end_date.strftime('%b %d, %Y'),
        'revenue': metrics['revenue'],
        'revenue_change': metrics['revenue_change'],
        'orders': metrics['orders'],
        'orders_change': metrics['orders_change'],
        'new_customers': customers['new_customers'],
        'cust_change': None,  # Can add lookback delta calculations if desired
        'avg_order_val': metrics['avg_order'],
        'aov_change': None,
        'units_sold': units_sold,
        'pending_orders': pending_orders,
    }

    # 4. Map top products to match layout keys (total_units, total_revenue)
    raw_products = get_top_products(limit=5, days=days_param)
    top_products_mapped = [
        {
            'product_name': p['product_name'],
            'total_units': p['units'],
            'total_revenue': p['revenue']
        } for p in raw_products
    ]

    # 5. Build timeline sequence datasets for Chart.js
    chart_data = get_daily_revenue_series(days_param)
    
    forecast_qs = list(SalesForecast.objects.filter(
        forecast_date__gte=timezone.now().date()
    ).order_by('forecast_date')[:14])

    # Inject empty or populated arrays so frontend line-chart won't crash
    chart_data['forecast_labels'] = [f.forecast_date.strftime('%b %d') for f in forecast_qs]
    chart_data['forecast_revenues'] = [float(f.predicted_revenue) for f in forecast_qs]

    # Map categories configuration to match the JS array destructors
    raw_categories = get_category_breakdown(days_param)
    categories_mapped = [
        {'category__name': c['category'], 'total': c['revenue']}
        for c in raw_categories
    ]

    return render(request, 'analytics/dashboard.html', {
        'stats': stats_context,
        'top_products': top_products_mapped,
        'low_stock': alerts['low_stock'],
        'out_stock': len(alerts['out_of_stock']),
        'forecasts': forecast_qs,
        'days': days_param,
        'chart': json.dumps(chart_data),
        'categories': json.dumps(categories_mapped),
    })


# ── AJAX Data Endpoints ───────────────────────────────────

@staff_member_required
@require_GET
def revenue_chart_data(request):
    """Chart.js historical timeline data."""
    period = int(request.GET.get('period', 30))
    data = get_daily_revenue_series(period)
    return JsonResponse(data)


@staff_member_required
@require_GET
def category_chart_data(request):
    """Chart.js donut distribution data."""
    period = int(request.GET.get('period', 30))
    data = get_category_breakdown(period)
    return JsonResponse({'categories': data})


@staff_member_required
@require_http_methods(["GET", "POST"])
def forecast_data(request):
    """Handles PyTorch LSTM network triggers and database caching."""
    days = int(request.GET.get('days', 14))
    
    # Process execution trigger via dashboard POST action button
    if request.method == "POST":
        try:
            save_forecasts(days_ahead=days)
            return JsonResponse({
                'success': True,
                'message': 'PyTorch LSTM Inference Engine ran successfully!'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    # Standard data ingestion fallback (GET)
    qs = SalesForecast.objects.filter(
        forecast_date__gte=timezone.now().date()
    ).order_by('forecast_date')[:days]
    
    data = [{'date': str(f.forecast_date), 'predicted': float(f.predicted_revenue),
             'lower': float(f.lower_bound), 'upper': float(f.upper_bound)} for f in qs]
             
    if not data:
        forecasts = generate_forecast(days)
        data = [{'date': str(f['date']), 'predicted': float(f['predicted']),
                 'lower': float(f['lower']), 'upper': float(f['upper'])} for f in forecasts]

    return JsonResponse({'forecasts': data})


@staff_member_required
@require_GET
def top_products_data(request):
    period = int(request.GET.get('period', 30))
    limit = int(request.GET.get('limit', 10))
    data = get_top_products(limit, period)
    return JsonResponse({'products': [
        {'name': d['product_name'], 'revenue': float(d['revenue']),
         'units': d['units'], 'orders': d['orders']} for d in data
    ]})


@staff_member_required
@require_GET
def payment_chart_data(request):
    period = int(request.GET.get('period', 30))
    return JsonResponse({'payments': get_payment_breakdown(period)})


@staff_member_required
@require_GET
def inventory_alerts_view(request):
    alerts = get_inventory_alerts()
    return render(request, 'analytics/inventory_alerts.html', alerts)


@staff_member_required
@require_GET
def export_csv(request):
    """Export actual sales snapshots to flat CSV tables."""
    period = int(request.GET.get('period', 30))
    snaps = DailySalesSnapshot.objects.filter(
        date__gte=timezone.now().date() - datetime.timedelta(days=period)
    ).order_by('date')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="shopai_sales_{period}d.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Revenue (KES)', 'Orders', 'Avg Order Value', 'Units Sold', 'New Customers'])
    for s in snaps:
        writer.writerow([s.date, s.total_revenue, s.order_count,
                         s.avg_order_value, s.units_sold, s.new_customers])
    return response