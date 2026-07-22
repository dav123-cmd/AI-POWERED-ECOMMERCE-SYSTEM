"""
URL configuration for ShopSmartAI project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('Users.urls', 'users'), namespace='users')),
    path('products/', include(('products.urls', 'products'), namespace='products')),
    path('orders/',include(('orders.urls','orders'),namespace='orders')),
    path('payments/',include(('payments.urls','payments'),namespace='payments')),
    path('ai_search/',include(('ai_search.urls','ai_search'),namespace='ai_search')),
    path('ai_recommendations/',include(('ai_recommendations.urls','ai_recommendations'),namespace='ai_recommendations')),
    path('reviews/',include(('reviews.urls','reviews'),namespace='reviews')),
    path('analytics/',include(('analytics.urls','analytics'),namespace='analytics')),
    path('notifications/',include(('notifications.urls','notifications'),namespace='notifications')),
    path('ai/chat/',include(('ai_chatbot.urls','ai_chatbot'),namespace='ai_chatbot')),
    path('wishlist/',include(('wishlist.urls','wishlist'),namespace='wishlist')),
    path('dashboard/',include(('dashboard.urls','dashboard'),namespace='dashboard')),
 path('accounts/', include('allauth.urls')),
  path('api/',include(('api.urls','api'),namespace='api')),
    
    
]

# Add this block at the very bottom of the file
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
