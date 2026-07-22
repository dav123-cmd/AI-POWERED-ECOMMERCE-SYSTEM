"""
ShopAI API v1 — URL Configuration
Mounted at /api/v1/ from core/urls.py.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from . import views

app_name = 'api'

router = DefaultRouter()
router.register(r'categories',     views.CategoryViewSet,     basename='category')
router.register(r'products',       views.ProductViewSet,      basename='product')
router.register(r'orders',         views.OrderViewSet,        basename='order')
router.register(r'reviews',        views.ReviewViewSet,       basename='review')
router.register(r'wishlist',       views.WishlistViewSet,     basename='wishlist')
router.register(r'notifications',  views.NotificationViewSet, basename='notification')
router.register(r'addresses',      views.AddressViewSet,      basename='address')

urlpatterns = [
    path('', include(router.urls)),

    # Health
    path('health/', views.HealthCheckView.as_view(), name='health'),

    # Auth (JWT)
    path('auth/register/',     views.RegisterView.as_view(),       name='register'),
    path('auth/login/',        TokenObtainPairView.as_view(),      name='login'),
    path('auth/refresh/',      TokenRefreshView.as_view(),         name='token_refresh'),
    path('auth/verify/',       TokenVerifyView.as_view(),          name='token_verify'),
    path('profile/',           views.ProfileView.as_view(),        name='profile'),

    # Cart
    path('cart/',                       views.CartView.as_view(),       name='cart'),
    path('cart/add/',                   views.CartAddView.as_view(),    name='cart_add'),
    path('cart/update/',                views.CartUpdateView.as_view(), name='cart_update'),
    path('cart/remove/<int:item_id>/',  views.CartRemoveView.as_view(), name='cart_remove'),

    # AI
    path('search/',            views.SemanticSearchView.as_view(),   name='search'),
    path('search/visual/',     views.VisualSearchView.as_view(),     name='visual_search'),
    path('recommendations/',   views.RecommendationsView.as_view(),  name='recommendations'),
    path('chat/message/',      views.ChatMessageView.as_view(),      name='chat_message'),

    # API Docs (OpenAPI 3 schema + interactive UIs)
    path('schema/',  SpectacularAPIView.as_view(),                          name='schema'),
    path('docs/',    SpectacularSwaggerView.as_view(url_name='api:schema'), name='docs'),
    path('redoc/',   SpectacularRedocView.as_view(url_name='api:schema'),   name='redoc'),
]
