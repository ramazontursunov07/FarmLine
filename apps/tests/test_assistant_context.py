"""AI yordamchi konteksti: sut ombori, kirim-chiqim davrlari, oylar/kunlar kesimi va qarzlar.

Telegram ham, sayt ham bir xil build_context() dan foydalanadi, shuning uchun "omborda qancha sut bor?",
"kecha qancha kirim-chiqim bo'ldi?" kabi savollarga javob berish uchun kerakli raqamlar shu yerda tekshiriladi.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.animals.models import Animal, AnimalGroup, AnimalType, MilkRecord, MilkSale
from apps.assistant import bot_service
from apps.assistant.context import build_context
from apps.assistant.services import build_system
from apps.debts.models import Debt, DebtPayment, Party
from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.users.models import User

TODAY = date(2026, 10, 13)  # seshanba


def make_user(username, role='fermer', **extra):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role, **extra)


# Haqiqiy internetga chiqmaslik uchun ob-havo so'rovlari soxta javob bilan almashtiriladi
_weather_patch = None


def setUpModule():
    global _weather_patch
    from apps.tests.test_weather import fake_get
    _weather_patch = patch('apps.weather.services.requests.get', side_effect=fake_get)
    _weather_patch.start()


def tearDownModule():
    _weather_patch.stop()


class ContextBase(TestCase):
    def setUp(self):
        self.owner = make_user('egasi')
        self.farm = Farm.objects.create(owner=self.owner, name='Ozoda', location='Toshkent', farm_type='chorvachilik')
        self.group = AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Sigir'), count=3)
        self.cow = Animal.objects.create(farm=self.farm, group=self.group, tag_number='1', name='Oqquloq')

    def milk(self, day, liters):
        return MilkRecord.objects.create(animal=self.cow, date=day, liters=Decimal(str(liters)))

    def tx(self, kind, amount, day, category='sotuv'):
        return Transaction.objects.create(
            farm=self.farm, transaction_type=kind, category=category, amount=amount, date=day,
            recorded_by=self.owner)


class MilkContextTests(ContextBase):
    def test_stock_and_periods(self):
        self.milk(TODAY, '12.5')                      # bugun
        self.milk(TODAY - timedelta(days=1), 20)      # kecha
        self.milk(TODAY - timedelta(days=4), 8)       # 9-oktabr: oxirgi 7 kun ichida
        self.milk(date(2026, 10, 1), 30)              # shu oy, lekin 7 kundan oldin
        MilkSale.objects.create(farm=self.farm, date=date(2026, 10, 10), liters=Decimal('10'),
                                price_per_liter=Decimal('4000'), amount=Decimal('40000'))
        ctx = build_context(self.owner, TODAY)
        self.assertIn('omborda 60.5 l sut qolgan', ctx)
        self.assertIn("jami sog'ilgan 70.5 l, sotilgan 10 l", ctx)
        self.assertIn('bugun 12.5 l, kecha 20 l, oxirgi 7 kun 40.5 l, shu oy 70.5 l', ctx)
        self.assertIn("Sotilgan sut shu oy: 10 l, sotuv summasi 40 000 so'm", ctx)

    def test_no_milk_says_so(self):
        self.assertIn("Sut ombori: hali sog'ilgan sut kiritilmagan", build_context(self.owner, TODAY))

    def test_other_owner_milk_not_visible(self):
        other = make_user('boshqa')
        farm2 = Farm.objects.create(owner=other, name='Yashirin', location='Buxoro', farm_type='aralash')
        group2 = AnimalGroup.objects.create(farm=farm2, animal_type=self.group.animal_type, count=1)
        cow2 = Animal.objects.create(farm=farm2, group=group2, tag_number='9')
        MilkRecord.objects.create(animal=cow2, date=TODAY, liters=Decimal('777.7'))
        ctx = build_context(self.owner, TODAY)
        self.assertNotIn('777.7', ctx)
        self.assertNotIn('Yashirin', ctx)

    def test_worker_sees_milk_but_no_money(self):
        worker = make_user('ishchi1', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        self.milk(TODAY, 15)
        MilkSale.objects.create(farm=self.farm, date=TODAY, liters=Decimal('5'),
                                price_per_liter=Decimal('4000'), amount=Decimal('20000'))
        self.tx('kirim', 123456, TODAY)
        ctx = build_context(worker, TODAY)
        self.assertIn('Sut ombori (Ozoda): omborda 10 l sut qolgan', ctx)
        self.assertNotIn('=== Ferma', ctx)
        self.assertNotIn('123 456', ctx)
        self.assertNotIn('20 000', ctx)
        self.assertNotIn('sotuv summasi', ctx)


class FinanceContextTests(ContextBase):
    def setUp(self):
        super().setUp()
        self.tx('kirim', 400000, date(2026, 10, 12))              # kecha
        self.tx('chiqim', 100000, TODAY, category='ozuqa')        # bugun
        self.tx('kirim', 1000000, date(2026, 10, 5))              # shu oy, 7 kundan oldin
        self.tx('kirim', 500000, date(2026, 9, 20))               # o'tgan oy
        self.tx('chiqim', 250000, date(2026, 3, 10), category='ozuqa')  # shu yil, lekin 6 oydan oldin
        self.ctx = build_context(self.owner, TODAY)

    def test_periods(self):
        self.assertIn("Bugun: kirim 0, chiqim 100 000, zarar 100 000 so'm", self.ctx)
        self.assertIn("Kecha: kirim 400 000, chiqim 0, foyda 400 000 so'm", self.ctx)
        self.assertIn("Oxirgi 7 kun (07.10–13.10): kirim 400 000, chiqim 100 000, foyda 300 000 so'm", self.ctx)
        self.assertIn("Shu oy (01.10–13.10): kirim 1 400 000, chiqim 100 000, foyda 1 300 000 so'm", self.ctx)
        self.assertIn("O'tgan oy: kirim 500 000, chiqim 0, foyda 500 000 so'm", self.ctx)
        self.assertIn("Shu yil (2026): kirim 1 900 000, chiqim 350 000, foyda 1 550 000 so'm", self.ctx)

    def test_months_breakdown_covers_six_months_only(self):
        self.assertIn('2026-10: kirim 1 400 000, chiqim 100 000', self.ctx)
        self.assertIn('2026-09: kirim 500 000, chiqim 0', self.ctx)
        self.assertNotIn('2026-03', self.ctx)

    def test_daily_breakdown_has_weekday(self):
        self.assertIn('12.10 (dushanba): kirim 400 000, chiqim 0', self.ctx)
        self.assertIn('13.10 (seshanba): kirim 0, chiqim 100 000', self.ctx)
        self.assertNotIn('05.10 (', self.ctx)  # 7 kundan oldingi kun kunlar ro'yxatida yo'q

    def test_income_sources_listed(self):
        self.assertIn('Shu oy kirim manbalari:', self.ctx)

    def test_explains_cash_basis(self):
        self.assertIn('haqiqiy olingan/to', self.ctx)


class DebtContextTests(ContextBase):
    def test_no_debts(self):
        self.assertIn('Qarzlar: kiritilmagan', build_context(self.owner, TODAY))

    def test_receivable_and_payable(self):
        client = Party.objects.create(farm=self.farm, kind='mijoz', name='Aziz')
        supplier = Party.objects.create(farm=self.farm, kind='taminotchi', name='Yem-Savdo')
        debt = Debt.objects.create(farm=self.farm, party=client, amount=Decimal('500000'),
                                   date=date(2026, 10, 1), due_date=date(2026, 10, 10))
        DebtPayment.objects.create(debt=debt, amount=Decimal('100000'), date=date(2026, 10, 5))
        Debt.objects.create(farm=self.farm, party=supplier, amount=Decimal('300000'),
                            date=date(2026, 10, 8), due_date=date(2026, 10, 20))
        ctx = build_context(self.owner, TODAY)
        self.assertIn("Sizga qarzdorlar (mijozlar): jami qoldiq 400 000 so'm (1 ta qarz), "
                      "shundan muddati o'tgan 400 000 so'm (1 ta)", ctx)
        self.assertIn("Aziz: 400 000 so'm, MUDDATI O'TGAN", ctx)
        self.assertIn("Siz qarzdorsiz (yetkazib beruvchilarga): jami qoldiq 300 000 so'm (1 ta qarz)", ctx)
        self.assertIn("Yem-Savdo: 300 000 so'm, muddat 20.10.2026", ctx)

    def test_fully_paid_debt_is_not_listed(self):
        client = Party.objects.create(farm=self.farm, kind='mijoz', name='Vali')
        debt = Debt.objects.create(farm=self.farm, party=client, amount=Decimal('100000'), date=date(2026, 10, 1))
        DebtPayment.objects.create(debt=debt, amount=Decimal('100000'), date=date(2026, 10, 2))
        ctx = build_context(self.owner, TODAY)
        self.assertIn("Sizga qarzdorlar (mijozlar): ochiq qarz yo'q", ctx)
        self.assertNotIn('Vali', ctx)

    def test_worker_never_sees_debts(self):
        worker = make_user('ishchi2', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        client = Party.objects.create(farm=self.farm, kind='mijoz', name='Aziz')
        Debt.objects.create(farm=self.farm, party=client, amount=Decimal('500000'), date=date(2026, 10, 1))
        ctx = build_context(worker, TODAY)
        self.assertNotIn('Aziz', ctx)
        self.assertNotIn('Qarzlar', ctx)


class TelegramPathTests(ContextBase):
    """Telegram boti ham xuddi shu kontekstni AI ga beradi."""

    def setUp(self):
        super().setUp()
        bot_service._history.clear()
        bot_service._calls.clear()
        self.owner.telegram_chat_id = '2002'
        self.owner.save(update_fields=['telegram_chat_id'])

    def test_bot_passes_milk_and_finance_to_ai(self):
        today = timezone.localdate()
        self.milk(today, 30)
        self.tx('kirim', 777000, today)
        with patch('apps.assistant.views.chat', return_value='Omborda 30 litr sut bor.') as chat_mock:
            reply, pending_id = bot_service.ask(self.owner, 'Omborda qancha sut bor?')
        self.assertEqual((reply, pending_id), ('Omborda 30 litr sut bor.', None))
        context = chat_mock.call_args.args[1]
        self.assertIn('omborda 30 l sut qolgan', context)
        self.assertIn('777 000', context)


class SystemPromptTests(TestCase):
    def test_tells_ai_to_use_numbers_from_context(self):
        system = build_system('')
        self.assertIn('kirim-chiqim', system)
        self.assertIn("o'ylab topma", system)
        self.assertNotIn('ferma holati', system)  # kontekst bo'sh bo'lsa, ferma holati bo'limi qo'shilmaydi
