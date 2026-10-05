from .views import InventoryItemViewSet, InventoryTransactionViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('inventory-item', InventoryItemViewSet, basename='inventory-item'),
router.register('inventory-transaction', InventoryTransactionViewSet, basename='inventory-transaction')

urlpatterns = router.urls
