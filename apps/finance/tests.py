from rest_framework.test import APITestCase

from apps.farms.models import Farm
from apps.users.models import User


class FinanceFilterTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='fermer1', password='Kuchli-Parol-2026', role='fermer')
        Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.client.force_authenticate(self.owner)

    def test_bad_dates_return_400_not_500(self):
        for params in ('date_from=2026-13-45', 'date_to=kecha', 'date_from=abc'):
            r = self.client.get(f'/api/finance/?{params}')
            self.assertEqual(r.status_code, 400, params)

    def test_bad_farm_returns_400(self):
        self.assertEqual(self.client.get('/api/finance/?farm=abc').status_code, 400)

    def test_valid_filters_ok(self):
        r = self.client.get('/api/finance/?date_from=2026-01-01&date_to=2026-12-31')
        self.assertEqual(r.status_code, 200)
