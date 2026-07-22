from django.urls import path
from . import views

app_name = 'ai_recommendations'

urlpatterns = [
    path('',                                      views.recommendations_page,   name='page'),
    path('api/',                                  views.recommendations_api,    name='api'),
    path('similar/<str:product_id>/',             views.similar_products_api,   name='similar'),
    path('bought-together/<str:product_id>/',     views.bought_together_api,    name='bought_together'),
    path('track/<str:product_id>/<str:interaction_type>/', views.track_interaction, name='track'),
]
