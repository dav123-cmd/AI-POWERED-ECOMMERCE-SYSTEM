from django.contrib import admin
from .models import Review, ReviewVote, ProductSentimentSummary

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ('product','user','rating','sentiment','fake_probability','is_approved','is_flagged','created_at')
    list_filter   = ('sentiment','is_approved','is_flagged','is_fake_flag','rating')
    search_fields = ('product__name','user__email','comment')
    list_editable = ('is_approved','is_flagged')
    readonly_fields = ('sentiment','sentiment_score','is_fake_flag','fake_probability','created_at')
    actions       = ['approve_reviews','run_ai_analysis']

    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True, is_flagged=False)
    approve_reviews.short_description = 'Approve selected reviews'

    def run_ai_analysis(self, request, queryset):
        from reviews.sentiment_engine import analyze_review
        for review in queryset:
            analyze_review(review)
        self.message_user(request, f'AI analysis complete for {queryset.count()} reviews.')
    run_ai_analysis.short_description = 'Run AI sentiment + fake detection'

@admin.register(ProductSentimentSummary)
class SentimentSummaryAdmin(admin.ModelAdmin):
    list_display = ('product','positive_count','neutral_count','negative_count','avg_sentiment_score','updated_at')
    readonly_fields = ('updated_at',)

admin.site.register(ReviewVote)
