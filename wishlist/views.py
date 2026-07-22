"""
ShopAI — Wishlist Views
"""
import json
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from .models import WishlistItem
from .services import toggle_wishlist, is_wishlisted
from products.models import Product


@login_required
def index(request):
    """Wishlist page — all saved products with price-drop / stock badges."""
    sort  = request.GET.get('sort', '-added_at')
    SORT_MAP = {
        '-added_at':   '-added_at',
        'added_at':    'added_at',
        'price':       'product__price',
        '-price':      '-product__price',
    }
    items = WishlistItem.objects.filter(user=request.user)\
                                .select_related('product', 'product__category')\
                                .prefetch_related('product__images')\
                                .order_by(SORT_MAP.get(sort, '-added_at'))

    total_value   = sum((i.current_price for i in items), 0)
    price_drops   = [i for i in items if i.price_dropped]
    out_of_stock  = [i for i in items if not i.product.is_in_stock]

    return render(request, 'wishlist/index.html', {
        'items':        items,
        'total_value':  total_value,
        'price_drops':  price_drops,
        'out_of_stock': out_of_stock,
        'sort':         sort,
    })


@login_required
@require_POST
def toggle(request):
    """
    AJAX toggle add/remove. Body: {"product_id": "..."}.
    Returns {"added": bool, "count": int} to match the existing
    toggleWishlist() JS contract in main.js.
    """
    try:
        data       = json.loads(request.body)
        product_id = data.get('product_id')
        product    = get_object_or_404(Product, id=product_id, is_active=True)
        added, count = toggle_wishlist(request.user, product)
        return JsonResponse({'added': added, 'count': count, 'success': True})
    except Exception as e:
        return JsonResponse({'added': False, 'error': str(e), 'success': False}, status=400)


@login_required
@require_POST
def remove_item(request, item_id):
    """Remove a single wishlist row (used on the wishlist page itself)."""
    item = get_object_or_404(WishlistItem, id=item_id, user=request.user)
    item.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'count': request.user.wishlist_items.count()})
    messages.success(request, 'Removed from wishlist.')
    return redirect('wishlist:index')


@login_required
@require_POST
def move_to_cart(request, product_id):
    """Move a single item from wishlist into the cart."""
    from orders.cart_utils import get_or_create_cart
    from orders.models import CartItem

    product = get_object_or_404(Product, id=product_id, is_active=True)
    if not product.is_in_stock:
        return JsonResponse({'success': False, 'error': 'This item is currently out of stock.'})

    cart = get_or_create_cart(request)
    item, created = CartItem.objects.get_or_create(
        cart=cart, product=product, variant=None, defaults={'quantity': 1}
    )
    if not created:
        item.quantity += 1
        item.save()

    WishlistItem.objects.filter(user=request.user, product=product).delete()

    return JsonResponse({
        'success':     True,
        'message':     f'"{product.name}" moved to cart!',
        'cart_count':  cart.items_count,
        'wishlist_count': request.user.wishlist_items.count(),
    })


@login_required
@require_POST
def move_all_to_cart(request):
    """Bulk move every in-stock wishlist item into the cart."""
    from orders.cart_utils import get_or_create_cart
    from orders.models import CartItem

    cart    = get_or_create_cart(request)
    items   = WishlistItem.objects.filter(user=request.user).select_related('product')
    moved   = 0
    skipped = 0

    for wi in items:
        if not wi.product.is_in_stock:
            skipped += 1
            continue
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=wi.product, variant=None, defaults={'quantity': 1}
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        moved += 1

    WishlistItem.objects.filter(user=request.user, product__in=[
        wi.product_id for wi in items if wi.product.is_in_stock
    ]).delete()

    msg = f'Moved {moved} item{"s" if moved != 1 else ""} to cart.'
    if skipped:
        msg += f' {skipped} out-of-stock item{"s" if skipped != 1 else ""} left in wishlist.'

    return JsonResponse({
        'success': True, 'message': msg,
        'moved': moved, 'skipped': skipped,
        'cart_count': cart.items_count,
    })


@login_required
@require_POST
def clear_all(request):
    request.user.wishlist_items.all().delete()
    return JsonResponse({'success': True, 'message': 'Wishlist cleared.'})


@login_required
@require_POST
def update_item_prefs(request, item_id):
    """Toggle per-item price-drop / back-in-stock notification flags."""
    item = get_object_or_404(WishlistItem, id=item_id, user=request.user)
    item.notify_price_drop    = request.POST.get('notify_price_drop') == 'on'
    item.notify_back_in_stock = request.POST.get('notify_back_in_stock') == 'on'
    item.save(update_fields=['notify_price_drop', 'notify_back_in_stock'])
    return JsonResponse({'success': True})
