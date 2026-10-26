from rest_framework.routers import DefaultRouter

from .views import RecurringTaskViewSet, TaskViewSet

router = DefaultRouter()
router.register('tasks-recurring', RecurringTaskViewSet, basename='task-recurring')
router.register('tasks', TaskViewSet, basename='task')

urlpatterns = router.urls
