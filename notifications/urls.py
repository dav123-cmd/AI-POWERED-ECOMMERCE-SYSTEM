from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('',                          views.index,             name='index'),
    path('feed/',                     views.dropdown_feed,      name='feed'),
    path('read/<uuid:notification_id>/',   views.mark_read,     name='mark_read'),
    path('read-all/',                 views.mark_all_read,      name='mark_all_read'),
    path('delete/<uuid:notification_id>/', views.delete_notification, name='delete'),
    path('clear-all/',                views.clear_all,          name='clear_all'),
    path('preferences/',              views.update_preferences, name='preferences'),
    path('go/<uuid:notification_id>/',views.go_to_notification, name='go'),
]
