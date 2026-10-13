from django.urls import path

from .views import ChatView

urlpatterns = [
    path('assistant/chat/', ChatView.as_view(), name='assistant-chat'),
]
