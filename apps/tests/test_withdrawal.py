from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from apps.animals.models import AnimalEvent, MilkRecord
from apps.inventory.models import InventoryItem
from apps.users.alerts import build_alert_lines, withdrawal_lines

from .test_animals import CARDS, EVENTS, MILK, AnimalCardBase

INVENTORY = '/api/inventory-item/'
SALES = '/api/animals-milk-sale/'
STOCK = '/api/animals-milk-sale/stock/'


class WithdrawalBase(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.cow = self.make_animal('77', name='Oqtosh', sex='urgochi')
        self.other = self.make_animal('78', name='Qoraqiz', sex='urgochi')
        self.med = InventoryItem.objects.create(
            farm=self.farm, item_name='Penitsillin', item_type='dori', quantity=10, unit='dona', withdrawal_days=4)

    def milk(self, animal, day_offset, liters):
        return MilkRecord.objects.create(
            animal=animal, date=self.today + timedelta(days=day_offset), liters=Decimal(liters))

    def treat(self, **extra):
        data = {'animal_group': self.group.pk, 'animal': self.cow.pk, 'event_type': 'davolash',
                'title': 'Mastit', 'start_date': str(self.today - timedelta(days=1)),
                'medicine': self.med.pk}
        data.update(extra)
        return self.client.post(EVENTS, data, format='json')


class EventFieldTests(WithdrawalBase):
    def test_days_come_from_medicine(self):
        with patch('apps.animals.views.notify_users'):
            r = self.treat()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['withdrawal_days'], 4)
        self.assertEqual(r.json()['medicine_name'], 'Penitsillin')
        self.assertIsNone(r.json()['withdrawal_until'])  # davolash tugamagan

    def test_days_can_be_overridden_and_until_is_computed(self):
        end = self.today
        with patch('apps.animals.views.notify_users'):
            r = self.treat(withdrawal_days=7, status='yakunlangan', end_date=str(end))
        self.assertEqual(r.json()['withdrawal_until'], str(end + timedelta(days=7)))

    def test_not_for_other_event_types(self):
        r = self.treat(event_type='kasallik')
        self.assertEqual(r.json()['withdrawal_days'], 0)
        self.assertIsNone(r.json()['medicine'])

    def test_only_medicine_items_allowed(self):
        feed = InventoryItem.objects.create(farm=self.farm, item_name='Silos', item_type='ozuqa', quantity=1, unit='kg')
        r = self.treat(medicine=feed.pk)
        self.assertEqual(r.status_code, 400)

    def test_inventory_item_stores_days_only_for_medicine(self):
        r = self.client.post(INVENTORY, {'farm': self.farm.pk, 'item_name': 'Antibiotik', 'item_type': 'dori',
                                         'unit': 'dona', 'withdrawal_days': 5}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()['withdrawal_days'], 5)
        r = self.client.post(INVENTORY, {'farm': self.farm.pk, 'item_name': 'Pichan', 'item_type': 'ozuqa',
                                         'unit': 'kg', 'withdrawal_days': 5}, format='json')
        self.assertEqual(r.json()['withdrawal_days'], 0)


class AnimalFlagTests(WithdrawalBase):
    def card(self, animal):
        return self.client.get(f'{CARDS}{animal.pk}/').json()

    def test_card_shows_ongoing_withdrawal(self):
        with patch('apps.animals.views.notify_users'):
            self.treat()
        w = self.card(self.cow)['withdrawal']
        self.assertTrue(w['ongoing'])
        self.assertEqual(w['medicine'], 'Penitsillin')
        self.assertIsNone(self.card(self.other)['withdrawal'])

    def test_finished_treatment_counts_days_after_end(self):
        with patch('apps.animals.views.notify_users'):
            self.treat(status='yakunlangan', start_date=str(self.today - timedelta(days=2)),
                       end_date=str(self.today - timedelta(days=1)))
        w = self.card(self.cow)['withdrawal']  # 4 kun: kecha + 4 = bugundan 3 kun keyin
        self.assertFalse(w['ongoing'])
        self.assertEqual(w['days_left'], 3)

    def test_expired_withdrawal_disappears(self):
        with patch('apps.animals.views.notify_users'):
            self.treat(status='yakunlangan', start_date=str(self.today - timedelta(days=20)),
                       end_date=str(self.today - timedelta(days=10)))
        self.assertIsNone(self.card(self.cow)['withdrawal'])

    def test_group_level_treatment_covers_all_cards(self):
        with patch('apps.animals.views.notify_users'):
            self.treat(animal=None)
        self.assertIsNotNone(self.card(self.cow)['withdrawal'])
        self.assertIsNotNone(self.card(self.other)['withdrawal'])


class MilkSaleTests(WithdrawalBase):
    def setUp(self):
        super().setUp()
        self.milk(self.cow, -3, '10')  # davolashdan oldin: sotsa bo'ladi
        self.milk(self.cow, 0, '8')  # davolash vaqtida: sotib bo'lmaydi
        self.milk(self.other, 0, '12')  # sog'lom sigir
        with patch('apps.animals.views.notify_users'):
            self.treat()

    def sale(self, liters, **extra):
        data = {'farm': self.farm.pk, 'date': str(self.today), 'liters': liters, 'price_per_liter': 5000}
        data.update(extra)
        return self.client.post(SALES, data, format='json')

    def test_stock_reports_withheld_and_list(self):
        s = self.client.get(f'{STOCK}?farm={self.farm.pk}').json()
        self.assertEqual(Decimal(s['available']), Decimal('30'))
        self.assertEqual(Decimal(s['withheld']), Decimal('8'))
        self.assertEqual(Decimal(s['sellable']), Decimal('22'))
        self.assertEqual(s['withdrawals'][0]['tag_number'], '77')

    def test_selling_within_sellable_is_fine(self):
        self.assertEqual(self.sale(22).status_code, 201)

    def test_selling_withheld_milk_is_blocked_with_clear_message(self):
        r = self.sale(25)
        self.assertEqual(r.status_code, 400)
        self.assertIn('ushlab turish', r.json()['liters'])
        self.assertIn('22', r.json()['liters'])

    def test_owner_can_confirm_and_sell_anyway(self):
        r = self.sale(25, confirm_withheld=True)
        self.assertEqual(r.status_code, 201, r.content)

    def test_after_period_milk_is_sellable_again_only_for_clean_days(self):
        # Muddat tugagach ham davolash vaqtidagi sut yaroqsiz bo'lib qoladi
        AnimalEvent.objects.update(status='yakunlangan', end_date=self.today - timedelta(days=9),
                                   start_date=self.today - timedelta(days=10))
        s = self.client.get(f'{STOCK}?farm={self.farm.pk}').json()
        self.assertEqual(s['withdrawals'], [])
        self.assertEqual(Decimal(s['withheld']), Decimal('0'))


class TelegramTests(WithdrawalBase):
    def test_owner_notified_when_treatment_has_withdrawal(self):
        with patch('apps.animals.views.notify_users') as notify:
            self.treat()
        users, text = notify.call_args.args
        self.assertEqual(users, [self.owner])
        self.assertIn('Penitsillin', text)
        self.assertIn('sotmang', text)
        self.assertIn('№77', text)

    def test_no_notification_without_withdrawal(self):
        self.med.withdrawal_days = 0
        self.med.save()
        with patch('apps.animals.views.notify_users') as notify:
            self.treat()
        notify.assert_not_called()

    def test_daily_digest_lists_withheld_animals(self):
        with patch('apps.animals.views.notify_users'):
            self.treat(status='yakunlangan', start_date=str(self.today - timedelta(days=2)),
                       end_date=str(self.today - timedelta(days=1)))
        lines = withdrawal_lines(self.farm, self.today)
        text = '\n'.join(lines)
        self.assertIn('№77', text)
        self.assertIn('3 kun qoldi', text)
        self.assertIn(lines[0], build_alert_lines(self.farm, self.today))

    def test_digest_empty_without_withdrawals(self):
        self.assertEqual(withdrawal_lines(self.farm, self.today), [])
