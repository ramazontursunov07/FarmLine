from datetime import timedelta
from decimal import Decimal

from apps.animals.models import AnimalEvent, MilkRecord
from apps.tests.test_animals import AnimalCardBase
from apps.users.alerts import build_alert_lines, repro_lines

URL = '/api/animals-card/repro/'


class ReproBase(AnimalCardBase):
    def setUp(self):
        super().setUp()
        self.old = self.today - timedelta(days=1500)

    def cow(self, tag, **kw):
        kw.setdefault('birth_date', self.old)
        kw.setdefault('sex', 'urgochi')
        return self.make_animal(tag, **kw)

    def calved(self, cow, days_ago):
        return AnimalEvent.objects.create(
            animal_group=self.group, animal=cow, event_type='tugilish', title="Tug'ilish", status='yakunlangan',
            start_date=self.today - timedelta(days=days_ago), animal_count=1, recorded_by=self.owner)

    def milk(self, cow, days_ago=0):
        MilkRecord.objects.create(animal=cow, date=self.today - timedelta(days=days_ago),
                                  liters=Decimal('10'), recorded_by=self.owner)

    def report(self):
        r = self.client.get(URL, {'farm': self.farm.pk})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()


class DryOffTests(ReproBase):
    def pregnant(self, tag, due_in):
        c = self.cow(tag, pregnant_since=self.today - timedelta(days=283 - due_in),
                     due_date=self.today + timedelta(days=due_in))
        self.milk(c)
        return c

    def test_dry_off_window(self):
        soon = self.pregnant('1', 64)    # quritishga 4 kun
        due = self.pregnant('2', 55)     # quritish vaqti o'tdi
        far = self.pregnant('3', 100)    # hali erta
        rows = {r['id']: r for r in self.report()['dry_off']}
        self.assertEqual(set(rows), {soon.pk, due.pk})
        self.assertEqual(rows[soon.pk]['days_to_dry'], 4)
        self.assertEqual(rows[soon.pk]['status'], 'yaqin')
        self.assertEqual(rows[due.pk]['status'], 'vaqti')
        self.assertEqual(rows[due.pk]['dry_date'], str(self.today + timedelta(days=55 - 60)))
        self.assertNotIn(far.pk, rows)

    def test_already_dry_cow_is_skipped(self):
        c = self.cow('1', pregnant_since=self.today - timedelta(days=240), due_date=self.today + timedelta(days=43))
        self.milk(c, days_ago=30)   # 30 kundan beri sut yo'q: quritilgan
        self.assertEqual(self.report()['dry_off'], [])

    def test_cow_without_any_milk_records_still_reminded(self):
        self.cow('1', pregnant_since=self.today - timedelta(days=230), due_date=self.today + timedelta(days=53))
        self.assertEqual(len(self.report()['dry_off']), 1)

    def test_overdue_pregnancy_not_listed(self):
        c = self.cow('1', pregnant_since=self.today - timedelta(days=300), due_date=self.today - timedelta(days=5))
        self.milk(c)
        self.assertEqual(self.report()['dry_off'], [])


class RebreedTests(ReproBase):
    def test_rebreed_statuses(self):
        early = self.cow('1'); self.calved(early, 30)
        ready = self.cow('2'); self.calved(ready, 70)
        late = self.cow('3'); self.calved(late, 130)
        rows = {r['id']: r for r in self.report()['rebreed']}
        self.assertEqual(set(rows), {ready.pk, late.pk})
        self.assertEqual(rows[ready.pk]['status'], 'vaqti')
        self.assertEqual(rows[late.pk]['status'], 'kechikdi')
        self.assertEqual(rows[late.pk]['projected_interval'], 130 + 283)
        self.assertEqual([r['id'] for r in self.report()['rebreed']], [late.pk, ready.pk])  # eng kechikkani birinchi

    def test_pregnant_cow_not_in_rebreed(self):
        c = self.cow('1', pregnant_since=self.today - timedelta(days=20), due_date=self.today + timedelta(days=263))
        self.calved(c, 90)
        self.assertEqual(self.report()['rebreed'], [])

    def test_never_calved_or_not_cattle_ignored(self):
        self.cow('1')   # tug'ish tarixi yo'q
        from apps.animals.models import AnimalGroup, AnimalType
        sheep = AnimalGroup.objects.create(farm=self.farm, animal_type=AnimalType.objects.create(name="Qo'y"), count=1)
        s = self.make_animal('9', group=sheep, sex='urgochi', birth_date=self.old)
        AnimalEvent.objects.create(animal_group=sheep, animal=s, event_type='tugilish', title='t', status='yakunlangan',
                                   start_date=self.today - timedelta(days=100), animal_count=1, recorded_by=self.owner)
        self.assertEqual(self.report()['rebreed'], [])

    def test_sold_and_male_ignored(self):
        a = self.cow('1', status='sotilgan'); self.calved(a, 100)
        self.assertEqual(self.report()['rebreed'], [])


class IntervalTests(ReproBase):
    def test_actual_gaps_and_average(self):
        c = self.cow('1')
        self.calved(c, 800); self.calved(c, 400); self.calved(c, 10)   # oraliq 400 va 390
        c.pregnant_since = self.today - timedelta(days=5); c.due_date = self.today + timedelta(days=278); c.save()
        rep = self.report()
        row = rep['intervals'][0]
        self.assertEqual(row['gaps'], [400, 390])
        self.assertEqual(rep['summary']['avg_interval'], '395')
        self.assertEqual(row['projected'], 288)   # 10 kun oldin tug'gan, keyingisi 278 kundan keyin
        self.assertEqual(rep['summary']['avg_days_open'], '5')

    def test_verdict_long_interval(self):
        c = self.cow('1'); self.calved(c, 200)   # 200 + 283 = 483 > 420
        self.assertEqual(self.report()['intervals'][0]['verdict'], 'uzun')


class AccessAndAlertTests(ReproBase):
    def test_requires_farm_and_membership(self):
        self.assertEqual(self.client.get(URL).status_code, 400)
        from apps.tests.test_animals import make_user
        self.client.force_authenticate(make_user('begona'))
        self.assertEqual(self.client.get(URL, {'farm': self.farm.pk}).status_code, 403)
        self.client.force_authenticate(self.worker)
        self.assertEqual(self.client.get(URL, {'farm': self.farm.pk}).status_code, 200)

    def test_alert_lines(self):
        due = self.cow('1', name='Mushuk', pregnant_since=self.today - timedelta(days=235),
                       due_date=self.today + timedelta(days=48))
        self.milk(due)
        late = self.cow('2'); self.calved(late, 120)
        text = "\n".join(repro_lines(self.farm, self.today))
        self.assertIn('Quritish vaqti: 1 ta', text)
        self.assertIn('№1 Mushuk', text)
        self.assertIn('Qayta urug', text)
        self.assertIn('tug\'ishlar orasi ~403 kun', text)
        self.assertIn('Quritish vaqti', "\n".join(build_alert_lines(self.farm, self.today)))

    def test_no_lines_when_nothing_due(self):
        self.assertEqual(repro_lines(self.farm, self.today), [])
