from django.db import models

# Create your models here.
from django.conf import settings
from django.utils import timezone
import uuid


class Cart(models.Model):
    """Session-based or user-based cart."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       null=True, blank=True, related_name='cart')
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    coupon      = models.ForeignKey('Coupon', null=True, blank=True, on_delete=models.SET_NULL)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'Cart({self.user or self.session_key})'

    @property
    def items_count(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def subtotal(self):
        return sum(i.line_total for i in self.items.select_related('product'))

    @property
    def discount_amount(self):
        if self.coupon and self.coupon.is_valid():
            return self.coupon.calculate_discount(self.subtotal)
        return 0

    @property
    def total(self):
        return max(self.subtotal - self.discount_amount, 0)


class CartItem(models.Model):
    cart     = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product  = models.ForeignKey('products.Product', on_delete=models.CASCADE)
    variant  = models.ForeignKey('products.ProductVariant', null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['cart', 'product', 'variant']

    def __str__(self):
        return f'{self.quantity}x {self.product.name}'

    @property
    def unit_price(self):
        base = self.product.effective_price
        if self.variant:
            base += self.variant.price_modifier
        return base

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class Order(models.Model):
    STATUS = [
        ('pending',    'Pending'),
        ('confirmed',  'Confirmed'),
        ('processing', 'Processing'),
        ('shipped',    'Shipped'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
        ('refunded',   'Refunded'),
    ]
    PAYMENT_STATUS = [
        ('unpaid',    'Unpaid'),
        ('paid',      'Paid'),
        ('refunded',  'Refunded'),
        ('partially', 'Partially Refunded'),
    ]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number    = models.CharField(max_length=20, unique=True, blank=True)
    user            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                        null=True, blank=True, related_name='orders')
    email           = models.EmailField()
    phone           = models.CharField(max_length=20, blank=True)

    # Shipping
    shipping_name   = models.CharField(max_length=120)
    shipping_line1  = models.CharField(max_length=200)
    shipping_line2  = models.CharField(max_length=200, blank=True)
    shipping_city   = models.CharField(max_length=100)
    shipping_state  = models.CharField(max_length=100)
    shipping_country= models.CharField(max_length=100, default='Kenya')
    shipping_postal = models.CharField(max_length=20, blank=True)

    # Amounts
    subtotal        = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_fee    = models.DecimalField(max_digits=8,  decimal_places=2, default=0)
    tax_amount      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total           = models.DecimalField(max_digits=12, decimal_places=2)

    # Coupon
    coupon_code     = models.CharField(max_length=50, blank=True)

    # Status
    status          = models.CharField(max_length=12, choices=STATUS, default='pending', db_index=True)
    payment_status  = models.CharField(max_length=10, choices=PAYMENT_STATUS, default='unpaid')
    payment_method  = models.CharField(max_length=30, blank=True)

    # Tracking
    tracking_number = models.CharField(max_length=100, blank=True)
    notes           = models.TextField(blank=True)

    # AI fraud score (0-1, higher = more suspicious)
    fraud_score     = models.FloatField(default=0.0)

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)
    delivered_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [models.Index(fields=['order_number']), models.Index(fields=['user', '-created_at'])]

    def __str__(self):
        return f'Order #{self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            ts = timezone.now().strftime('%y%m%d%H%M')
            short = str(self.id)[:4].upper()
            self.order_number = f'SAI-{ts}-{short}'
        super().save(*args, **kwargs)

    @property
    def shipping_address(self):
        parts = [self.shipping_name, self.shipping_line1]
        if self.shipping_line2:
            parts.append(self.shipping_line2)
        parts += [self.shipping_city, self.shipping_state, self.shipping_country]
        return ', '.join(parts)

    @property
    def is_cancellable(self):
        return self.status in ('pending', 'confirmed')


class OrderItem(models.Model):
    order       = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product     = models.ForeignKey('products.Product', on_delete=models.SET_NULL, null=True)
    product_name= models.CharField(max_length=255)   # snapshot
    variant_info= models.CharField(max_length=200, blank=True)
    sku         = models.CharField(max_length=100, blank=True)
    quantity    = models.PositiveIntegerField()
    unit_price  = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.quantity}x {self.product_name}'


class OrderStatusHistory(models.Model):
    order      = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    status     = models.CharField(max_length=12)
    note       = models.TextField(blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-changed_at']


class Coupon(models.Model):
    TYPE = [('percent', 'Percentage'), ('fixed', 'Fixed Amount')]
    code            = models.CharField(max_length=50, unique=True)
    coupon_type     = models.CharField(max_length=10, choices=TYPE, default='percent')
    value           = models.DecimalField(max_digits=8, decimal_places=2)
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usage_limit     = models.PositiveIntegerField(null=True, blank=True)
    usage_count     = models.PositiveIntegerField(default=0)
    is_active       = models.BooleanField(default=True)
    valid_from      = models.DateTimeField()
    valid_to        = models.DateTimeField()
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_to:
            return False
        if self.usage_limit and self.usage_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, subtotal):
        if subtotal < self.min_order_value:
            return 0
        if self.coupon_type == 'percent':
            discount = subtotal * (self.value / 100)
            if self.max_discount:
                discount = min(discount, self.max_discount)
            return discount
        return min(self.value, subtotal)
