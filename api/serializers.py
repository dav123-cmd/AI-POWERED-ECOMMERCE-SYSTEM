"""
ShopAI — REST API Serializers
Mirrors the same business rules used by the web views (cart_utils,
sentiment_engine, fraud_detector, ARIA engine) so the API is a true
second front-end onto the same backend, not a parallel implementation.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.types import OpenApiTypes

from products.models import Category, Brand, Tag, Product, ProductImage, ProductVariant
from orders.models import Cart, CartItem, Order, OrderItem
from reviews.models import Review
from wishlist.models import WishlistItem
from notifications.models import Notification
from Users.models import Address

User = get_user_model()


# ── Users / Auth ──────────────────────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirm password')

    class Meta:
        model  = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'password', 'password2']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(password=password, **validated_data)
        return user


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Address
        fields = ['id', 'label', 'address_type', 'full_name', 'phone', 'address_line1',
                  'address_line2', 'city', 'state', 'country', 'postal_code', 'is_default']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class UserSerializer(serializers.ModelSerializer):
    full_name      = serializers.CharField(source='get_full_name', read_only=True)
    avatar_url     = serializers.CharField(read_only=True)
    wishlist_count = serializers.IntegerField(read_only=True)
    addresses      = AddressSerializer(many=True, read_only=True)

    class Meta:
        model  = User
        fields = ['id', 'email', 'first_name', 'last_name', 'full_name', 'phone',
                  'avatar_url', 'bio', 'date_of_birth', 'gender', 'is_verified',
                  'preferred_categories', 'wishlist_count', 'addresses', 'date_joined']
        read_only_fields = ['id', 'email', 'is_verified', 'date_joined']


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['first_name', 'last_name', 'phone', 'bio', 'date_of_birth',
                  'gender', 'preferred_categories']


# ── Products ──────────────────────────────────────────────

class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model  = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'parent',
                  'icon', 'is_featured', 'product_count']


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Brand
        fields = ['id', 'name', 'slug', 'logo', 'website']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Tag
        fields = ['id', 'name', 'slug']


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ProductVariant
        fields = ['id', 'name', 'value', 'stock', 'price_modifier', 'is_available']


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list/search results."""
    primary_image      = serializers.SerializerMethodField()
    effective_price     = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discount_percent    = serializers.IntegerField(read_only=True)
    is_on_sale          = serializers.BooleanField(read_only=True)
    is_in_stock         = serializers.BooleanField(read_only=True)
    category_name      = serializers.CharField(source='category.name', read_only=True, default=None)

    class Meta:
        model  = Product
        fields = ['id', 'name', 'slug', 'short_desc', 'price', 'compare_price', 'ai_price',
                  'effective_price', 'discount_percent', 'is_on_sale', 'is_in_stock',
                  'is_new', 'is_featured', 'rating_avg', 'rating_count',
                  'category_name', 'primary_image']

    @extend_schema_field(OpenApiTypes.URI)
    def get_primary_image(self, obj):
        img = obj.primary_image
        if not img:
            return None
        request = self.context.get('request')
        url = img.image.url
        return request.build_absolute_uri(url) if request else url


class ProductDetailSerializer(ProductListSerializer):
    """Full serializer for retrieve views — adds nested images/variants/tags."""
    images      = ProductImageSerializer(many=True, read_only=True)
    variants    = ProductVariantSerializer(many=True, read_only=True)
    tags        = TagSerializer(many=True, read_only=True)
    category    = CategorySerializer(read_only=True)
    brand       = BrandSerializer(read_only=True)
    is_low_stock= serializers.BooleanField(read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            'description', 'sku', 'stock', 'is_low_stock', 'category', 'brand',
            'images', 'variants', 'tags', 'view_count', 'purchase_count', 'created_at',
        ]


# ── Cart ──────────────────────────────────────────────────

class CartItemSerializer(serializers.ModelSerializer):
    product    = ProductListSerializer(read_only=True)
    variant    = ProductVariantSerializer(read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model  = CartItem
        fields = ['id', 'product', 'variant', 'quantity', 'unit_price', 'line_total', 'added_at']


class CartSerializer(serializers.ModelSerializer):
    items        = CartItemSerializer(many=True, read_only=True)
    items_count  = serializers.IntegerField(read_only=True)
    subtotal     = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total        = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    coupon_code  = serializers.CharField(source='coupon.code', read_only=True, default=None)

    class Meta:
        model  = Cart
        fields = ['id', 'items', 'items_count', 'subtotal', 'discount_amount', 'total',
                  'coupon_code', 'updated_at']


class CartAddSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity   = serializers.IntegerField(default=1, min_value=1)


class CartUpdateSerializer(serializers.Serializer):
    item_id  = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=0)


# ── Orders ────────────────────────────────────────────────

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model  = OrderItem
        fields = ['id', 'product', 'product_name', 'variant_info', 'sku',
                  'quantity', 'unit_price', 'total_price']


class OrderSerializer(serializers.ModelSerializer):
    items           = OrderItemSerializer(many=True, read_only=True)
    status_display  = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    is_cancellable  = serializers.BooleanField(read_only=True)
    shipping_address= serializers.CharField(read_only=True)

    class Meta:
        model  = Order
        fields = ['id', 'order_number', 'email', 'phone', 'items',
                  'shipping_name', 'shipping_address', 'shipping_city', 'shipping_country',
                  'subtotal', 'discount_amount', 'shipping_fee', 'tax_amount', 'total',
                  'coupon_code', 'status', 'status_display', 'payment_status',
                  'payment_status_display', 'payment_method', 'tracking_number',
                  'is_cancellable', 'created_at', 'delivered_at']
        read_only_fields = ['order_number', 'subtotal', 'total', 'status', 'payment_status']


class CheckoutSerializer(serializers.Serializer):
    """Creates an Order from the user's current cart (mirrors orders.views._process_checkout)."""
    email            = serializers.EmailField()
    phone            = serializers.CharField(required=False, allow_blank=True)
    shipping_name    = serializers.CharField(max_length=120)
    shipping_line1   = serializers.CharField(max_length=200)
    shipping_line2   = serializers.CharField(max_length=200, required=False, allow_blank=True)
    shipping_city    = serializers.CharField(max_length=100)
    shipping_state    = serializers.CharField(max_length=100)
    shipping_country = serializers.CharField(max_length=100, default='Kenya')
    shipping_postal   = serializers.CharField(max_length=20, required=False, allow_blank=True)
    payment_method   = serializers.ChoiceField(choices=['stripe', 'paypal', 'mpesa'])
    notes            = serializers.CharField(required=False, allow_blank=True)


# ── Reviews ───────────────────────────────────────────────

class ReviewSerializer(serializers.ModelSerializer):
    user_name        = serializers.CharField(source='user.get_full_name', read_only=True)
    user_avatar      = serializers.CharField(source='user.avatar_url', read_only=True)
    has_purchased    = serializers.SerializerMethodField()

    class Meta:
        model  = Review
        fields = ['id', 'product', 'user_name', 'user_avatar', 'rating', 'title', 'comment',
                  'sentiment', 'sentiment_score', 'has_purchased', 'helpful_count',
                  'is_approved', 'created_at']
        read_only_fields = ['sentiment', 'sentiment_score', 'is_approved', 'helpful_count']

    @extend_schema_field(serializers.BooleanField())
    def get_has_purchased(self, obj):
        return bool(obj.order_id)


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Review
        fields = ['product', 'rating', 'title', 'comment']

    def validate_comment(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError('Review must be at least 10 characters.')
        return value

    def validate(self, attrs):
        request = self.context['request']
        if Review.objects.filter(product=attrs['product'], user=request.user).exists():
            raise serializers.ValidationError('You have already reviewed this product.')
        return attrs

    def create(self, validated_data):
        from orders.models import Order
        request = self.context['request']
        order = Order.objects.filter(
            user=request.user, payment_status='paid', items__product=validated_data['product']
        ).order_by('-created_at').first()
        return Review.objects.create(user=request.user, order=order, **validated_data)


# ── Wishlist ──────────────────────────────────────────────

class WishlistItemSerializer(serializers.ModelSerializer):
    product          = ProductListSerializer(read_only=True)
    product_id       = serializers.UUIDField(write_only=True)
    current_price    = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    price_dropped    = serializers.BooleanField(read_only=True)
    price_drop_pct   = serializers.IntegerField(read_only=True)

    class Meta:
        model  = WishlistItem
        fields = ['id', 'product', 'product_id', 'current_price', 'price_dropped',
                  'price_drop_pct', 'notify_price_drop', 'notify_back_in_stock', 'added_at']

    def create(self, validated_data):
        from products.models import Product
        product = Product.objects.get(id=validated_data.pop('product_id'))
        request = self.context['request']
        item, _ = WishlistItem.objects.get_or_create(
            user=request.user, product=product,
            defaults={'price_at_add': product.effective_price}
        )
        return item


# ── Notifications ─────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    time_ago         = serializers.CharField(read_only=True)

    class Meta:
        model  = Notification
        fields = ['id', 'category', 'category_display', 'level', 'title', 'message',
                  'icon', 'link', 'is_read', 'time_ago', 'created_at']


# ── AI: Search / Recommendations / Chat ──────────────────

class SemanticSearchQuerySerializer(serializers.Serializer):
    q          = serializers.CharField(max_length=500)
    category   = serializers.CharField(required=False, allow_blank=True)
    min_price  = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    max_price  = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    top_k      = serializers.IntegerField(default=24, min_value=1, max_value=48)


class ChatMessageSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=1000)


class ChatReplySerializer(serializers.Serializer):
    reply       = serializers.CharField()
    intent      = serializers.CharField()
    confidence  = serializers.FloatField()
    session_id  = serializers.CharField()


# ── Small response-shape serializers (for OpenAPI schema accuracy) ──

class HealthCheckSerializer(serializers.Serializer):
    status  = serializers.CharField()
    service = serializers.CharField()
    version = serializers.CharField()


class SearchResponseSerializer(serializers.Serializer):
    query   = serializers.CharField()
    count   = serializers.IntegerField()
    results = ProductListSerializer(many=True)


class VisualSearchResponseSerializer(serializers.Serializer):
    count   = serializers.IntegerField()
    results = ProductListSerializer(many=True)


class RecommendationsResponseSerializer(serializers.Serializer):
    personalized = serializers.BooleanField()
    results      = ProductListSerializer(many=True)


class WishlistToggleSerializer(serializers.Serializer):
    added = serializers.BooleanField()
    count = serializers.IntegerField()


class WishlistToggleRequestSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()


class SimpleSuccessSerializer(serializers.Serializer):
    success = serializers.BooleanField()
