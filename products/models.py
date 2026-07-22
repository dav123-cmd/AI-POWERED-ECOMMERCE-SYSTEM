
"""
ShopAI — Products Models
"""
from django.db import models
from django.utils.text import slugify
from django.urls import reverse
from django.conf import settings
import uuid


class Category(models.Model):
    name        = models.CharField(max_length=100, unique=True)
    slug        = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    image       = models.ImageField(upload_to='categories/', null=True, blank=True)
    parent      = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children')
    icon        = models.CharField(max_length=50, blank=True, help_text='FontAwesome class e.g. fa-shirt')
    is_featured = models.BooleanField(default=False)
    order       = models.PositiveIntegerField(default=0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'categories'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('products:category', kwargs={'slug': self.slug})

    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()


class Brand(models.Model):
    name    = models.CharField(max_length=100, unique=True)
    slug    = models.SlugField(unique=True, blank=True)
    logo    = models.ImageField(upload_to='brands/', null=True, blank=True)
    website = models.URLField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


def product_image_path(instance, filename):
    ext = filename.split('.')[-1]
    return f'products/{instance.product.id}/{uuid.uuid4()}.{ext}'


class Product(models.Model):
    STATUS_CHOICES = [
        ('active',   'Active'),
        ('inactive', 'Inactive'),
        ('draft',    'Draft'),
    ]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name         = models.CharField(max_length=255)
    slug         = models.SlugField(unique=True, blank=True, max_length=255)
    description  = models.TextField()
    short_desc   = models.CharField(max_length=300, blank=True)
    category     = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    brand        = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    tags         = models.ManyToManyField(Tag, blank=True, related_name='products')

    # Pricing
    price        = models.DecimalField(max_digits=10, decimal_places=2)
    compare_price= models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text='Original price before discount')
    cost_price   = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                       help_text='Cost price (for profit calculation)')

    # AI dynamic price (set by PyTorch model)
    ai_price     = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Inventory
    sku          = models.CharField(max_length=100, unique=True, blank=True)
    stock        = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    track_inventory    = models.BooleanField(default=True)

    # Status
    status       = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    is_active    = models.BooleanField(default=True)
    is_featured  = models.BooleanField(default=False)
    is_new       = models.BooleanField(default=True)

    # SEO
    meta_title   = models.CharField(max_length=255, blank=True)
    meta_desc    = models.TextField(blank=True, max_length=300)

    # AI Embeddings (stored as JSON for FAISS indexing)
    text_embedding   = models.JSONField(null=True, blank=True)
    visual_embedding = models.JSONField(null=True, blank=True)

    # Stats (updated by signals/tasks)
    view_count     = models.PositiveIntegerField(default=0)
    purchase_count = models.PositiveIntegerField(default=0)
    rating_avg     = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count   = models.PositiveIntegerField(default=0)

    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='products_created')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['slug']),
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['is_featured', 'is_active']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        if not self.sku:
            self.sku = f'SKU-{str(self.id)[:8].upper()}'
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('products:detail', kwargs={'slug': self.slug})

    @property
    def primary_image(self):
        img = self.images.filter(is_primary=True).first()
        return img or self.images.first()

    @property
    def discount_percent(self):
        if self.compare_price and self.compare_price > self.price:
            return int(((self.compare_price - self.price) / self.compare_price) * 100)
        return 0

    @property
    def is_on_sale(self):
        return self.discount_percent > 0

    @property
    def is_in_stock(self):
        return not self.track_inventory or self.stock > 0

    @property
    def is_low_stock(self):
        return self.track_inventory and 0 < self.stock <= self.low_stock_threshold

    @property
    def effective_price(self):
        return self.ai_price or self.price


class ProductImage(models.Model):
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image      = models.ImageField(upload_to=product_image_path)
    alt_text   = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order      = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-is_primary', 'order']

    def save(self, *args, **kwargs):
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    """Size, Color, etc. variants of a product."""
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name       = models.CharField(max_length=100)   # e.g. "Size"
    value      = models.CharField(max_length=100)   # e.g. "XL"
    sku_suffix = models.CharField(max_length=50, blank=True)
    stock      = models.PositiveIntegerField(default=0)
    price_modifier = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_available   = models.BooleanField(default=True)

    class Meta:
        unique_together = ['product', 'name', 'value']

    def __str__(self):
        return f'{self.product.name} — {self.name}: {self.value}'


class ProductView(models.Model):
    """Track product views for AI recommendations."""
    product    = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='views')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='product_views')
    session_key= models.CharField(max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-viewed_at']



class FloatingProduct(models.Model):
    # Setup placement choices to assign products to the Big or Small card slots
    CARD_CHOICES = [
        ('big', 'Big Card (Air Max Slot)'),
        ('small', 'Small Card (Leather Tote Slot)'),
    ]
    
    name = models.CharField(max_length=100)
    price = models.IntegerField(help_text="Price in KES")
    discount_percentage = models.IntegerField(blank=True, null=True, help_text="Optional: e.g., 20 for -20%")
    image = models.ImageField( upload_to='floating_products/')
    card_type = models.CharField(max_length=10, choices=CARD_CHOICES, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_card_type_display()})"



class TeamMember(models.Model):
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=100)
    bio = models.TextField()
    image = models.ImageField(upload_to='team/')
    linkedin_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return self.name

class CompanyValue(models.Model):
    title = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, help_text="e.g., fa-solid fa-star")

    def __str__(self):
        return self.title