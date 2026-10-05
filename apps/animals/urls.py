from rest_framework.routers import DefaultRouter
from .views import AnimalTypeViewSet, AnimalEventViewSet, AnimalGroupViewSet

router = DefaultRouter()

router.register('animals-group', AnimalGroupViewSet, basename='animal-group'),
router.register('animals-type', AnimalTypeViewSet, basename='animal-type'),
router.register('animals-event', AnimalEventViewSet, basename='animal-event')

urlpatterns = router.urls
