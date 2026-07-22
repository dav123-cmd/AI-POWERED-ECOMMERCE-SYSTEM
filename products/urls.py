from django.urls import path
from . import views
from . import pricing_views
app_name = 'products'

urlpatterns = [
    path('',                            views.home,             name='home'),
    path('shop/',                       views.product_list,     name='list'),
    path('shop/categories/',            views.categories_page,  name='categories'),
    path('shop/category/<slug:slug>/',  views.category_detail,  name='category'),
    path('shop/deals/',                 views.deals,            name='deals'),
    path('shop/new/',                   views.new_arrivals,     name='new_arrivals'),
    path('shop/bestsellers/',           views.bestsellers,      name='bestsellers'),
    path('shop/<slug:slug>/',           views.product_detail,   name='detail'),
    path('shop/<slug:slug>/quick/',     views.quick_view,       name='quick_view'),
    path('about/', views.about_page, name='about'),
]

urlpatterns += [
    path('api/price/<str:product_id>/',  pricing_views.get_price_api,    name='ai_price'),
    path('api/prices/update/',           pricing_views.update_all_prices, name='update_prices'),
]
