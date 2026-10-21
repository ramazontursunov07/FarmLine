from rest_framework.routers import DefaultRouter

from .views import DebtPaymentViewSet, DebtViewSet, PartyViewSet

router = DefaultRouter()
router.register('debt-party', PartyViewSet, basename='debt-party')
router.register('debt-payment', DebtPaymentViewSet, basename='debt-payment')
router.register('debt', DebtViewSet, basename='debt')

urlpatterns = router.urls
