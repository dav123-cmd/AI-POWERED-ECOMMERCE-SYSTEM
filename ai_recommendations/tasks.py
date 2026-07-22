"""
ShopAI — Celery Tasks for Recommendation Engine
"""
from celery import shared_task


@shared_task(name='ai_recommendations.train_model', bind=True, max_retries=2)
def train_recommendation_model(self):
    """
    Celery task: retrain the recommendation model.
    Scheduled to run every 24 hours via Celery Beat.
    Also triggered when interaction count hits a threshold.
    """
    try:
        from .recommender import train_recommender
        model = train_recommender()
        if model:
            return {'status': 'success', 'message': 'Model trained successfully'}
        return {'status': 'skipped', 'message': 'Insufficient interaction data'}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=300)


@shared_task(name='ai_recommendations.record_interaction')
def record_interaction_async(user_id, product_id, interaction_type):
    """
    Async interaction recording to avoid blocking request/response.
    """
    try:
        from django.contrib.auth import get_user_model
        from products.models import Product
        from .models import UserProductInteraction

        User    = get_user_model()
        user    = User.objects.get(id=user_id)
        product = Product.objects.get(id=product_id)

        UserProductInteraction.objects.get_or_create(
            user=user, product=product, interaction=interaction_type,
            defaults={'weight': UserProductInteraction.WEIGHTS.get(interaction_type, 1.0)}
        )
    except Exception:
        pass


@shared_task(name='ai_recommendations.rebuild_similar')
def rebuild_similar_products():
    """Rebuild SimilarProduct table from current model."""
    try:
        from .recommender import _load_model, _compute_similar_products
        import torch
        model, maps = _load_model()
        if model:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            _compute_similar_products(
                model, maps['product_map'], maps['product_ids'], device
            )
            return {'status': 'success'}
        return {'status': 'no_model'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}
