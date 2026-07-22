from django.contrib import admin

# Register your models here.
from .models import Order, OrderItem, Cart, CartItem, Coupon, OrderStatusHistory

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name','sku','quantity','unit_price','total_price')

class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ('status','note','changed_by','changed_at')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ('order_number','user','email','total','status','payment_status','created_at')
    list_filter   = ('status','payment_status','payment_method')
    search_fields = ('order_number','email','phone','shipping_name')
    readonly_fields = ('order_number','id','created_at','updated_at','fraud_score')
    inlines       = [OrderItemInline, StatusHistoryInline]
    list_editable = ('status','payment_status')

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code','coupon_type','value','usage_count','usage_limit','is_active','valid_to')
    list_editable = ('is_active',)
    search_fields = ('code',)

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('id','user','session_key','items_count','updated_at')
