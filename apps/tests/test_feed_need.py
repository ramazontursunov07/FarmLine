from datetime import timedelta
from decimal import Decimal

from apps.animals.models import AnimalGroup, AnimalType, MilkRecord, WeightRecord
from apps.inventory.feed_need import dairy_ration, detect_kind
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.tests.test_animals import AnimalCardBase, make_user
from apps.users.alerts import build_alert_lines, feed_forecast_lines

NEED = '/api/inventory-item/feed-need/'


def kind(report, name):
    return next(k for k in report['kinds'] if k['kind'] == name)


class FeedNeedBase(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.group.count = 1
        self.group.save()
        self.cow = self.make_animal('1', name='Len', sex='urgochi', birth_date=self.today - timedelta(days=1500))

    def milk(self, animal, liters, days=5):
        for i in range(days):
            MilkRecord.objects.create(animal=animal, date=self.today - timedelta(days=i), liters=Decimal(liters),
                                      recorded_by=self.owner)

    def weigh(self, animal, kg):
        WeightRecord.objects.create(animal=animal, date=self.today, weight_kg=Decimal(kg), recorded_by=self.owner)

    def item(self, name, qty, unit='kg', **extra):
        return InventoryItem.objects.create(farm=self.farm, item_name=name, item_type='ozuqa',
                                            quantity=Decimal(qty), unit=unit, **extra)

    def report(self, **params):
        params.setdefault('farm', self.farm.pk)
        return self.client.get(NEED, params)


class RationTests(FeedNeedBase):
    def test_ration_follows_guide(self):
        mid, high = dairy_ration(11), dairy_ration(20)
        self.assertEqual((mid['dagal'], mid['shirali'], mid['konsentrat']), (Decimal('4.5'), Decimal('13.5'), Decimal('2.5')))
        self.assertTrue(Decimal('20') <= high['shirali'] <= Decimal('25'))      # qo'llanma: 20-25 kg silos
        self.assertTrue(Decimal('6') <= high['konsentrat'] <= Decimal('8') or Decimal('5.9') < high['konsentrat'] < 8)
        self.assertTrue(Decimal('5') <= high['dagal'] <= Decimal('6'))

    def test_kind_detection(self):
        self.assertEqual(detect_kind('Silos'), 'shirali')
        self.assertEqual(detect_kind('Beda pichan'), 'dagal')
        self.assertEqual(detect_kind("Makkajo'xori"), 'konsentrat')
        self.assertEqual(detect_kind('Omuxta yem'), 'konsentrat')
        self.assertIsNone(detect_kind('Tuz'))


class NeedTests(FeedNeedBase):
    def test_need_grows_with_milk(self):
        self.milk(self.cow, 10)
        low = Decimal(kind(self.report().json(), 'konsentrat')['need_kg_per_day'])
        MilkRecord.objects.all().update(liters=Decimal('20'))
        high = Decimal(kind(self.report().json(), 'konsentrat')['need_kg_per_day'])
        self.assertLess(int(low), int(high))

    def test_need_scales_with_weight_and_is_clamped(self):
        self.milk(self.cow, 11)
        base = Decimal(kind(self.report().json(), 'shirali')['need_kg_per_day'])   # 13,5 kg (vazn yo'q = 550 kg)
        self.weigh(self.cow, 650)
        heavy = Decimal(kind(self.report().json(), 'shirali')['need_kg_per_day'])
        self.assertGreater(heavy, base)
        WeightRecord.objects.all().update(weight_kg=Decimal('2000'))               # nomaqbul vazn chegaralanadi
        capped = Decimal(kind(self.report().json(), 'shirali')['need_kg_per_day'])
        self.assertEqual(capped, Decimal('17.6'))                                  # 13,5 * 1,3 (eng ko'pi bilan)

    def test_stock_days_left_and_tonnes(self):
        self.milk(self.cow, 11)
        self.item('Silos', '1', unit='tonna')                                      # 1000 kg
        k = kind(self.report().json(), 'shirali')
        self.assertEqual(k['stock_kg'], '1000')
        self.assertEqual(k['need_kg_per_day'], '13.5')
        self.assertEqual(Decimal(k['days_left']), Decimal('74.1'))                 # 1000 / 13,5

    def test_unit_without_kg_is_excluded_until_weight_given(self):
        self.milk(self.cow, 11)
        item = self.item('Omuxta yem', '10', unit='qop')
        j = self.report().json()
        self.assertEqual(kind(j, 'konsentrat')['stock_kg'], '0')
        self.assertTrue(any('Kg/birlik' in w for w in j['warnings']))
        item.kg_per_unit = Decimal('50')
        item.save()
        self.assertEqual(kind(self.report().json(), 'konsentrat')['stock_kg'], '500')

    def test_unknown_item_warns_and_override_works(self):
        self.milk(self.cow, 11)
        tuz = self.item('Tuz', '100')
        self.assertTrue(any('Tuz' in w for w in self.report().json()['warnings']))
        tuz.feed_kind = 'hisobsiz'
        tuz.save()
        self.assertFalse(any('Tuz' in w for w in self.report().json()['warnings']))
        tuz.feed_kind = 'konsentrat'
        tuz.save()
        self.assertEqual(kind(self.report().json(), 'konsentrat')['stock_kg'], '100')

    def test_uncarded_cattle_are_assumed_milking(self):
        self.group.count = 11                         # 1 kartochka + 10 kartochkasiz
        self.group.save()
        j = self.report().json()
        self.assertTrue(any('kartochkasi ochilmagan' in w for w in j['warnings']))
        self.assertEqual({c['key'] for c in j['categories']}, {'kartochkasiz', 'saqlovchi'})
        # 10 ta * 13,5 kg silos (taxmin) + 1 ta katta hayvon * 12 kg
        self.assertEqual(kind(j, 'shirali')['need_kg_per_day'], '147.0')

    def test_dry_pregnant_calf_and_young(self):
        self.group.count = 4
        self.group.save()
        dry = self.make_animal('2', sex='urgochi', birth_date=self.today - timedelta(days=1500),
                               pregnant_since=self.today - timedelta(days=200))
        young = self.make_animal('3', sex='urgochi', birth_date=self.today - timedelta(days=200))
        calf = self.make_animal('4', sex='urgochi', birth_date=self.today - timedelta(days=30))
        j = self.report().json()
        keys = {c['key'] for c in j['categories']}
        self.assertEqual(keys, {'saqlovchi', 'quruq', 'yosh', 'buzoq'})
        self.assertEqual(kind(j, 'dagal')['need_kg_per_day'], '15.8')
        del dry, young, calf

    def test_sheep_and_poultry_per_head(self):
        sheep = AnimalType.objects.create(name="Qo'y")
        hens = AnimalType.objects.create(name='Tovuq')
        AnimalGroup.objects.create(farm=self.farm, animal_type=sheep, count=10)
        AnimalGroup.objects.create(farm=self.farm, animal_type=hens, count=100)
        self.group.status = 'olgan'
        self.group.save()
        j = self.report().json()
        self.assertEqual(kind(j, 'dagal')['need_kg_per_day'], '15.0')              # 10 * 1,5 kg
        self.assertEqual(kind(j, 'konsentrat')['need_kg_per_day'], '14.5')  # 3 + 11,5

    def test_unsupported_type_is_reported(self):
        pigs = AnimalType.objects.create(name="Cho'chqa")
        AnimalGroup.objects.create(farm=self.farm, animal_type=pigs, count=5)
        self.assertTrue(any("Cho'chqa" in w for w in self.report().json()['warnings']))

    def test_actual_use_comparison(self):
        self.milk(self.cow, 11)
        item = self.item('Silos', '5000')
        InventoryItem.objects.filter(pk=item.pk).update(created_at=item.created_at - timedelta(days=30))
        for i in range(5):  # kuniga ~1 kg: ehtiyojdan ancha kam
            InventoryTransaction.objects.create(inventory_item=item, transaction_type='sarf', quantity=Decimal('1'),
                                                date=self.today - timedelta(days=i))
        k = kind(self.report().json(), 'shirali')
        self.assertEqual(k['compare'], 'kam')


class AccessTests(FeedNeedBase):
    def test_worker_can_view_stranger_cannot(self):
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.report().status_code, 200)
        self.client.force_authenticate(make_user('begona', 'fermer'))
        self.assertEqual(self.report().status_code, 403)

    def test_farm_required(self):
        self.assertEqual(self.client.get(NEED).status_code, 400)


class AlertTests(FeedNeedBase):
    def test_warns_by_need_even_without_usage_history(self):
        self.milk(self.cow, 11)
        self.item('Silos', '40')                       # 40 kg / ~13,5 kg = ~2 kun
        lines = feed_forecast_lines(self.farm, self.today)
        text = "\n".join(lines)
        self.assertIn("ehtiyoji bo'yicha", text)
        self.assertIn('Silos', text)
        self.assertIn('kunga yetadi', text)

    def test_no_warning_when_plenty(self):
        self.milk(self.cow, 11)
        self.item('Silos', '5000')
        self.assertEqual(feed_forecast_lines(self.farm, self.today), [])

    def test_history_line_is_skipped_for_covered_items(self):
        self.milk(self.cow, 11)
        item = self.item('Silos', '40')
        InventoryItem.objects.filter(pk=item.pk).update(created_at=item.created_at - timedelta(days=30))
        for i in range(5):
            InventoryTransaction.objects.create(inventory_item=item, transaction_type='sarf', quantity=Decimal('20'),
                                                date=self.today - timedelta(days=i))
        lines = feed_forecast_lines(self.farm, self.today)
        self.assertEqual(sum('Silos' in l for l in lines), 1)                      # ikki marta takrorlanmaydi
        self.assertIn(lines[0], build_alert_lines(self.farm, self.today))

    def test_falls_back_to_history_without_animals(self):
        AnimalGroup.objects.all().update(count=0)
        from apps.animals.models import Animal
        Animal.objects.all().delete()
        item = self.item('Silos', '40')
        InventoryItem.objects.filter(pk=item.pk).update(created_at=item.created_at - timedelta(days=30))
        for i in range(5):
            InventoryTransaction.objects.create(inventory_item=item, transaction_type='sarf', quantity=Decimal('20'),
                                                date=self.today - timedelta(days=i))
        text = "\n".join(feed_forecast_lines(self.farm, self.today))
        self.assertIn('Yem bashorati', text)
