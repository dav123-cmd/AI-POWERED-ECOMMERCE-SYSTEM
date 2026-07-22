from django.urls import path
from . import views

app_name = 'wishlist'

urlpatterns = [
    path('',                            views.index,          name='index'),
    path('toggle/',                     views.toggle,          name='toggle'),
    path('remove/<uuid:item_id>/',      views.remove_item,     name='remove'),
    path('move-to-cart/<str:product_id>/', views.move_to_cart, name='move_to_cart'),
    path('move-all-to-cart/',           views.move_all_to_cart, name='move_all_to_cart'),
    path('clear/',                      views.clear_all,       name='clear'),
    path('prefs/<uuid:item_id>/',       views.update_item_prefs, name='prefs'),
]
