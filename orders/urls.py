from django.urls import path
from . import views

app_name = 'orders'

urlpatterns = [
    # Cart
    path('cart/',                           views.cart_view,        name='cart'),
    path('cart/add/',                       views.cart_add,         name='cart_add'),
    path('cart/update/',                    views.cart_update,      name='cart_update'),
    path('cart/remove/<int:item_id>/',      views.cart_remove,      name='cart_remove'),
    path('cart/coupon/apply/',              views.apply_coupon,     name='apply_coupon'),
    path('cart/coupon/remove/',             views.remove_coupon,    name='remove_coupon'),
    # Checkout
    path('checkout/',                       views.checkout,         name='checkout'),
    path('order/<str:order_number>/',       views.order_summary,    name='order_summary'),
    # Orders
    path('history/',                        views.order_history,    name='history'),
    path('detail/<str:order_number>/',      views.order_detail,     name='order_detail'),
    path('cancel/<str:order_number>/',      views.cancel_order,     name='cancel_order'),
    path('track/',                          views.track_order,      name='track'),
]
