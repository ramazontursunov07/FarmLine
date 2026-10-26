from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.animals.models import MilkRecord, MilkSale
from apps.finance.models import Transaction
from apps.tests.test_animals import AnimalCardBase

PROFIT = '/api/animals-milk/profit/'


class MilkProfitTests(AnimalCardBase):
    def setUp(self):
        super().setUp()
        # Oyning 1-kuni bo'lsa ham ishlashi uchun: joriy oyda kamida bitta kun bor (bugun)
        self.day = self.today
        self.start = self.today.replace(day=1)
        old = self.today - timedelta(days=1500)
        self.good = self.make_animal('1', name='Yaxshi', sex='urgochi', birth_date=old)
        self.bad = self.make_animal('2', name='Kam', sex='urgochi', birth_date=old)
        self.dry = self.make_animal('3', name='Quruq', sex='urgochi', birth_date=old)
        self.calf = self.make_animal('4', name='Buzoq', sex='urgochi', birth_date=self.today - timedelta(days=100))
        self.bull = self.make_animal('5', name='Buqa', sex='erkak', birth_date=old)
        self.days = (self.today - self.start).days + 1
        MilkRecord.objects.create(animal=self.good, date=self.day, liters=Decimal('30'), recorded_by=self.owner)
        MilkRecord.objects.create(animal=self.bad, date=self.day, liters=Decimal('2'), recorded_by=self.owner)
        Transaction.objects.create(farm=self.farm, transaction_type='chiqim', category='ozuqa',
                                   amount=Decimal('300000'), date=self.day, recorded_by=self.owner)
        Transaction.objects.create(farm=self.farm, transaction_type='chiqim', category='ish_haqi',
                                   amount=Decimal('60000'), date=self.day, recorded_by=self.owner)
        MilkSale.objects.create(farm=self.farm, date=self.day, liters=Decimal('10'),
                                price_per_liter=Decimal('5000'), amount=Decimal('50000'), recorded_by=self.owner)

    def report(self, **params):
        params.setdefault('farm', self.farm.pk)
        return self.client.get(PROFIT, params)

    def test_cost_per_liter_and_price(self):
        r = self.report()
        self.assertEqual(r.status_code, 200, r.content)
        t = r.json()['totals']
        self.assertEqual(t['liters'], '32.0')
        self.assertEqual(t['cost'], '360000')
        self.assertEqual(t['cost_per_liter'], '11250')  # 360000 / 32
        self.assertEqual((t['price_per_liter'], t['price_source']), ('5000', 'sotuv'))
        self.assertEqual(t['profit'], str(160000 - 360000))  # 32 l * 5000 - xarajat

    def test_feed_cost_per_liter(self):
        t = self.report().json()['totals']
        self.assertEqual(t['feed_cost'], '300000')  # faqat "ozuqa" chiqimi
        self.assertEqual(t['feed_cost_per_liter'], '9375')  # 300000 / 32

    def test_only_adult_females_are_counted(self):
        ids = {c['id'] for c in self.report().json()['cows']}
        self.assertEqual(ids, {self.good.pk, self.bad.pk, self.dry.pk})  # buzoq va buqa yo'q

    def test_cows_sorted_worst_first_and_verdicts(self):
        cows = self.report().json()['cows']
        verdicts = {c['name']: c['verdict'] for c in cows}
        self.assertEqual(verdicts, {'Yaxshi': 'foyda', 'Kam': 'zarar', 'Quruq': 'sut_yoq'})
        profits = [Decimal(c['profit']) for c in cows]
        self.assertEqual(profits, sorted(profits))
        # xarajat 3 ta sigirga teng bo'linadi
        self.assertEqual({c['cost'] for c in cows}, {'120000'})

    def test_good_cow_is_profitable_when_cheap(self):
        Transaction.objects.all().delete()
        Transaction.objects.create(farm=self.farm, transaction_type='chiqim', category='ozuqa',
                                   amount=Decimal('30000'), date=self.day, recorded_by=self.owner)
        cows = {c['name']: c for c in self.report().json()['cows']}
        self.assertEqual(cows['Yaxshi']['verdict'], 'foyda')  # 30 l * 5000 = 150000 > 10000
        self.assertEqual(cows['Kam']['verdict'], 'foyda')  # 2 l * 5000 = 10000 >= 10000
        self.assertEqual(cows['Quruq']['verdict'], 'sut_yoq')

    def test_exclude_categories(self):
        t = self.report(exclude='ish_haqi').json()['totals']
        self.assertEqual(t['cost'], '300000')

    def test_manual_price_overrides(self):
        t = self.report(price='8000').json()['totals']
        self.assertEqual((t['price_per_liter'], t['price_source']), ('8000', 'qolda'))

    def test_no_price_without_sales(self):
        MilkSale.objects.all().delete()
        j = self.report().json()
        self.assertIsNone(j['totals']['price_per_liter'])
        self.assertTrue(any('narxi' in w for w in j['warnings']))
        self.assertIsNone(j['cows'][0]['profit'])

    def test_no_milk_gives_warning_not_crash(self):
        MilkRecord.objects.all().delete()
        j = self.report().json()
        self.assertIsNone(j['totals']['cost_per_liter'])
        self.assertTrue(any("sog'ilgan sut yozilmagan" in w for w in j['warnings']))

    def test_other_month_is_isolated(self):
        last_month = (self.start - timedelta(days=1)).strftime('%Y-%m')
        j = self.report(month=last_month).json()
        self.assertEqual(j['totals']['liters'], '0.0')
        self.assertEqual(j['totals']['cost'], '0')

    def test_future_and_bad_month_rejected(self):
        self.assertEqual(self.report(month='2999-01').status_code, 400)
        self.assertEqual(self.report(month='abc').status_code, 400)

    def test_requires_finance_access(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.report().status_code, 403)

    def test_requires_farm(self):
        self.assertEqual(self.client.get(PROFIT).status_code, 400)

    def test_break_even_daily_liters(self):
        cow = {c['name']: c for c in self.report().json()['cows']}['Kam']
        # 120000 / kunlar / 5000 so'm
        expected = Decimal('120000') / self.days / Decimal('5000')
        self.assertEqual(cow['break_even_daily'], str(expected.quantize(Decimal('0.1'))))
