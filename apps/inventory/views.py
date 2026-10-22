from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.core.mixins import IdempotentCreateMixin
from apps.debts import credit
from apps.farms.models import Worker
from apps.finance.models import Transaction as FinanceTransaction
from apps.finance.views import finance_farms
from apps.users.notify import display_name, notify_users
from .models import InventoryItem, InventoryTransaction
from .serializers import InventoryItemSerializer, InventoryTransactionSerializer


def is_farm_member(user, farm):
    """Ferma egasi yoki shu fermaga biriktirilgan ishchimi?"""
    return farm.owner_id == user.id or Worker.objects.filter(farm=farm, user=user).exists()


def fmt(value):
    """Decimal ni chiroyli ko'rsatish: 50.00 -> 50"""
    return format(value.normalize(), 'f')


def create_purchase_expense(inv_tx, item, user, amount):
    """Ombor kirimining narxini moliyada "Chiqim" qilib yozadi (balansdan ayriladi) va kirimga bog'laydi."""
    description = f"Ombor kirimi: {item.item_name}, {fmt(inv_tx.quantity)} {item.unit}"
    if inv_tx.note:
        description += f" ({inv_tx.note})"
    inv_tx.finance_transaction = FinanceTransaction.objects.create(
        farm=item.farm,
        transaction_type='chiqim',
        category=item.item_type,  # ozuqa / dori / boshqa: moliya kategoriyalari bilan bir xil
        amount=amount,
        description=description,
        date=inv_tx.date,
        recorded_by=user,
    )
    inv_tx.save(update_fields=['finance_transaction'])


class InventoryItemViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
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
        amount = serializer.validated_data.pop('initial_amount', None)
        user = self.request.user
        with transaction.atomic():
            item = serializer.save()
            # Boshlang'ich zaxira ham oddiy kirim sifatida yoziladi: tarixda ko'rinadi, narxi bo'lsa balansdan ayriladi
            if item.quantity > 0:
                inv_tx = InventoryTransaction.objects.create(
                    inventory_item=item,
                    transaction_type='kirim',
                    quantity=item.quantity,
                    date=timezone.localdate(),
                    note="Boshlang'ich zaxira",
                    amount=amount,
                    recorded_by=user,
                )
                if amount:
                    create_purchase_expense(inv_tx, item, user, amount)

    def perform_update(self, serializer):
        self._ensure_owner(serializer.instance.farm)
        serializer.save()

    def perform_destroy(self, instance):
        self._ensure_owner(instance.farm)
        instance.delete()


class InventoryTransactionViewSet(IdempotentCreateMixin, viewsets.ModelViewSet):
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        # Narx faqat moliyani ko'rish huquqi bor fermalar uchun ko'rsatiladi (bir marta hisoblanadi)
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False) or not user.is_authenticated:
            context['finance_farm_ids'] = set()
        else:
            context['finance_farm_ids'] = set(finance_farms(user).values_list('pk', flat=True))
        return context

    def perform_create(self, serializer):
        user = self.request.user
        item = serializer.validated_data['inventory_item']
        if not is_farm_member(user, item.farm):
            raise PermissionDenied("Siz bu fermaning omboriga yozuv qo'sha olmaysiz.")

        qty = serializer.validated_data['quantity']
        kind = serializer.validated_data['transaction_type']
        amount = serializer.validated_data.get('amount')
        credit_info = None
        if credit.parse_credit_flag(self.request.data):
            if kind != 'kirim' or not amount:
                raise ValidationError({'amount': "Nasiyaga olish uchun kirim va jami narxni kiriting"})
            credit_info = credit.parse_credit(self.request.data, item.farm, amount, serializer.validated_data['date'])

        # Narx moliyada chiqim bo'lib yoziladi, shuning uchun moliyani o'zgartirish huquqi kerak
        if amount and not finance_farms(user).filter(pk=item.farm_id).exists():
            raise ValidationError({
                'amount': "Narxni kiritish uchun moliya huquqi kerak. "
                          "Narxsiz yozing, ferma egasi keyin moliyaga qo'shadi."
            })

        with transaction.atomic():
            locked = InventoryItem.objects.select_for_update().get(pk=item.pk)
            before = locked.quantity
            if kind == 'sarf':
                if qty > locked.quantity:
                    raise ValidationError({
                        'quantity': f"Omborda yetarli emas. Hozir: {fmt(locked.quantity)} {locked.unit}"
                    })
                locked.quantity -= qty
            else:
                locked.quantity += qty
            locked.save(update_fields=['quantity', 'updated_at'])
            inv_tx = serializer.save(recorded_by=user)

            # Kirim narx bilan yozilsa, shu summa moliyada avtomatik "Chiqim" bo'ladi (balansdan ayriladi)
            if kind == 'kirim' and amount and credit_info:
                # Nasiyaga olindi: pul hozir balansdan ayrilmaydi, qarz ochiladi (to'langan sari chiqim bo'ladi)
                inv_tx.debt = credit.open_credit(
                    farm=item.farm, kind='taminotchi', credit=credit_info, total=amount, date=inv_tx.date,
                    description=f"{item.item_name}, {fmt(qty)} {item.unit}", user=user, category=item.item_type)
                inv_tx.save(update_fields=['debt'])
            elif kind == 'kirim' and amount:
                create_purchase_expense(inv_tx, locked, user, amount)

            # Faqat zaxira chegaradan YUQORIDAN pastga o'tgan paytda ogohlantiramiz (har sarfda emas)
            if kind == 'sarf' and before > locked.low_stock_threshold and locked.is_low_stock:
                notify_users([item.farm.owner], (
                    f"⚠️ Ombor: «{locked.item_name}» kam qoldi!\n"
                    f"Qoldi: {fmt(locked.quantity)} {locked.unit} (chegara: {fmt(locked.low_stock_threshold)} {locked.unit})\n"
                    f"Ferma: {item.farm.name}\n"
                    f"Oxirgi sarfni kiritdi: {display_name(user)}"
                ))

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
            finance_tx = instance.finance_transaction
            debt = instance.debt
            instance.delete()
            if debt is not None:
                credit.delete_debt(debt)  # nasiya qarzi va u bo'yicha to'langan pullar ham qaytariladi
            # Kirim bilan birga yozilgan moliyaviy chiqim ham o'chadi (balans qaytadi)
            if finance_tx is not None:
                finance_tx.delete()
