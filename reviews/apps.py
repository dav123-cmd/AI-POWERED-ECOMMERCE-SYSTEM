from django.apps import AppConfig

class ReviewsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reviews'
    verbose_name = 'Reviews & Sentiment'

    def ready(self):
        from pathlib import Path
        from django.conf import settings
        model_path = Path(settings.AI_MODELS_DIR) / 'sentiment_model.pth'
        if not model_path.exists():
            try:
                from .sentiment_engine import train_sentiment_model, train_fake_detector
                train_sentiment_model()
                train_fake_detector()
            except Exception:
                pass
