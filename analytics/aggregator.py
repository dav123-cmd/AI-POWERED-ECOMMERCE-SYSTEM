"""
ShopAI — Analytics Aggregator
Computes and caches all dashboard metrics.
"""
from django.db.models import Sum, Count, Avg, F, Q
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal


def get_revenue_metrics(days=30):
    """Revenue totals for dashboard KPI cards."""
    from orders.models import Order

    now        = timezone.now()
    period_start = now - timedelta(days=days)
    prev_start   = now - timedelta(days=days * 2)

    curr = Order.objects.filter(
        payment_status='paid', created_at__gte=period_start
    ).aggregate(
        revenue=Sum('total'), orders=Count('id'),
        avg_order=Avg('total'), customers=Count('user', distinct=True)
    )
    prev = Order.objects.filter(
        payment_status='paid',
        created_at__gte=prev_start, created_at__lt=period_start
    ).aggregate(revenue=Sum('total'), orders=Count('id'))

    curr_rev  = float(curr['revenue'] or 0)
    prev_rev  = float(prev['revenue'] or 0)
    rev_change= ((curr_rev - prev_rev) / max(prev_rev, 1)) * 100

    curr_ord  = curr['orders'] or 0
    prev_ord  = prev['orders'] or 0
    ord_change= ((curr_ord - prev_ord) / max(prev_ord, 1)) * 100

    return {
        'revenue':       curr_rev,
        'revenue_change':round(rev_change, 1),
        'orders':        curr_ord,
        'orders_change': round(ord_change, 1),
        'avg_order':     float(curr['avg_order'] or 0),
        'customers':     curr['customers'] or 0,
    }


def get_daily_revenue_series(days=30):
    """Day-by-day revenue for the line chart."""
    from orders.models import Order

    end_date   = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)

    qs = Order.objects.filter(
        payment_status='paid',
        created_at__date__gte=start_date
    ).extra(select={'day': "DATE(created_at)"})\
     .values('day').annotate(rev=Sum('total'), cnt=Count('id'))\
     .order_by('day')

    rev_map = {row['day']: (float(row['rev']), row['cnt']) for row in qs}

    labels, revenues, orders = [], [], []
    d = start_date
    while d <= end_date:
        labels.append(d.strftime('%b %d'))
        rev, cnt = rev_map.get(d, (0.0, 0))
        revenues.append(round(rev, 2))
        orders.append(cnt)
        d += timedelta(days=1)

    return {'labels': labels, 'revenues': revenues, 'orders': orders}


def get_top_products(limit=10, days=30):
    """Best-performing products by revenue."""
    from orders.models import OrderItem

    since = timezone.now() - timedelta(days=days)
    items = OrderItem.objects.filter(
        order__payment_status='paid', order__created_at__gte=since
    ).values('product_id', 'product_name')\
     .annotate(
        revenue=Sum(F('unit_price') * F('quantity')),
        units=Sum('quantity'), orders=Count('order', distinct=True)
    ).order_by('-revenue')[:limit]

    return list(items)


def get_category_breakdown(days=30):
    """Revenue by category for the pie/donut chart."""
    from orders.models import OrderItem

    since = timezone.now() - timedelta(days=days)
    data  = OrderItem.objects.filter(
        order__payment_status='paid', order__created_at__gte=since,
        product__category__isnull=False
    ).values('product__category__name')\
     .annotate(revenue=Sum(F('unit_price') * F('quantity')))\
     .order_by('-revenue')[:8]

    return [
        {'category': d['product__category__name'], 'revenue': float(d['revenue'])}
        for d in data
    ]


def get_inventory_alerts():
    """Products with low or zero stock."""
    from products.models import Product

    low   = Product.objects.filter(is_active=True, stock__lte=F('low_stock_threshold'), stock__gt=0)\
                           .order_by('stock')[:20]
    out   = Product.objects.filter(is_active=True, stock=0)[:20]
    return {'low_stock': list(low), 'out_of_stock': list(out)}


def get_customer_metrics(days=30):
    """New vs returning customers, retention metrics."""
    from orders.models import Order
    from django.contrib.auth import get_user_model
    User = get_user_model()

    since  = timezone.now() - timedelta(days=days)
    new    = User.objects.filter(date_joined__gte=since).count()
    total  = User.objects.count()
    repeat = Order.objects.filter(
        payment_status='paid', created_at__gte=since
    ).values('user').annotate(cnt=Count('id')).filter(cnt__gt=1).count()

    return {'new_customers': new, 'total_customers': total, 'repeat_buyers': repeat}


def get_payment_breakdown(days=30):
    """Payment method distribution."""
    from payments.models import Payment

    since = timezone.now() - timedelta(days=days)
    data  = Payment.objects.filter(
        status='completed', created_at__gte=since
    ).values('method').annotate(
        count=Count('id'), revenue=Sum('amount')
    ).order_by('-revenue')

    return [{'method': d['method'], 'count': d['count'], 'revenue': float(d['revenue'])} for d in data]


def get_conversion_funnel(days=30):
    """Rough conversion funnel: visits → views → cart → purchase."""
    from products.models import ProductView
    from orders.models import Order, Cart

    since  = timezone.now() - timedelta(days=days)
    views  = ProductView.objects.filter(viewed_at__gte=since).count()
    carts  = Order.objects.filter(created_at__gte=since).count()
    orders = Order.objects.filter(payment_status='paid', created_at__gte=since).count()

    return {
        'views':   views,
        'carts':   carts,
        'orders':  orders,
        'view_to_cart':    round(carts  / max(views, 1) * 100, 1),
        'cart_to_order':   round(orders / max(carts, 1) * 100, 1),
        'overall_conv':    round(orders / max(views, 1) * 100, 2),
    }


def rebuild_daily_snapshots(days=30):
    """Celery task: rebuild DailySalesSnapshot for last N days."""
    from orders.models import Order
    from .models import DailySalesSnapshot
    from django.contrib.auth import get_user_model
    User = get_user_model()

    end_date   = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    d = start_date
    created = 0

    while d <= end_date:
        orders  = Order.objects.filter(payment_status='paid', created_at__date=d)
        agg     = orders.aggregate(
            rev=Sum('total'), cnt=Count('id'),
            avg=Avg('total'), units=Sum('items__quantity')
        )
        new_cust= User.objects.filter(date_joined__date=d).count()

        snap, _ = DailySalesSnapshot.objects.update_or_create(
            date=d,
            defaults={
                'total_revenue':   agg['rev']   or Decimal('0'),
                'order_count':     agg['cnt']   or 0,
                'avg_order_value': agg['avg']   or Decimal('0'),
                'units_sold':      agg['units'] or 0,
                'new_customers':   new_cust,
            }
        )
        d += timedelta(days=1)
        created += 1

    print(f'Rebuilt {created} daily snapshots')
    return created
# analytics/aggregator.py

def get_chart_data(days=30):
    """Wrapper to match the expected function name in views.py."""
    return get_daily_revenue_series(days=days)