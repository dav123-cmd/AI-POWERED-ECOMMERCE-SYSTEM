import json
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.admin.views.decorators import staff_member_required
from .pricing_engine import get_dynamic_price, update_product_ai_prices
from .models import Product


@require_GET
def get_price_api(request, product_id):
    """
    AJAX: get AI-optimized price for a product.
    Optional: pass ?user=1 to include user-segment pricing.
    """
    try:
        product   = Product.objects.get(id=product_id, is_active=True)
        user      = request.user if request.user.is_authenticated else None
        ai_price, multiplier = get_dynamic_price(product, user)

        return JsonResponse({
            'success':    True,
            'product_id': str(product.id),
            'base_price': float(product.price),
            'ai_price':   float(ai_price) if ai_price else float(product.price),
            'multiplier': multiplier or 1.0,
            'savings':    float(product.compare_price - ai_price)
                          if (product.compare_price and ai_price and ai_price < product.compare_price)
                          else 0,
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)


@staff_member_required
def update_all_prices(request):
    """Admin endpoint: recalculate AI prices for all products."""
    count = update_product_ai_prices()
    return JsonResponse({'success': True, 'updated': count})
