from rest_framework.routers import DefaultRouter
from .views import FarmViewSet, WorkerViewSet

router = DefaultRouter()
router.register('farms', FarmViewSet, basename='farm')
router.register('workers', WorkerViewSet, basename='worker')

urlpatterns = router.urls
