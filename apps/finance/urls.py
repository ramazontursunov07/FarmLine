from rest_framework.routers import DefaultRouter

from apps.finance.views import TransactionViewSet

router = DefaultRouter()

router.register('finance', TransactionViewSet, basename='finance')

urlpatterns = router.urls
