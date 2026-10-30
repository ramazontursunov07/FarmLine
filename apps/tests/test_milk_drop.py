from datetime import timedelta
from decimal import Decimal

from apps.animals.models import Animal, MilkRecord
from apps.tests.test_alerts import TODAY, CalvingBase
from apps.users.alerts import build_alert_lines, milk_drop_lines


class MilkDropTests(CalvingBase):
    def milk_cow(self, tag='14', name='Oqbosh', before=20, after=20, recent_days=(1, 2, 3), **extra):
        """Oldingi 14 kun `before` litr, oxirgi kunlar `after` litr sog'adigan sigir."""
        cow = Animal.objects.create(farm=self.farm, group=self.group, tag_number=tag, name=name, **extra)
        for i in range(1, 18):
            if i <= 3 and i not in recent_days:
                continue
            MilkRecord.objects.create(animal=cow, date=TODAY - timedelta(days=i), session='kun',
                                      liters=Decimal(after if i <= 3 else before))
        return cow

    def test_warns_when_milk_drops_sharply(self):
        self.milk_cow(before=20, after=12)
        lines = milk_drop_lines(self.farm, TODAY)
        text = "\n".join(lines)
        self.assertTrue(lines[0].startswith("📉"))
        self.assertIn("Sut kamaydi: 1 ta", text)
        self.assertIn("№14 Oqbosh", text)
        self.assertIn("20.0 → 12.0 l", text)
        self.assertIn("−40%", text)

    def test_stable_milk_no_warning(self):
        self.milk_cow(before=20, after=19)
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_low_producer_ignored(self):
        self.milk_cow(before=4, after=1)
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_needs_recent_records(self):
        self.milk_cow(before=20, after=5, recent_days=(1,))
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_today_is_not_counted(self):
        cow = self.milk_cow(before=20, after=20)
        MilkRecord.objects.create(animal=cow, date=TODAY, session='ertalab', liters=Decimal('2'))
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_dried_off_cow_ignored(self):
        self.milk_cow(before=20, after=5, dried_off_on=TODAY - timedelta(days=2))
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_cow_close_to_calving_ignored(self):
        self.milk_cow(before=20, after=5, pregnant_since=TODAY - timedelta(days=230),
                      due_date=TODAY + timedelta(days=50))
        self.assertEqual(milk_drop_lines(self.farm, TODAY), [])

    def test_included_in_daily_alerts(self):
        self.milk_cow(before=20, after=10)
        self.assertIn("Sut kamaydi", "\n".join(build_alert_lines(self.farm, TODAY)))
