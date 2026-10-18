from datetime import date, datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.animals.models import Animal, AnimalEvent, AnimalGroup, AnimalType
from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.tasks.models import Task
from apps.users.alerts import (
    build_alert_lines, calving_lines, feed_forecast_lines, spending_alert_lines, vaccination_lines,
)
from apps.users.digest import build_farm_section, build_worker_digest
from apps.users.models import User

TODAY = date(2026, 10, 13)


class AlertsBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='egasi', password='Kuchli-Parol-2026', role='fermer')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')


class FeedForecastTests(AlertsBase):
    def make_feed(self, quantity, daily_use, days=14, records=None):
        item = InventoryItem.objects.create(farm=self.farm, item_name='Omuxta yem', item_type='ozuqa',
                                            quantity=quantity, unit='kg')
        InventoryItem.objects.filter(pk=item.pk).update(created_at=timezone.make_aware(datetime(2026, 9, 1, 12, 0)))
        for i in range(records if records is not None else days):
            InventoryTransaction.objects.create(inventory_item=item, transaction_type='sarf',
                                                quantity=daily_use, date=TODAY - timedelta(days=i))
        return item

    def test_warns_when_feed_lasts_few_days(self):
        self.make_feed(quantity=30, daily_use=10)  # kuniga 10 kg, 30 kg qoldi
        text = "\n".join(feed_forecast_lines(self.farm, TODAY))
        self.assertIn("Omuxta yem", text)
        self.assertIn("~3 kunga yetadi", text)

    def test_no_warning_when_plenty_left(self):
        self.make_feed(quantity=1000, daily_use=10)
        self.assertEqual(feed_forecast_lines(self.farm, TODAY), [])

    def test_not_enough_records_no_forecast(self):
        self.make_feed(quantity=5, daily_use=10, records=1)
        self.assertEqual(feed_forecast_lines(self.farm, TODAY), [])

    def test_new_item_needs_a_few_days_of_data(self):
        item = self.make_feed(quantity=5, daily_use=10, records=2)
        # mahsulot kecha qo'shilgan: kuzatuv atigi 2 kun -- bashorat berilmaydi
        InventoryItem.objects.filter(pk=item.pk).update(created_at=timezone.make_aware(datetime(2026, 10, 12, 12, 0)))
        self.assertEqual(feed_forecast_lines(self.farm, TODAY), [])

    def test_ignores_non_feed_items(self):
        item = self.make_feed(quantity=1, daily_use=10)
        InventoryItem.objects.filter(pk=item.pk).update(item_type='dori')
        self.assertEqual(feed_forecast_lines(self.farm, TODAY), [])

    def test_empty_stock_says_finished(self):
        self.make_feed(quantity=0, daily_use=10)
        self.assertIn("tugagan", "\n".join(feed_forecast_lines(self.farm, TODAY)))


class SpendingAlertTests(AlertsBase):
    def add(self, d, amount, category='ozuqa', kind='chiqim'):
        Transaction.objects.create(farm=self.farm, transaction_type=kind, category=category,
                                   amount=amount, date=d, recorded_by=self.owner)

    def test_warns_when_spending_up_50_percent(self):
        self.add(date(2026, 9, 5), 1000000)
        self.add(date(2026, 9, 25), 5000000)  # o'tgan oyning keyingi qismi -- hisobga olinmaydi
        self.add(date(2026, 10, 3), 1500000)
        text = "\n".join(spending_alert_lines(self.farm, TODAY))
        self.assertIn("50%", text)
        self.assertIn("Ozuqa", text)

    def test_no_warning_below_threshold(self):
        self.add(date(2026, 9, 5), 1000000)
        self.add(date(2026, 10, 3), 1200000)
        self.assertEqual(spending_alert_lines(self.farm, TODAY), [])

    def test_income_is_not_counted(self):
        self.add(date(2026, 9, 5), 1000000)
        self.add(date(2026, 10, 3), 9000000, category='sotuv', kind='kirim')
        self.assertEqual(spending_alert_lines(self.farm, TODAY), [])

    def test_no_previous_month_no_percent(self):
        self.add(date(2026, 10, 3), 1500000)
        self.assertEqual(spending_alert_lines(self.farm, TODAY), [])

    def test_waits_until_day_five(self):
        self.add(date(2026, 9, 1), 100000)
        self.add(date(2026, 10, 2), 900000)
        self.assertEqual(spending_alert_lines(self.farm, date(2026, 10, 3)), [])

    def test_tiny_amounts_are_ignored(self):
        self.add(date(2026, 9, 5), 10000)
        self.add(date(2026, 10, 3), 50000)  # +400%, lekin farqi atigi 40 000 so'm
        self.assertEqual(spending_alert_lines(self.farm, TODAY), [])


class VaccinationTests(AlertsBase):
    def setUp(self):
        super().setUp()
        self.group = AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Sigir'), count=10)

    def event(self, days_from_today, status='boshlangan', title='Oqsil vaksinasi', group=None):
        return AnimalEvent.objects.create(
            animal_group=group or self.group, event_type='vaksinatsiya', title=title,
            status=status, start_date=TODAY + timedelta(days=days_from_today))

    def test_upcoming_and_today(self):
        self.event(0, title='Bugungi')
        self.event(1, title='Ertangi')
        text = "\n".join(vaccination_lines(self.farm, TODAY))
        self.assertIn("Bugungi — bugun", text)
        self.assertIn("Ertangi — ertaga", text)

    def test_far_future_not_reminded_yet(self):
        self.event(20)
        self.assertEqual(vaccination_lines(self.farm, TODAY), [])

    def test_overdue_recent_is_flagged(self):
        self.event(-2)
        self.assertIn("2 kun kechikdi", "\n".join(vaccination_lines(self.farm, TODAY)))

    def test_old_overdue_is_dropped(self):
        self.event(-30)
        self.assertEqual(vaccination_lines(self.farm, TODAY), [])

    def test_finished_is_not_reminded(self):
        self.event(1, status='yakunlangan')
        self.assertEqual(vaccination_lines(self.farm, TODAY), [])

    def test_sold_group_is_skipped(self):
        AnimalGroup.objects.filter(pk=self.group.pk).update(status='sotilgan')
        self.event(1)
        self.assertEqual(vaccination_lines(self.farm, TODAY), [])

    def test_other_event_types_are_skipped(self):
        AnimalEvent.objects.create(animal_group=self.group, event_type='davolash', title='x',
                                   start_date=TODAY + timedelta(days=1))
        self.assertEqual(vaccination_lines(self.farm, TODAY), [])


class DigestIntegrationTests(AlertsBase):
    def test_alerts_appear_in_farm_section(self):
        group = AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Qo\'y'), count=5)
        AnimalEvent.objects.create(animal_group=group, event_type='vaksinatsiya', title='Chechak',
                                   start_date=TODAY + timedelta(days=1))
        text = build_farm_section(self.farm, TODAY)
        self.assertIn("💉 Vaksinatsiya", text)
        self.assertIn("Chechak", text)

    def test_quiet_farm_has_no_alert_blocks(self):
        self.assertEqual(build_alert_lines(self.farm, TODAY), [])


class CalvingBase(AlertsBase):
    def setUp(self):
        super().setUp()
        self.group = AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Sigir'), count=5)

    def cow(self, days_left, tag='14', name='Oqbosh', **extra):
        """Tug'ishiga days_left kun qolgan bug'oz sigir (manfiy bo'lsa, muddati o'tgan)."""
        return Animal.objects.create(
            farm=self.farm, group=self.group, tag_number=tag, name=name,
            pregnant_since=TODAY - timedelta(days=280 - days_left),
            due_date=TODAY + timedelta(days=days_left), **extra,
        )


class CalvingTests(CalvingBase):
    def test_warns_when_calving_is_near(self):
        self.cow(5)
        lines = calving_lines(self.farm, TODAY)
        text = "\n".join(lines)
        self.assertTrue(lines[0].startswith("🐄"))
        self.assertIn("Tug'ishi yaqin: 1 ta", text)
        self.assertIn("№14 Oqbosh", text)
        self.assertIn("5 kundan keyin", text)
        self.assertNotIn("🚨", text)

    def test_urgent_marker_when_few_days_left(self):
        self.cow(2)
        lines = calving_lines(self.farm, TODAY)
        self.assertTrue(lines[0].startswith("🚨"))
        self.assertIn("2 kundan keyin", "\n".join(lines))

    def test_today_and_tomorrow_wording(self):
        self.cow(0, tag='1', name='Bugun')
        self.cow(1, tag='2', name='Ertaga')
        text = "\n".join(calving_lines(self.farm, TODAY))
        self.assertIn("№1 Bugun — bugun", text)
        self.assertIn("№2 Ertaga — ertaga", text)

    def test_overdue_cow_shows_hint(self):
        self.cow(-3)
        text = "\n".join(calving_lines(self.farm, TODAY))
        self.assertIn("3 kun kechikdi", text)
        self.assertIn("«Tug'ilish»", text)

    def test_hint_not_shown_before_due_date(self):
        self.cow(5)
        self.assertNotIn("«Tug'ilish»", "\n".join(calving_lines(self.farm, TODAY)))

    def test_outside_window_is_not_listed(self):
        self.cow(20, tag='1')  # hali erta
        self.cow(-22, tag='2')  # juda eski, ehtimol eskirgan ma'lumot
        self.assertEqual(calving_lines(self.farm, TODAY), [])

    def test_window_edges_are_included(self):
        self.cow(14, tag='1')
        self.cow(-21, tag='2')
        self.assertIn("Tug'ishi yaqin: 2 ta", "\n".join(calving_lines(self.farm, TODAY)))

    def test_not_pregnant_or_inactive_animals_are_skipped(self):
        Animal.objects.create(farm=self.farm, group=self.group, tag_number='5', name='Bo\'sh')  # bug'oz emas
        self.cow(2, tag='6', status='sotilgan')
        self.cow(2, tag='7', status='olgan')
        self.assertEqual(calving_lines(self.farm, TODAY), [])

    def test_other_farms_are_not_included(self):
        other_owner = User.objects.create_user(username='boshqa', password='Kuchli-Parol-2026', role='fermer')
        other_farm = Farm.objects.create(owner=other_owner, name='Boshqa', location='Qarshi', farm_type='aralash')
        other_group = AnimalGroup.objects.create(farm=other_farm, animal_type=self.group.animal_type, count=1)
        Animal.objects.create(farm=other_farm, group=other_group, tag_number='9',
                              pregnant_since=TODAY - timedelta(days=270),
                              due_date=TODAY + timedelta(days=3))
        self.assertEqual(calving_lines(self.farm, TODAY), [])

    def test_sorted_by_due_date_and_long_list_is_trimmed(self):
        self.cow(9, tag='A', name='Kech')
        self.cow(1, tag='B', name='Erta')
        for i in range(5):
            self.cow(7, tag=f'X{i}', name='Oddiy')
        text = "\n".join(calving_lines(self.farm, TODAY))
        self.assertLess(text.index("Erta"), text.index("Kech"))
        self.assertIn("va yana 2 ta", text)

    def test_recording_the_birth_stops_the_reminder(self):
        cow = self.cow(0)
        Animal.objects.filter(pk=cow.pk).update(pregnant_since=None,
                                                due_date=None)  # "Tug'ilish" yozilganda shunday bo'ladi
        self.assertEqual(calving_lines(self.farm, TODAY), [])

    def test_included_in_farm_section_and_alert_lines(self):
        self.cow(2)
        self.assertIn("Tug'ishi yaqin", build_farm_section(self.farm, TODAY))
        self.assertIn("Tug'ishi yaqin", "\n".join(build_alert_lines(self.farm, TODAY)))


class WorkerCalvingDigestTests(CalvingBase):
    def setUp(self):
        super().setUp()
        self.worker = User.objects.create_user(username='ishchi', password='Kuchli-Parol-2026', role='ishchi')
        Worker.objects.create(user=self.worker, farm=self.farm, can_view_finance=False)

    def test_worker_gets_calving_reminder_without_tasks(self):
        self.cow(2)
        text = build_worker_digest(self.worker, TODAY)
        self.assertIn("bugungi eslatmalar", text)
        self.assertIn("🏡 Baraka", text)
        self.assertIn("№14 Oqbosh", text)

    def test_worker_with_nothing_gets_no_message(self):
        self.assertIsNone(build_worker_digest(self.worker, TODAY))

    def test_tasks_and_calving_in_one_message(self):
        self.cow(1)
        Task.objects.create(farm=self.farm, title="Suv tashish", created_by=self.owner)
        text = build_worker_digest(self.worker, TODAY)
        self.assertIn("bugungi vazifalaringiz", text)
        self.assertIn("Suv tashish", text)
        self.assertIn("Tug'ishi yaqin", text)
        self.assertNotIn("bugungi eslatmalar", text)

    def test_task_only_message_has_no_calving_block(self):
        Task.objects.create(farm=self.farm, title="Suv tashish", created_by=self.owner)
        text = build_worker_digest(self.worker, TODAY)
        self.assertIn("bugungi vazifalaringiz", text)
        self.assertNotIn("Tug'ishi", text)

    def test_user_who_is_not_a_worker_gets_nothing(self):
        self.cow(1)
        stranger = User.objects.create_user(username='begona', password='Kuchli-Parol-2026', role='ishchi')
        self.assertIsNone(build_worker_digest(stranger, TODAY))

