from .views import InventoryItemViewSet, InventoryTransactionViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('inventory_item', InventoryItemViewSet, basename='inventory_item'),
router.register('inventory_transaction', InventoryTransactionViewSet, basename='inventory_transaction')

urlpatterns = router.urls
