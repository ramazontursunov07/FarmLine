from django.urls import path

from .views import ActionCancelView, ActionConfirmView, ChatView

urlpatterns = [
    path('assistant/chat/', ChatView.as_view(), name='assistant-chat'),
    path('assistant/actions/<int:pk>/confirm/', ActionConfirmView.as_view(), name='assistant-action-confirm'),
    path('assistant/actions/<int:pk>/cancel/', ActionCancelView.as_view(), name='assistant-action-cancel'),
]
