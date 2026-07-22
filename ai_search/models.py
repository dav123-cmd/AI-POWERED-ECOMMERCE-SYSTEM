from django.db import models

# Create your models here.
from django.conf import settings


class SearchQuery(models.Model):
    """Log every search for analytics and model retraining."""
    TYPES = [('text','Text'),('semantic','Semantic'),('visual','Visual')]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='searches')
    session_key  = models.CharField(max_length=40, blank=True)
    query        = models.CharField(max_length=500)
    search_type  = models.CharField(max_length=10, choices=TYPES, default='semantic')
    results_count= models.PositiveIntegerField(default=0)
    clicked_product = models.ForeignKey('products.Product', null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='search_clicks')
    ip_address   = models.GenericIPAddressField(null=True, blank=True)
    searched_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-searched_at']

    def __str__(self):
        return f'"{self.query}" ({self.search_type})'


class FAISSIndex(models.Model):
    """Tracks when the FAISS vector index was last built."""
    index_type   = models.CharField(max_length=20)  # 'text' or 'visual'
    product_count= models.PositiveIntegerField(default=0)
    index_path   = models.CharField(max_length=500)
    built_at     = models.DateTimeField(auto_now_add=True)
    is_active    = models.BooleanField(default=True)

    class Meta:
        ordering = ['-built_at']

    def __str__(self):
        return f'FAISS {self.index_type} index — {self.product_count} products'
