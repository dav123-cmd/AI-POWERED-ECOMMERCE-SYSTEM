from django.apps import AppConfig

class AiChatbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_chatbot'
    verbose_name = 'AI Chatbot (ARIA)'

    def ready(self):
        # Auto-train classifier on startup if model doesn't exist
        from pathlib import Path
        from django.conf import settings
        model_path = Path(settings.AI_MODELS_DIR) / 'intent_classifier.pth'
        if not model_path.exists():
            try:
                from .intent_classifier import train_classifier
                train_classifier()
            except Exception:
                pass
