from rest_framework.routers import DefaultRouter
from .views import AttendanceViewSet, FarmViewSet, WorkerViewSet

router = DefaultRouter()
router.register('farms', FarmViewSet, basename='farm')
router.register('attendance', AttendanceViewSet, basename='attendance')
router.register('workers', WorkerViewSet, basename='worker')

urlpatterns = router.urls
