"""
ShopAI — Admin Dashboard Views
A professional, data-rich control center pulling live metrics from
every subsystem built across the project: orders, products, users,
payments, fraud detection, recommendations, search, sentiment, and
sales forecasting.
"""
import json
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Sum, Count, Avg, Q, F, ExpressionWrapper, FloatField
from django.core.paginator import Paginator
from django.utils import timezone

from .models import ActivityLog, StaffRole, SavedReport
from .permissions import dashboard_permission_required


# ── Helpers ────────────────────────────────────────────────

def _log(request, action, model_name='', obj_id='', obj_repr='', details=None):
    """Record a staff action in the audit trail."""
    ActivityLog.objects.create(
        user        = request.user if request.user.is_authenticated else None,
        action      = action,
        model_name  = model_name,
        object_id   = str(obj_id),
        object_repr = obj_repr,
        details     = details or {},
        ip_address  = request.META.get('REMOTE_ADDR'),
    )


def _ai_model_status():
    """Check which trained AI model files exist on disk."""
    import datetime as _dt
    models_dir = Path(settings.AI_MODELS_DIR)
    MODEL_INFO = [
        ('recommender',  'Recommendation Engine', 'recommender.pth',          'Collaborative Filtering (PyTorch)'),
        ('search_text',  'Semantic Search',        'faiss_text.bin',          'Sentence Transformers + FAISS'),
        ('search_visual','Visual Search',          'faiss_visual.bin',        'ResNet50 CNN + FAISS'),
        ('sentiment',    'Sentiment Classifier',   'sentiment_model.pth',     'Bidirectional GRU + Attention'),
        ('fake_review',  'Fake Review Detector',   'fake_review_detector.pth','Hybrid Text + Behavioral Net'),
        ('fraud',        'Fraud Detector',         'fraud_detector.pth',      'Autoencoder Anomaly Detection'),
        ('pricing',      'Dynamic Pricing',        'pricing_model.pth',       'Feedforward Regression Net'),
        ('forecast',     'Sales Forecasting',      'sales_forecast.pth',      'LSTM + Attention'),
        ('intent',       'Intent Classifier',      'intent_classifier.pth',   'Bidirectional LSTM (ARIA)'),
    ]
    status = []
    for key, name, filename, arch in MODEL_INFO:
        path   = models_dir / filename
        exists = path.exists()
        updated = '—'
        if exists:
            try:
                updated = _dt.datetime.fromtimestamp(path.stat().st_mtime).strftime('%b %d, %H:%M')
            except Exception:
                pass
        status.append({
            'key': key, 'name': name, 'filename': filename, 'arch': arch,
            'exists': exists,
            'size':   f'{path.stat().st_size / 1024:.1f} KB' if exists else '—',
            'updated': updated,
        })
    return status


# ── Main Dashboard Home ────────────────────────────────────

@dashboard_permission_required()
def dashboard_home(request):
    """Main admin dashboard — real-time overview with full analytics suite."""
    from orders.models import Order
    from products.models import Product
    from Users.models import User
    from reviews.models import Review
    from analytics.aggregator import get_chart_data, get_category_breakdown, get_top_products

    today      = date.today()
    week_ago   = today - timedelta(days=7)
    month_ago  = today - timedelta(days=30)

    # ── KPIs ──────────────────────────────────────────────
    today_orders_qs = Order.objects.filter(created_at__date=today, payment_status='paid')
    today_revenue   = today_orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    month_orders_qs = Order.objects.filter(created_at__date__gte=month_ago, payment_status='paid')
    month_revenue   = month_orders_qs.aggregate(s=Sum('total'))['s'] or Decimal('0')

    total_users     = User.objects.count()
    new_users_week  = User.objects.filter(date_joined__date__gte=week_ago).count()

    pending_orders  = Order.objects.filter(status='pending').count()
    fraud_flagged   = Order.objects.filter(fraud_score__gte=0.10, payment_status='paid').count()
    pending_reviews = Review.objects.filter(is_approved=False, is_flagged=False).count()

    low_stock_qs    = Product.objects.filter(is_active=True, track_inventory=True,
                                              stock__gt=0, stock__lte=F('low_stock_threshold'))
    out_of_stock    = Product.objects.filter(is_active=True, track_inventory=True, stock=0).count()

    # ── Hourly revenue today ───────────────────────────────
    hourly = []
    for h in range(24):
        rev = today_orders_qs.filter(created_at__hour=h).aggregate(s=Sum('total'))['s'] or 0
        hourly.append({'hour': h, 'revenue': float(rev)})

    # ── Revenue trend + LSTM forecast (last 30 days) ───────
    chart = get_chart_data(days=30)

    # ── Orders by status (doughnut) ────────────────────────
    status_counts = dict(Order.objects.values_list('status').annotate(c=Count('id')).order_by())
    order_status_chart = {
        'labels': [s[1] for s in Order.STATUS if status_counts.get(s[0])],
        'values': [status_counts.get(s[0], 0) for s in Order.STATUS if status_counts.get(s[0])],
    }

    # ── User growth — last 14 days ─────────────────────────
    user_growth = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        c = User.objects.filter(date_joined__date=d).count()
        user_growth.append({'date': d.strftime('%b %d'), 'count': c})

    # ── Sentiment split across all reviews ─────────────────
    sentiment_counts = dict(Review.objects.exclude(sentiment='')
                                  .values_list('sentiment').annotate(c=Count('id')).order_by())

    # ── Fraud risk distribution ─────────────────────────────
    paid_orders = Order.objects.filter(payment_status='paid')
    fraud_buckets = {
        'low':      paid_orders.filter(fraud_score__lt=0.05).count(),
        'medium':   paid_orders.filter(fraud_score__gte=0.05, fraud_score__lt=0.10).count(),
        'high':     paid_orders.filter(fraud_score__gte=0.10, fraud_score__lt=0.18).count(),
        'critical': paid_orders.filter(fraud_score__gte=0.18).count(),
    }

    # ── Recent orders / activity / alerts ──────────────────
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:8]
    activity_log  = ActivityLog.objects.select_related('user').order_by('-created_at')[:10]

    # ── AI model status grid ───────────────────────────────
    ai_status = _ai_model_status()
    ai_active_count = sum(1 for m in ai_status if m['exists'])

    return render(request, 'dashboard/home.html', {
        'today_revenue':   today_revenue,
        'today_orders':    today_orders_qs.count(),
        'month_revenue':   month_revenue,
        'month_orders':    month_orders_qs.count(),
        'total_users':     total_users,
        'new_users_week':  new_users_week,
        'pending_orders':  pending_orders,
        'fraud_flagged':   fraud_flagged,
        'pending_reviews': pending_reviews,
        'low_stock':       low_stock_qs.select_related('category')[:8],
        'low_stock_count': low_stock_qs.count(),
        'out_of_stock':    out_of_stock,
        'recent_orders':   recent_orders,
        'activity_log':    activity_log,
        'ai_status':       ai_status,
        'ai_active_count': ai_active_count,
        'ai_total_count':  len(ai_status),
        'hourly_json':         json.dumps(hourly),
        'chart_json':          json.dumps(chart),
        'order_status_json':   json.dumps(order_status_chart),
        'user_growth_json':    json.dumps(user_growth),
        'sentiment_json':      json.dumps(sentiment_counts),
        'fraud_buckets_json':  json.dumps(fraud_buckets),
        'category_json':       json.dumps(get_category_breakdown(30), default=float),
        'top_products':        get_top_products(limit=6),
        'today':            today,
    })


# ── Orders Management ─────────────────────────────────────

@dashboard_permission_required('orders')
def orders_panel(request):
    """Orders management panel with filters."""
    from orders.models import Order

    status = request.GET.get('status', '')
    q      = request.GET.get('q', '').strip()
    orders = Order.objects.select_related('user').prefetch_related('items').order_by('-created_at')

    if status:
        orders = orders.filter(status=status)
    if q:
        orders = orders.filter(
            Q(order_number__icontains=q) | Q(email__icontains=q) |
            Q(shipping_name__icontains=q)
        )

    page = Paginator(orders, 25).get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/orders_panel.html', {
        'orders': page, 'page_obj': page,
        'status_filter': status, 'search': q,
        'status_choices': Order.STATUS,
        'stats': {
            'pending':    Order.objects.filter(status='pending').count(),
            'processing': Order.objects.filter(status='processing').count(),
            'shipped':    Order.objects.filter(status='shipped').count(),
        }
    })


@dashboard_permission_required('orders')
def update_order_status(request, order_number):
    """AJAX: update order status."""
    from orders.models import Order, OrderStatusHistory
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    order  = get_object_or_404(Order, order_number=order_number)
    status = request.POST.get('status')
    note   = request.POST.get('note', '')
    VALID  = [s[0] for s in Order.STATUS]
    if status not in VALID:
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
    old = order.status
    order.status = status
    if status == 'delivered':
        order.delivered_at = timezone.now()
    order.save()
    OrderStatusHistory.objects.create(
        order=order, status=status, note=note, changed_by=request.user
    )
    try:
        from notifications.services import notify_order_status_changed
        notify_order_status_changed(order)
    except Exception:
        pass
    _log(request, 'update', 'Order', order.order_number,
         f'Order {order.order_number}', {'old': old, 'new': status})
    return JsonResponse({'success': True, 'new_status': status})


# ── Products Management ───────────────────────────────────

@dashboard_permission_required('products')
def products_panel(request):
    """Products management panel."""
    from products.models import Product, Category
    q          = request.GET.get('q', '').strip()
    cat_id     = request.GET.get('category', '')
    sort       = request.GET.get('sort', '-created_at')
    low_stock  = request.GET.get('low_stock') == '1'
    products   = Product.objects.select_related('category', 'brand').prefetch_related('images')

    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    if cat_id:
        products = products.filter(category_id=cat_id)
    if low_stock:
        products = products.filter(is_active=True, track_inventory=True,
                                    stock__lte=F('low_stock_threshold'))

    VALID_SORTS = ['-created_at', 'name', 'price', '-price', 'stock', '-stock',
                   '-purchase_count', '-rating_avg']
    products = products.order_by(sort if sort in VALID_SORTS else '-created_at')

    page = Paginator(products, 20).get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/products_panel.html', {
        'products': page, 'page_obj': page,
        'categories': Category.objects.all(),
        'search': q, 'sort': sort, 'low_stock_filter': low_stock,
        'selected_category': cat_id,
        'low_stock_count': Product.objects.filter(
            is_active=True, track_inventory=True,
            stock__gt=0, stock__lte=F('low_stock_threshold')
        ).count(),
        'out_of_stock_count': Product.objects.filter(
            is_active=True, track_inventory=True, stock=0
        ).count(),
        'total_count': Product.objects.count(),
        'active_count': Product.objects.filter(is_active=True).count(),
    })


@dashboard_permission_required('products')
def toggle_product_status(request, product_id):
    """AJAX: toggle product active/inactive."""
    from products.models import Product
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active'])
    _log(request, 'update', 'Product', str(product_id), product.name,
         {'is_active': product.is_active})
    return JsonResponse({'success': True, 'is_active': product.is_active})


# ── Pricing AI Panel ───────────────────────────────────────

@dashboard_permission_required('products')
def pricing_panel(request):
    """Dynamic pricing dashboard — preview & apply AI-optimized prices."""
    from products.models import Product
    from django.db.models import Case, When

    q        = request.GET.get('q', '').strip()
    products = Product.objects.filter(is_active=True).select_related('category')

    if q:
        products = products.filter(Q(name__icontains=q) | Q(sku__icontains=q))

    # Per-row multiplier (ai_price/price) and % change — NULL-safe via Case/When
    priced_filter = Q(ai_price__isnull=False) & ~Q(price=0)
    products = products.annotate(
        price_ratio=Case(
            When(priced_filter, then=ExpressionWrapper(F('ai_price') / F('price'), output_field=FloatField())),
            default=None, output_field=FloatField(),
        ),
        change_pct=Case(
            When(priced_filter, then=ExpressionWrapper(
                (F('ai_price') - F('price')) * 100.0 / F('price'), output_field=FloatField())),
            default=None, output_field=FloatField(),
        ),
    ).order_by('-view_count', '-created_at')

    page = Paginator(products, 25).get_page(request.GET.get('page', 1))

    priced_qs = Product.objects.filter(is_active=True, ai_price__isnull=False, price__gt=0)
    ratio     = ExpressionWrapper(F('ai_price') / F('price'), output_field=FloatField())
    agg = priced_qs.annotate(ratio=ratio).aggregate(
        avg_mult = Avg('ratio'),
        up       = Count('id', filter=Q(ai_price__gt=F('price'))),
        down     = Count('id', filter=Q(ai_price__lt=F('price'))),
    )

    return render(request, 'dashboard/pricing_panel.html', {
        'products':         page, 'page_obj': page, 'search': q,
        'ai_priced_count':  priced_qs.count(),
        'avg_multiplier':   f"×{agg['avg_mult']:.3f}" if agg['avg_mult'] else '—',
        'prices_up':        agg['up'] or 0,
        'prices_down':      agg['down'] or 0,
    })


# ── Users Management ──────────────────────────────────────

@dashboard_permission_required('users')
def users_panel(request):
    """Users management panel."""
    from Users.models import User
    q     = request.GET.get('q', '').strip()
    users = User.objects.annotate(
        order_count=Count('orders', filter=Q(orders__payment_status='paid'), distinct=True),
        total_spent=Sum('orders__total', filter=Q(orders__payment_status='paid'))
    ).order_by('-date_joined')

    if q:
        users = users.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))

    page = Paginator(users, 25).get_page(request.GET.get('page', 1))

    return render(request, 'dashboard/users_panel.html', {
        'users': page, 'page_obj': page, 'search': q,
        'total_users': User.objects.count(),
        'verified':    User.objects.filter(is_verified=True).count(),
        'staff':       User.objects.filter(is_staff=True).count(),
    })


@dashboard_permission_required('users')
def toggle_user_staff(request, user_id):
    """AJAX: toggle a user's staff status (superuser only)."""
    from Users.models import User
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Superuser access required.'}, status=403)
    user = get_object_or_404(User, id=user_id)
    user.is_staff = not user.is_staff
    user.save(update_fields=['is_staff'])
    _log(request, 'update', 'User', str(user_id), user.email, {'is_staff': user.is_staff})
    return JsonResponse({'success': True, 'is_staff': user.is_staff})


# ── AI Models Panel ───────────────────────────────────────

@dashboard_permission_required('ai_models')
def ai_models_panel(request):
    """AI models status, training, and metrics."""
    from ai_recommendations.models import RecommenderModel
    from ai_search.models import SearchQuery
    from reviews.models import Review

    models_status = _ai_model_status()
    recent_model  = RecommenderModel.objects.filter(is_active=True).first()

    return render(request, 'dashboard/ai_models_panel.html', {
        'models_status':  models_status,
        'search_queries': SearchQuery.objects.count(),
        'total_reviews':  Review.objects.count(),
        'recent_model':   recent_model,
    })


@dashboard_permission_required('ai_models')
def retrain_model(request):
    """
    Trigger AI model retraining. Runs synchronously so the demo works
    reliably whether or not a Celery worker is online.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False}, status=405)

    model_key = request.POST.get('model')

    try:
        if model_key == 'recommender':
            from ai_recommendations.recommender import train_recommender
            result = train_recommender()
            msg    = 'Recommendation model retrained!' if result else \
                     'Not enough interaction data to train yet — using popularity fallback.'

        elif model_key == 'search_text':
            from ai_search.semantic_search import build_text_index
            _, ids = build_text_index(force=True)
            msg    = f'Text search index rebuilt ({len(ids)} products).'

        elif model_key == 'search_visual':
            from ai_search.visual_search import build_visual_index
            _, ids = build_visual_index(force=True)
            msg    = f'Visual search index rebuilt ({len(ids)} images).'

        elif model_key == 'sentiment':
            from reviews.sentiment_engine import train_sentiment_model
            train_sentiment_model()
            msg = 'Sentiment classifier retrained!'

        elif model_key == 'fake_review':
            from reviews.sentiment_engine import train_fake_detector
            train_fake_detector()
            msg = 'Fake review detector retrained!'

        elif model_key == 'fraud':
            from payments.fraud_detector import train_fraud_detector
            train_fraud_detector()
            msg = 'Fraud detection model retrained!'

        elif model_key == 'pricing':
            from products.pricing_engine import train_pricing_model
            train_pricing_model()
            msg = 'Dynamic pricing model retrained!'

        elif model_key == 'forecast':
            from analytics.forecasting import train_forecast_model
            train_forecast_model()
            msg = 'Sales forecasting model retrained!'

        elif model_key == 'intent':
            from ai_chatbot.intent_classifier import train_classifier
            train_classifier()
            msg = 'ARIA intent classifier retrained!'

        else:
            return JsonResponse({'success': False, 'error': 'Unknown model.'}, status=400)

        _log(request, 'train', 'AIModel', model_key, model_key)
        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ── Activity Log ──────────────────────────────────────────

@dashboard_permission_required()
def activity_log_view(request):
    """Full audit trail of staff actions."""
    logs   = ActivityLog.objects.select_related('user').order_by('-created_at')
    action = request.GET.get('action', '')
    if action:
        logs = logs.filter(action=action)
    page = Paginator(logs, 50).get_page(request.GET.get('page', 1))
    return render(request, 'dashboard/activity_log.html', {
        'logs': page, 'page_obj': page,
        'action_filter': action,
        'action_choices': ActivityLog.ACTIONS,
    })
