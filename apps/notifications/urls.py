from django.urls import path

from .views import NotificationClearView, NotificationCountView, NotificationListView, NotificationReadView

urlpatterns = [
    path('notifications/', NotificationListView.as_view(), name='notifications'),
    path('notifications/count/', NotificationCountView.as_view(), name='notifications_count'),
    path('notifications/read/', NotificationReadView.as_view(), name='notifications_read'),
    path('notifications/clear/', NotificationClearView.as_view(), name='notifications_clear'),
]
