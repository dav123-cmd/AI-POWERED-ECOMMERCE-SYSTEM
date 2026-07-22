"""
ShopAI — Recommendations Views
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from .recommender import (get_recommendations, get_similar_products,
                           get_frequently_bought_together, record_interaction)


@login_required
def recommendations_page(request):
    """Full personalized recommendations page."""
    products = get_recommendations(request.user, top_k=24)
    return render(request, 'ai_recommendations/recommendations.html', {
        'products': products, 'is_personalized': True,
    })


@require_GET
def recommendations_api(request):
    """
    AJAX endpoint — returns JSON list of recommended products.
    Used for homepage widget + product page sidebar.
    """
    if not request.user.is_authenticated:
        from products.models import Product
        products = Product.objects.filter(is_active=True)\
                                  .order_by('-purchase_count').prefetch_related('images')[:8]
    else:
        products = get_recommendations(request.user, top_k=8)

    data = [{
        'id':       str(p.id),
        'name':     p.name,
        'price':    float(p.effective_price),
        'old_price':float(p.compare_price) if p.compare_price else None,
        'url':      p.get_absolute_url(),
        'image':    p.primary_image.image.url if p.primary_image else '',
        'category': p.category.name if p.category else '',
        'rating':   float(p.rating_avg),
        'discount': p.discount_percent,
    } for p in products]

    return JsonResponse({'success': True, 'products': data, 'count': len(data)})


@require_GET
def similar_products_api(request, product_id):
    """AJAX — products similar to a given product."""
    from products.models import Product
    try:
        product  = Product.objects.get(id=product_id, is_active=True)
        products = get_similar_products(product, top_k=6)
        data = [{
            'id':    str(p.id),
            'name':  p.name,
            'price': float(p.effective_price),
            'url':   p.get_absolute_url(),
            'image': p.primary_image.image.url if p.primary_image else '',
        } for p in products]
        return JsonResponse({'success': True, 'products': data})
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)


@require_GET
def bought_together_api(request, product_id):
    """AJAX — products frequently bought with this one."""
    from products.models import Product
    try:
        product  = Product.objects.get(id=product_id, is_active=True)
        products = get_frequently_bought_together(product, top_k=4)
        data = [{
            'id':    str(p.id),
            'name':  p.name,
            'price': float(p.effective_price),
            'url':   p.get_absolute_url(),
            'image': p.primary_image.image.url if p.primary_image else '',
        } for p in products]
        return JsonResponse({'success': True, 'products': data})
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)


def track_interaction(request, product_id, interaction_type):
    """Record a user interaction (called via AJAX)."""
    from products.models import Product
    from django.views.decorators.http import require_POST

    if not request.user.is_authenticated:
        return JsonResponse({'success': False})
    actions = [
    ("View", "fa-eye", "1x"),
    ("Wishlist", "fa-heart", "2x"),
    ("Cart", "fa-shopping-cart", "3x"),
    ("Purchase", "fa-check-circle", "5x"),
]
    #VALID = ('view', 'wishlist', 'cart', 'purchase')
    if interaction_type not in actions:
        return JsonResponse({'success': False, 'error': 'Invalid type'}, status=400)

    try:
        product = Product.objects.get(id=product_id, is_active=True)
        # Fire async Celery task to avoid blocking
        from .tasks import record_interaction_async
        record_interaction_async.delay(str(request.user.id), str(product.id), interaction_type)
        return JsonResponse({'success': True})
    except Product.DoesNotExist:
        return JsonResponse({'success': False}, status=404)
