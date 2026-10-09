from django.db import transaction
from django.db.models import F, Q
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.farms.models import Worker
from .models import InventoryItem, InventoryTransaction
from .serializers import InventoryItemSerializer, InventoryTransactionSerializer


def is_farm_member(user, farm):
    """Ferma egasi yoki shu fermaga biriktirilgan ishchimi?"""
    return farm.owner_id == user.id or Worker.objects.filter(farm=farm, user=user).exists()


def fmt(value):
    """Decimal ni chiroyli ko'rsatish: 50.00 -> 50"""
    return format(value.normalize(), 'f')


class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    Ombor mahsulotlari (ozuqa, dori...).
    Ko'rish: ferma egasi va ishchilar. Qo'shish/tahrirlash/o'chirish: faqat ferma egasi.
    Filtrlar: ?farm= ?item_type= ?low=1 (zaxirasi kam qolganlar)
    """
    queryset = InventoryItem.objects.all()
    serializer_class = InventoryItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = InventoryItem.objects.select_related('farm').filter(
            Q(farm__owner=user) | Q(farm__workers__user=user)
        ).distinct()
        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(farm_id=int(p['farm']))
        if p.get('item_type'):
            qs = qs.filter(item_type=p['item_type'])
        if p.get('low') in ('1', 'true'):
            qs = qs.filter(quantity__lte=F('low_stock_threshold'))
        return qs

    def _ensure_owner(self, farm):
        if farm.owner_id != self.request.user.id:
            raise PermissionDenied("Ombor mahsulotlarini faqat ferma egasi boshqara oladi.")

    def perform_create(self, serializer):
        self._ensure_owner(serializer.validated_data['farm'])
        serializer.save()

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance.farm)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance.farm)
        instance.delete()


class InventoryTransactionViewSet(viewsets.ModelViewSet):
    """
    Ombor harakatlari (kirim/sarf). Ferma egasi ham, ishchi ham yozadi; zaxira avtomatik yangilanadi.
    Yozuvni tahrirlab bo'lmaydi (xato bo'lsa, ferma egasi o'chirib, qaytadan kiritadi).
    Filtrlar: ?farm= ?inventory_item= ?transaction_type=
    """
    queryset = InventoryTransaction.objects.all()
    serializer_class = InventoryTransactionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = InventoryTransaction.objects.select_related('inventory_item__farm', 'recorded_by').filter(
            Q(inventory_item__farm__owner=user) | Q(inventory_item__farm__workers__user=user)
        ).distinct().order_by('-date', '-id')
        p = self.request.query_params
        if p.get('farm', '').isdigit():
            qs = qs.filter(inventory_item__farm_id=int(p['farm']))
        if p.get('inventory_item', '').isdigit():
            qs = qs.filter(inventory_item_id=int(p['inventory_item']))
        if p.get('transaction_type'):
            qs = qs.filter(transaction_type=p['transaction_type'])
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        item = serializer.validated_data['inventory_item']
        if not is_farm_member(user, item.farm):
            raise PermissionDenied("Siz bu fermaning omboriga yozuv qo'sha olmaysiz.")

        qty = serializer.validated_data['quantity']
        kind = serializer.validated_data['transaction_type']

        with transaction.atomic():
            locked = InventoryItem.objects.select_for_update().get(pk=item.pk)
            if kind == 'sarf':
                if qty > locked.quantity:
                    raise ValidationError({
                        'quantity': f"Omborda yetarli emas. Hozir: {fmt(locked.quantity)} {locked.unit}"
                    })
                locked.quantity -= qty
            else:
                locked.quantity += qty
            locked.save(update_fields=['quantity', 'updated_at'])
            serializer.save(recorded_by=user)

    def perform_destroy(self, instance):
        item = instance.inventory_item
        if item.farm.owner_id != self.request.user.id:
            raise PermissionDenied("Ombor yozuvini faqat ferma egasi o'chira oladi.")

        with transaction.atomic():
            locked = InventoryItem.objects.select_for_update().get(pk=item.pk)
            if instance.transaction_type == 'sarf':
                locked.quantity += instance.quantity
            else:
                if instance.quantity > locked.quantity:
                    raise ValidationError(
                        "Bu kirimni o'chirib bo'lmaydi: undan keyin mahsulot sarflangan, zaxira yetmay qoladi."
                    )
                locked.quantity -= instance.quantity
            locked.save(update_fields=['quantity', 'updated_at'])
            instance.delete()
