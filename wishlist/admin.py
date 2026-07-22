from django.contrib import admin
from .models import WishlistItem

@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display  = ('user', 'product', 'price_at_add', 'price_dropped', 'added_at')
    list_filter   = ('notify_price_drop', 'notify_back_in_stock')
    search_fields = ('user__email', 'product__name')
    readonly_fields = ('added_at',)

    def price_dropped(self, obj):
        return obj.price_dropped
    price_dropped.boolean = True
    price_dropped.short_description = 'Price Dropped?'
