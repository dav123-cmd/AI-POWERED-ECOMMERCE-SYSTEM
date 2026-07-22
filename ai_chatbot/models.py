"""
ShopAI — ARIA Chatbot Models
"""
from django.db import models
from django.conf import settings
import uuid


class ChatSession(models.Model):
    """One chat session per user/visitor."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name='chat_sessions')
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    is_active   = models.BooleanField(default=True)
    # Handoff to human support
    handed_off  = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'Chat({self.user or self.session_key[:8]})'

    @property
    def message_count(self):
        return self.messages.count()


class ChatMessage(models.Model):
    ROLES = [('user','User'), ('assistant','Assistant'), ('system','System')]

    session    = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role       = models.CharField(max_length=10, choices=ROLES)
    content    = models.TextField()
    intent     = models.CharField(max_length=50, blank=True)   # classified intent
    confidence = models.FloatField(default=0.0)                 # intent confidence
    metadata   = models.JSONField(default=dict, blank=True)    # product refs, order refs, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'[{self.role}] {self.content[:60]}'


class IntentLabel(models.Model):
    """Training data for intent classifier."""
    text   = models.TextField()
    intent = models.CharField(max_length=50, db_index=True)
    source = models.CharField(max_length=20, default='manual')  # manual, inferred

    class Meta:
        ordering = ['intent']

    def __str__(self):
        return f'{self.intent}: {self.text[:50]}'
