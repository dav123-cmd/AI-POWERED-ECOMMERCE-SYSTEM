"""
ShopAI API — Custom throttles.
AI endpoints (semantic/visual search, recommendations, chat) run real
model inference per request, so they get a tighter, separately-scoped
rate limit than ordinary CRUD endpoints.
"""
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle


class AIUserThrottle(UserRateThrottle):
    scope = 'ai_user'


class AIAnonThrottle(AnonRateThrottle):
    scope = 'ai_anon'
