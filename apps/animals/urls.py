from rest_framework.routers import DefaultRouter
from .views import AnimalTypeViewSet, AnimalEventViewSet, AnimalGroupViewSet

router = DefaultRouter()

router.register('animals_group', AnimalGroupViewSet, basename='animal_group'),
router.register('animals_type', AnimalTypeViewSet, basename='animal_type'),
router.register('animals_event', AnimalEventViewSet, basename='animal_event')

urlpatterns = router.urls
