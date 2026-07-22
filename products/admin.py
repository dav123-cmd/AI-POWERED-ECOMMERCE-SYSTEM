

# Register your models here.
from django.contrib import admin
from .models import Category, Brand, Tag, Product, ProductImage, ProductVariant,TeamMember, CompanyValue,FloatingProduct
class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 2

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display  = ('name','category','brand','price','stock','is_active','is_featured','rating_avg','created_at')
    list_filter   = ('is_active','is_featured','is_new','status','category','brand')
    search_fields = ('name','sku','description')
    prepopulated_fields = {'slug': ('name',)}
    inlines       = [ProductImageInline, ProductVariantInline]
    list_editable = ('is_active','is_featured','price','stock')
    readonly_fields = ('view_count','purchase_count','rating_avg','rating_count','created_at','updated_at')
    fieldsets = (
        ('Basic Info',  {'fields': ('name','slug','category','brand','tags','short_desc','description')}),
        ('Pricing',     {'fields': ('price','compare_price','cost_price','ai_price')}),
        ('Inventory',   {'fields': ('sku','stock','low_stock_threshold','track_inventory')}),
        ('Status',      {'fields': ('status','is_active','is_featured','is_new')}),
        ('SEO',         {'fields': ('meta_title','meta_desc')}),
        ('Stats',       {'fields': ('view_count','purchase_count','rating_avg','rating_count')}),
        ('Timestamps',  {'fields': ('created_at','updated_at')}),
    )

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name','parent','is_featured','order','product_count')
    list_editable = ('is_featured','order')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name','slug','website')
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Tag)



@admin.register(FloatingProduct)
class FloatingProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'card_type', 'price', 'is_active')
    list_filter = ('card_type', 'is_active')
admin.site.register(TeamMember)
admin.site.register(CompanyValue)