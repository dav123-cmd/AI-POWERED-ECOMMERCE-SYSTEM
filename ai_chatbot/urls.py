from django.urls import path
from . import views

app_name = 'ai_chatbot'

urlpatterns = [
    path('message/',  views.send_message,    name='message'),
    path('history/',  views.get_history,     name='history'),
    path('clear/',    views.clear_history,   name='clear'),
    path('handoff/',  views.request_handoff, name='handoff'),
    path('',          views.chat_page,       name='page'),
]
