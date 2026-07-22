"""
ShopAI — Reviews & Ratings Models
"""
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class Review(models.Model):
    SENTIMENT = [
        ('positive', 'Positive'),
        ('neutral',  'Neutral'),
        ('negative', 'Negative'),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product     = models.ForeignKey('products.Product', on_delete=models.CASCADE,
                                    related_name='reviews')
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='reviews')
    order       = models.ForeignKey('orders.Order', null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='reviews')

    # Rating & content
    rating      = models.PositiveSmallIntegerField(
                      validators=[MinValueValidator(1), MaxValueValidator(5)])
    title       = models.CharField(max_length=150, blank=True)
    comment     = models.TextField()
    images      = models.JSONField(default=list, blank=True)  # list of image URLs

    # AI analysis
    sentiment        = models.CharField(max_length=10, choices=SENTIMENT, blank=True)
    sentiment_score  = models.FloatField(default=0.0)   # -1 (neg) to +1 (pos)
    is_fake_flag     = models.BooleanField(default=False)
    fake_probability = models.FloatField(default=0.0)   # 0–1
    ai_summary       = models.TextField(blank=True)     # AI-generated summary sentence

    # Moderation
    is_approved  = models.BooleanField(default=False)
    is_flagged   = models.BooleanField(default=False)
    flag_reason  = models.CharField(max_length=200, blank=True)

    # Helpfulness votes
    helpful_count    = models.PositiveIntegerField(default=0)
    not_helpful_count= models.PositiveIntegerField(default=0)

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering        = ['-created_at']
        unique_together = ['product', 'user']
        indexes         = [
            models.Index(fields=['product', 'is_approved']),
            models.Index(fields=['sentiment']),
        ]

    def __str__(self):
        return f'{self.user} → {self.product} ({self.rating}★)'

    @property
    def helpfulness_ratio(self):
        total = self.helpful_count + self.not_helpful_count
        return self.helpful_count / total if total > 0 else 0.5


class ReviewVote(models.Model):
    """Track helpful/not-helpful votes."""
    review     = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='votes')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_helpful = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['review', 'user']


class ProductSentimentSummary(models.Model):
    """
    AI-generated summary of all reviews for a product.
    Rebuilt after each new review.
    """
    product             = models.OneToOneField('products.Product', on_delete=models.CASCADE,
                                               related_name='sentiment_summary')
    positive_count      = models.PositiveIntegerField(default=0)
    neutral_count       = models.PositiveIntegerField(default=0)
    negative_count      = models.PositiveIntegerField(default=0)
    avg_sentiment_score = models.FloatField(default=0.0)
    top_positive_phrases= models.JSONField(default=list)  # e.g. ["great quality", "fast delivery"]
    top_negative_phrases= models.JSONField(default=list)
    ai_summary          = models.TextField(blank=True)
    updated_at          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Sentiment: {self.product.name}'

    @property
    def positive_pct(self):
        total = self.positive_count + self.neutral_count + self.negative_count
        return round(self.positive_count / total * 100) if total > 0 else 0
