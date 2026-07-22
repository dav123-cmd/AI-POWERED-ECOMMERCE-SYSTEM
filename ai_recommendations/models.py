"""
ShopAI — Recommendations Models
Stores interaction data for collaborative filtering training.
"""
from django.db import models
from django.conf import settings


class UserProductInteraction(models.Model):
    """
    Tracks all user-product interactions for training the recommender.
    Interaction types weighted by importance for training:
      purchase=5, cart=3, wishlist=2, view=1
    """
    TYPES = [
        ('view',     'View',     ),
        ('wishlist', 'Wishlist', ),
        ('cart',     'Add to Cart'),
        ('purchase', 'Purchase', ),
    ]
    WEIGHTS = {'view': 1.0, 'wishlist': 2.0, 'cart': 3.0, 'purchase': 5.0}

    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='product_interactions')
    product     = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                    related_name='user_interactions')
    interaction = models.CharField(max_length=10, choices=TYPES)
    weight      = models.FloatField(default=1.0)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['user', 'product']),
            models.Index(fields=['user', 'interaction']),
        ]

    def save(self, *args, **kwargs):
        self.weight = self.WEIGHTS.get(self.interaction, 1.0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} — {self.interaction} — {self.product}'


class RecommenderModel(models.Model):
    """Tracks trained model checkpoints."""
    version       = models.CharField(max_length=50)
    model_path    = models.CharField(max_length=500)
    n_users       = models.PositiveIntegerField(default=0)
    n_products    = models.PositiveIntegerField(default=0)
    embedding_dim = models.PositiveIntegerField(default=64)
    train_loss    = models.FloatField(null=True, blank=True)
    is_active     = models.BooleanField(default=False)
    trained_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-trained_at']

    def __str__(self):
        return f'RecommenderModel v{self.version} (active={self.is_active})'


class SimilarProduct(models.Model):
    """
    Pre-computed product similarity pairs.
    Rebuilt after each model retrain.
    """
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                 related_name='similar_products')
    similar = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                 related_name='similar_to')
    score   = models.FloatField()  # cosine similarity in embedding space

    class Meta:
        unique_together = ['product', 'similar']
        ordering        = ['-score']

    def __str__(self):
        return f'{self.product.name} → {self.similar.name} ({self.score:.3f})'
