from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('submit/<str:product_id>/',         views.submit_review,        name='submit'),
    path('product/<str:product_id>/',        views.product_reviews,      name='product_reviews'),
    path('sentiment/<str:product_id>/',      views.sentiment_summary,    name='sentiment_summary'),
    path('vote/<uuid:review_id>/',           views.vote_review,          name='vote'),
    path('moderation/',                      views.moderation_dashboard, name='moderation'),
    path('moderation/<uuid:review_id>/',     views.moderate_review,      name='moderate'),
]
