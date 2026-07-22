"""
ShopAI — Wishlist Models
A flat per-user wishlist (one row per saved product), with
price-drop and back-in-stock tracking baked in.
"""
from django.db import models
from django.conf import settings
import uuid


class WishlistItem(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                 related_name='wishlist_items')
    product  = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                 related_name='wishlist_items')

    # Snapshot of the price when saved — used to detect drops later
    price_at_add = models.DecimalField(max_digits=10, decimal_places=2)

    # Per-item notification preferences
    notify_price_drop    = models.BooleanField(default=True)
    notify_back_in_stock = models.BooleanField(default=True)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'product']
        ordering        = ['-added_at']
        indexes         = [models.Index(fields=['user', '-added_at'])]

    def __str__(self):
        return f'{self.user} {self.product}'

    @property
    def current_price(self):
        return self.product.effective_price

    @property
    def price_dropped(self):
        return self.current_price < self.price_at_add

    @property
    def price_drop_amount(self):
        diff = self.price_at_add - self.current_price
        return diff if diff > 0 else 0

    @property
    def price_drop_pct(self):
        if self.price_at_add and self.price_dropped:
            return round(float(self.price_drop_amount) / float(self.price_at_add) * 100)
        return 0
