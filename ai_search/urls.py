from django.urls import path
from . import views

app_name = 'ai_search'

urlpatterns = [
    path('',           views.search_results,    name='results'),
    path('suggest/',   views.search_suggest,     name='suggest'),
    path('visual/',    views.visual_search_page, name='visual'),
    path('visual/api/',views.visual_search_api,  name='visual_api'),
    path('history/',   views.search_history,     name='history'),
]
