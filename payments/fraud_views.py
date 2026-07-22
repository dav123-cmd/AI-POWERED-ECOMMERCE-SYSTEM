"""
ShopAI — Fraud Detection Views
"""
import json
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from orders.models import Order
from .fraud_detector import analyze_order, score_and_update_order, train_fraud_detector


@staff_member_required
def fraud_dashboard(request):
    """Admin fraud monitoring dashboard."""
    high_risk = Order.objects.filter(
        fraud_score__gte=0.10
    ).order_by('-fraud_score').select_related('user')[:50]

    stats = {
        'total_orders':    Order.objects.count(),
        'flagged_orders':  Order.objects.filter(fraud_score__gte=0.10).count(),
        'blocked_orders':  Order.objects.filter(fraud_score__gte=0.18, status='cancelled').count(),
        'avg_fraud_score': Order.objects.aggregate(
            avg=__import__('django.db.models', fromlist=['Avg']).Avg('fraud_score')
        )['avg'] or 0,
    }
    return render(request, 'payments/fraud_dashboard.html', {
        'orders': high_risk, 'stats': stats,
    })


@staff_member_required
@require_POST
def analyze_order_view(request, order_number):
    """Re-analyze a specific order for fraud."""
    order  = get_object_or_404(Order, order_number=order_number)
    result = score_and_update_order(order)
    return JsonResponse({'success': True, **result})


@staff_member_required
@require_POST
def retrain_fraud_model(request):
    """Trigger fraud model retraining."""
    try:
        train_fraud_detector()
        return JsonResponse({'success': True, 'message': 'Model retrained successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@staff_member_required
def bulk_analyze(request):
    """Analyze all unscored orders."""
    orders  = Order.objects.filter(fraud_score=0.0, payment_status='paid')[:200]
    results = []
    for order in orders:
        r = score_and_update_order(order)
        results.append({'order': order.order_number, 'score': r['score'], 'action': r['action']})
    flagged = sum(1 for r in results if r['action'] in ('review','block'))
    return JsonResponse({
        'success': True,
        'analyzed': len(results),
        'flagged': flagged,
        'results': results[:20],
    })
