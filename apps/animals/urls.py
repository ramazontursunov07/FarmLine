from rest_framework.routers import DefaultRouter
from .views import (AnimalTypeViewSet, AnimalEventViewSet, AnimalGroupViewSet,
                    AnimalViewSet, WeightRecordViewSet, MilkRecordViewSet, MilkSaleViewSet)

router = DefaultRouter()

router.register('animals-group', AnimalGroupViewSet, basename='animal-group'),
router.register('animals-type', AnimalTypeViewSet, basename='animal-type'),
router.register('animals-event', AnimalEventViewSet, basename='animal-event')
router.register('animals-card', AnimalViewSet, basename='animal-card')
router.register('animals-weight', WeightRecordViewSet, basename='animal-weight')
router.register('animals-milk', MilkRecordViewSet, basename='animal-milk')
router.register('animals-milk-sale', MilkSaleViewSet, basename='animal-milk-sale')

urlpatterns = router.urls
