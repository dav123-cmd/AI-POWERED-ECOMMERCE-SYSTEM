from .models import Cart, CartItem


def get_or_create_cart(request):
    """Return the cart for the current user or session."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        # Merge anonymous cart if exists
        if request.session.session_key:
            anon = Cart.objects.filter(session_key=request.session.session_key, user=None).first()
            if anon:
                for item in anon.items.all():
                    existing = cart.items.filter(product=item.product, variant=item.variant).first()
                    if existing:
                        existing.quantity += item.quantity
                        existing.save()
                    else:
                        item.cart = cart
                        item.save()
                anon.delete()
        return cart
    # Anonymous
    if not request.session.session_key:
        request.session.create()
    cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user=None)
    return cart


def get_cart_count(request):
    try:
        cart = get_or_create_cart(request)
        return cart.items_count
    except Exception:
        return 0
