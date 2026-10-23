from datetime import date, timedelta

from apps.animals import reproduction
from apps.animals.models import Animal, AnimalEvent, MilkRecord
from apps.tests.test_alerts import CalvingBase
from apps.tests.test_animals import CARDS, EVENTS, AnimalCardBase, rows
from apps.users.alerts import build_alert_lines, dry_off_lines, rebreed_lines
from apps.users.digest import build_worker_digest

TODAY = date(2026, 10, 13)


class ReproBase(CalvingBase):
    def calved(self, days_ago, tag='20', name='Qora', **extra):
        """days_ago kun oldin tug'gan, hozir bug'oz bo'lmagan sigir."""
        cow = Animal.objects.create(farm=self.farm, group=self.group, tag_number=tag, name=name, **extra)
        AnimalEvent.objects.create(animal_group=self.group, animal=cow, event_type='tugilish', title='Buzoq',
                                   animal_count=1, start_date=TODAY - timedelta(days=days_ago))
        return cow

    def info(self, cow):
        cow.refresh_from_db()
        return reproduction.info(cow, TODAY)


class DryOffLogicTests(ReproBase):
    def test_states_by_days_to_calving(self):
        self.assertIsNone(self.info(self.cow(120))['dry_off_state'])  # hali erta
        self.assertEqual(self.info(self.cow(66, tag='2'))['dry_off_state'], 'soon')
        self.assertEqual(self.info(self.cow(60, tag='3'))['dry_off_state'], 'now')
        self.assertEqual(self.info(self.cow(50, tag='4'))['dry_off_state'], 'late')

    def test_dried_off_marker_stops_reminder(self):
        cow = self.cow(50, dried_off_on=TODAY - timedelta(days=2))
        data = self.info(cow)
        self.assertEqual(data['dry_off_state'], 'done')
        self.assertEqual(data['dried_off_on'], TODAY - timedelta(days=2))

    def test_milk_stopped_counts_as_dry(self):
        cow = self.cow(50)
        MilkRecord.objects.create(animal=cow, date=TODAY - timedelta(days=10), liters=5)
        self.assertEqual(self.info(cow)['dry_off_state'], 'done')

    def test_overdue_calving_not_reminded_to_dry_off(self):
        self.assertIsNone(self.info(self.cow(-2))['dry_off_state'])

    def test_male_has_no_reproduction(self):
        bull = Animal.objects.create(farm=self.farm, group=self.group, tag_number='9', sex='erkak')
        self.assertIsNone(reproduction.info(bull, TODAY))


class RebreedLogicTests(ReproBase):
    def test_states_by_days_since_calving(self):
        self.assertEqual(self.info(self.calved(30))['rebreed_state'], 'waiting')
        self.assertEqual(self.info(self.calved(62, tag='2'))['rebreed_state'], 'now')
        self.assertEqual(self.info(self.calved(100, tag='3'))['rebreed_state'], 'late')
        self.assertEqual(self.info(self.calved(120, tag='4'))['rebreed_state'], 'critical')

    def test_pregnant_cow_has_no_rebreed_state(self):
        cow = self.calved(100, pregnant_since=TODAY - timedelta(days=10), due_date=TODAY + timedelta(days=273))
        self.assertIsNone(self.info(cow)['rebreed_state'])

    def test_calving_interval_between_last_two_calvings(self):
        cow = self.calved(100)
        AnimalEvent.objects.create(animal_group=self.group, animal=cow, event_type='tugilish', title='Oldingi',
                                   animal_count=1, start_date=TODAY - timedelta(days=100 + 430))
        data = self.info(cow)
        self.assertEqual(data['calving_interval_days'], 430)
        self.assertTrue(data['interval_long'])

    def test_late_insemination_makes_expected_interval_long(self):
        cow = self.calved(150, pregnant_since=TODAY - timedelta(days=5))
        data = self.info(cow)
        self.assertEqual(data['expected_interval_days'], 145 + 283)
        self.assertTrue(data['interval_long'])


class ReproAlertTests(ReproBase):
    def test_dry_off_line(self):
        self.cow(50)
        lines = dry_off_lines(self.farm, TODAY)
        text = "\n".join(lines)
        self.assertTrue(lines[0].startswith("⚠️"))
        self.assertIn("Quritish vaqti: 1 ta", text)
        self.assertIn("№14 Oqbosh", text)
        self.assertIn("«Quritildi»", text)

    def test_dry_off_silent_when_marked_or_far(self):
        self.cow(50, dried_off_on=TODAY)
        self.cow(120, tag='2')
        self.assertEqual(dry_off_lines(self.farm, TODAY), [])

    def test_rebreed_lines_and_critical_marker(self):
        self.calved(100)
        self.calved(120, tag='21', name='Sariq')
        lines = rebreed_lines(self.farm, TODAY)
        text = "\n".join(lines)
        self.assertTrue(lines[0].startswith("🚨"))
        self.assertIn("Urug'lantirish vaqti: 2 ta", text)
        self.assertIn("400 kundan oshadi", text)
        self.assertLess(text.index("Sariq"), text.index("Qora"))  # eng kechikkani birinchi

    def test_rebreed_silent_while_waiting_and_after_first_week_of_window(self):
        self.calved(30)
        self.calved(75, tag='2')  # 'now' oynasining 7 kunidan keyin
        self.assertEqual(rebreed_lines(self.farm, TODAY), [])

    def test_rebreed_nudge_in_first_week(self):
        self.calved(62)
        self.assertIn("Urug'lantirish vaqti: 1 ta", "\n".join(rebreed_lines(self.farm, TODAY)))

    def test_included_in_farm_alerts(self):
        self.cow(50)
        self.calved(100, tag='2')
        text = "\n".join(build_alert_lines(self.farm, TODAY))
        self.assertIn("Quritish vaqti", text)
        self.assertIn("Urug'lantirish vaqti", text)

    def test_worker_digest_has_dry_off(self):
        from apps.farms.models import Worker
        from apps.users.models import User
        worker = User.objects.create_user(username='ishchi', password='Kuchli-Parol-2026', role='ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        self.cow(50)
        self.assertIn("Quritish vaqti", build_worker_digest(worker, TODAY))


class ReproApiTests(AnimalCardBase):
    def cow(self, **extra):
        today = self.today
        return self.make_animal('14', sex='urgochi', **{
            'pregnant_since': today - timedelta(days=230), 'due_date': today + timedelta(days=53), **extra})

    def test_card_exposes_reproduction(self):
        cow = self.cow()
        data = self.client.get(f'{CARDS}{cow.pk}/').json()
        self.assertEqual(data['reproduction']['dry_off_state'], 'late')
        self.assertIsNone(data['dried_off_on'])

    def test_list_exposes_reproduction(self):
        self.cow()
        row = rows(self.client.get(CARDS))[0]
        self.assertEqual(row['reproduction']['dry_off_state'], 'late')

    def test_mark_and_undo_dried_off(self):
        cow = self.cow()
        r = self.client.patch(f'{CARDS}{cow.pk}/', {'dried_off_on': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['reproduction']['dry_off_state'], 'done')
        r = self.client.patch(f'{CARDS}{cow.pk}/', {'dried_off_on': None}, format='json')
        self.assertEqual(r.json()['reproduction']['dry_off_state'], 'late')

    def test_dried_off_rejected_when_not_pregnant_or_future(self):
        open_cow = self.make_animal('15', sex='urgochi')
        r = self.client.patch(f'{CARDS}{open_cow.pk}/', {'dried_off_on': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 400)
        cow = self.cow()
        r = self.client.patch(f'{CARDS}{cow.pk}/',
                              {'dried_off_on': str(self.today + timedelta(days=1))}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_calving_clears_dried_off(self):
        cow = self.cow(dried_off_on=self.today - timedelta(days=3))
        r = self.client.post(EVENTS, {'animal_group': self.group.pk, 'animal': cow.pk, 'event_type': 'tugilish',
                                      'title': "Buzoq tug'ildi", 'animal_count': 1,
                                      'start_date': str(self.today)}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        cow.refresh_from_db()
        self.assertIsNone(cow.dried_off_on)
        self.assertIsNone(cow.pregnant_since)
        data = self.client.get(f'{CARDS}{cow.pk}/').json()['reproduction']
        self.assertEqual(data['days_since_calving'], 0)
        self.assertEqual(data['rebreed_state'], 'waiting')

    def test_clearing_pregnancy_clears_dried_off(self):
        cow = self.cow(dried_off_on=self.today)
        r = self.client.patch(f'{CARDS}{cow.pk}/', {'pregnant_since': None}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        cow.refresh_from_db()
        self.assertIsNone(cow.dried_off_on)
