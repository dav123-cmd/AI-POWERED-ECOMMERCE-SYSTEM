"""
ShopAI — Wishlist Service Layer
Helpers for adding/removing items and triggering price-drop /
back-in-stock notifications. Other apps (products admin, inventory
jobs) call these rather than touching WishlistItem directly.
"""
from .models import WishlistItem


def is_wishlisted(user, product):
    if not user or not user.is_authenticated:
        return False
    return WishlistItem.objects.filter(user=user, product=product).exists()


def add_to_wishlist(user, product):
    """Create a wishlist row (snapshotting current price) and record an AI interaction."""
    item, created = WishlistItem.objects.get_or_create(
        user=user, product=product,
        defaults={'price_at_add': product.effective_price}
    )
    if created:
        try:
            from ai_recommendations.tasks import record_interaction_async
            record_interaction_async.delay(str(user.id), str(product.id), 'wishlist')
        except Exception:
            pass
    return item, created


def remove_from_wishlist(user, product):
    return WishlistItem.objects.filter(user=user, product=product).delete()


def toggle_wishlist(user, product):
    """Returns (added: bool, total_count: int)."""
    if is_wishlisted(user, product):
        remove_from_wishlist(user, product)
        return False, user.wishlist_items.count()
    add_to_wishlist(user, product)
    return True, user.wishlist_items.count()


# ── Notification triggers (called from product admin / inventory jobs) ──

def notify_wishlist_back_in_stock(product):
    """Call this when a product transitions from out-of-stock to in-stock."""
    items = WishlistItem.objects.filter(product=product, notify_back_in_stock=True)\
                                .select_related('user')
    users = [i.user for i in items]
    if not users:
        return 0
    try:
        from notifications.services import notify_back_in_stock
        notify_back_in_stock(product, users)
    except Exception:
        pass
    return len(users)


def notify_wishlist_price_drop(product, old_price):
    """
    Call this when a product's price decreases.
    Only notifies users whose saved price is still higher than the new price,
    then refreshes their snapshot so they aren't notified again for the same drop.
    """
    new_price = product.effective_price
    if new_price >= old_price:
        return 0

    items = WishlistItem.objects.filter(
        product=product, notify_price_drop=True, price_at_add__gt=new_price
    ).select_related('user')
    users = [i.user for i in items]
    if not users:
        return 0

    try:
        from notifications.services import notify_price_drop
        notify_price_drop(product, users, old_price, new_price)
    except Exception:
        pass

    items.update(price_at_add=new_price)
    return len(users)


def check_stock_and_price_change(product, previous_stock, previous_price):
    """
    Convenience combined check — call after saving a Product with its
    pre-save stock/price values to fire whichever notifications apply.
    """
    if previous_stock == 0 and product.stock > 0:
        notify_wishlist_back_in_stock(product)
    if previous_price and product.effective_price < previous_price:
        notify_wishlist_price_drop(product, previous_price)
