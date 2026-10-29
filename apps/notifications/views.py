import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import Notification
from .serializers import NotificationSerializer

logger = logging.getLogger(__name__)

LIST_LIMIT = 50


def _sync(user):
    # Eslatmalarni hisoblashda xato bo'lsa ham, bildirishnomalar ro'yxati ochilaveradi
    try:
        services.sync_alerts(user)
    except Exception:
        logger.exception("Bildirishnomalarni yangilashda xato (user=%s)", user.pk)


def _unread(user):
    return Notification.objects.filter(user=user, is_read=False).count()


class NotificationListView(APIView):
    """GET /api/notifications/ -- so'nggi 50 ta bildirishnoma va o'qilmaganlar soni."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _sync(request.user)
        qs = Notification.objects.filter(user=request.user)
        if request.query_params.get('unread') == '1':
            qs = qs.filter(is_read=False)
        return Response({
            'unread_count': _unread(request.user),
            'results': NotificationSerializer(qs[:LIST_LIMIT], many=True).data,
        })


class NotificationCountView(APIView):
    """GET /api/notifications/count/ -- qo'ng'iroqcha uchun yengil so'rov."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _sync(request.user)
        return Response({'unread_count': _unread(request.user)})


class NotificationReadView(APIView):
    """POST /api/notifications/read/ -- {"ids": [1, 2]} yoki {"all": true}: o'qilgan deb belgilaydi."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        qs = Notification.objects.filter(user=request.user, is_read=False)
        if request.data.get('all') is True:
            pass
        else:
            ids = request.data.get('ids')
            if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
                return Response({'detail': "ids butun sonlar ro'yxati bo'lishi kerak yoki all=true yuboring"},
                                status=400)
            qs = qs.filter(pk__in=ids)
        qs.update(is_read=True)
        return Response({'unread_count': _unread(request.user)})


class NotificationClearView(APIView):
    """POST /api/notifications/clear/ -- o'qilgan bildirishnomalarni o'chiradi."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=True).delete()
        return Response({'unread_count': _unread(request.user)})
    