"""
ShopAI — Reviews Views
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.admin.views.decorators import staff_member_required
from .models import Review, ReviewVote, ProductSentimentSummary
from .sentiment_engine import analyze_review
from products.models import Product
from orders.models import Order


@login_required
@require_POST
def submit_review(request, product_id):
    """Submit a new review with AI sentiment analysis."""
    product = get_object_or_404(Product, id=product_id, is_active=True)

    # Check if user already reviewed
    if Review.objects.filter(product=product, user=request.user).exists():
        return JsonResponse({'success': False, 'error': 'You have already reviewed this product.'})

    # Check if user purchased (optional enforcement)
    has_purchased = Order.objects.filter(
        user=request.user, payment_status='paid',
        items__product=product
    ).exists()

    rating  = int(request.POST.get('rating', 0))
    comment = request.POST.get('comment', '').strip()
    title   = request.POST.get('title', '').strip()

    if not 1 <= rating <= 5:
        return JsonResponse({'success': False, 'error': 'Rating must be between 1 and 5.'})
    if len(comment) < 10:
        return JsonResponse({'success': False, 'error': 'Review must be at least 10 characters.'})

    # Get associated order
    order = Order.objects.filter(
        user=request.user, payment_status='paid', items__product=product
    ).order_by('-created_at').first()

    review = Review.objects.create(
        product  = product,
        user     = request.user,
        order    = order,
        rating   = rating,
        title    = title,
        comment  = comment,
    )

    # Run AI analysis async (or sync for simplicity)
    try:
        sentiment, score, is_fake = analyze_review(review)
        msg = 'Review submitted! It will appear after AI moderation.'
        if not is_fake:
            msg = 'Review published! Thanks for your feedback.'
    except Exception:
        msg = 'Review submitted and pending moderation.'

    return JsonResponse({
        'success':   True,
        'message':   msg,
        'approved':  review.is_approved,
        'sentiment': review.sentiment,
    })


@require_GET
def product_reviews(request, product_id):
    """AJAX: get paginated reviews for a product."""
    product  = get_object_or_404(Product, id=product_id)
    sort     = request.GET.get('sort', '-helpful_count')
    filter_s = request.GET.get('sentiment', '')
    filter_r = request.GET.get('rating', '')

    reviews  = Review.objects.filter(product=product, is_approved=True)\
                             .select_related('user')

    if filter_s in ('positive', 'neutral', 'negative'):
        reviews = reviews.filter(sentiment=filter_s)
    if filter_r.isdigit():
        reviews = reviews.filter(rating=int(filter_r))

    VALID_SORTS = ['-created_at', 'created_at', '-helpful_count', '-rating', 'rating']
    reviews = reviews.order_by(sort if sort in VALID_SORTS else '-created_at')

    data = [{
        'id':           str(r.id),
        'user':         r.user.get_full_name(),
        'avatar':       r.user.avatar_url,
        'rating':       r.rating,
        'title':        r.title,
        'comment':      r.comment,
        'sentiment':    r.sentiment,
        'sentiment_score': r.sentiment_score,
        'helpful_count':r.helpful_count,
        'has_purchased':bool(r.order),
        'created_at':   r.created_at.strftime('%d %b %Y'),
    } for r in reviews[:20]]

    return JsonResponse({'success': True, 'reviews': data, 'count': reviews.count()})


@require_GET
def sentiment_summary(request, product_id):
    """AJAX: get sentiment summary for product."""
    product = get_object_or_404(Product, id=product_id)
    try:
        summary = product.sentiment_summary
        return JsonResponse({
            'success':           True,
            'positive_count':    summary.positive_count,
            'neutral_count':     summary.neutral_count,
            'negative_count':    summary.negative_count,
            'positive_pct':      summary.positive_pct,
            'avg_score':         summary.avg_sentiment_score,
            'positive_phrases':  summary.top_positive_phrases,
            'negative_phrases':  summary.top_negative_phrases,
            'total':             summary.positive_count + summary.neutral_count + summary.negative_count,
        })
    except ProductSentimentSummary.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No reviews yet'})


@login_required
@require_POST
def vote_review(request, review_id):
    """Mark a review as helpful or not."""
    review     = get_object_or_404(Review, id=review_id, is_approved=True)
    is_helpful = request.POST.get('helpful') == '1'

    vote, created = ReviewVote.objects.get_or_create(
        review=review, user=request.user,
        defaults={'is_helpful': is_helpful}
    )
    if not created:
        vote.is_helpful = is_helpful
        vote.save()

    # Recount
    helpful     = review.votes.filter(is_helpful=True).count()
    not_helpful = review.votes.filter(is_helpful=False).count()
    Review.objects.filter(pk=review.pk).update(
        helpful_count=helpful, not_helpful_count=not_helpful
    )
    return JsonResponse({'success': True, 'helpful_count': helpful})


# ── Admin / Moderation ────────────────────────────────────

@staff_member_required
def moderation_dashboard(request):
    """Review moderation dashboard for staff."""
    pending  = Review.objects.filter(is_approved=False, is_flagged=False).select_related('user','product')
    flagged  = Review.objects.filter(is_flagged=True).select_related('user','product')
    recent   = Review.objects.filter(is_approved=True).select_related('user','product').order_by('-created_at')[:20]

    stats = {
        'total':    Review.objects.count(),
        'approved': Review.objects.filter(is_approved=True).count(),
        'pending':  pending.count(),
        'flagged':  flagged.count(),
        'fake':     Review.objects.filter(is_fake_flag=True).count(),
        'positive': Review.objects.filter(sentiment='positive').count(),
        'negative': Review.objects.filter(sentiment='negative').count(),
    }
    return render(request, 'reviews/moderation_dashboard.html', {
        'pending': pending, 'flagged': flagged,
        'recent': recent, 'stats': stats,
    })


@staff_member_required
@require_POST
def moderate_review(request, review_id):
    """Approve or reject a review."""
    review = get_object_or_404(Review, id=review_id)
    action = request.POST.get('action')

    if action == 'approve':
        review.is_approved = True
        review.is_flagged  = False
        review.save()
        from .sentiment_engine import update_product_sentiment
        update_product_sentiment(review.product)
        return JsonResponse({'success': True, 'message': 'Review approved.'})
    elif action == 'reject':
        review.delete()
        return JsonResponse({'success': True, 'message': 'Review deleted.'})
    elif action == 'flag':
        review.is_flagged  = True
        review.is_approved = False
        review.flag_reason = request.POST.get('reason', 'Manually flagged')
        review.save()
        return JsonResponse({'success': True, 'message': 'Review flagged.'})

    return JsonResponse({'success': False, 'error': 'Invalid action.'}, status=400)
