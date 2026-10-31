from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.animals.models import AnimalGroup, AnimalType
from apps.farms.models import Farm
from apps.users.models import User

REFRESH = '/api/users/token/refresh/'
LOGOUT = '/api/users/logout/'
GROUPS = '/api/animals-group/'


class RefreshTokenTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='egasi', password='Kuchli-Parol-2026', role='fermer')
        self.client = APIClient()

    def test_rotated_refresh_token_cannot_be_reused(self):
        old = str(RefreshToken.for_user(self.user))
        first = self.client.post(REFRESH, {'refresh': old}, format='json')
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.json()['refresh'], old)
        again = self.client.post(REFRESH, {'refresh': old}, format='json')
        self.assertEqual(again.status_code, 401)  # eski token bekor qilingan
        newer = self.client.post(REFRESH, {'refresh': first.json()['refresh']}, format='json')
        self.assertEqual(newer.status_code, 200)

    def test_logout_blacklists_refresh_token(self):
        token = str(RefreshToken.for_user(self.user))
        r = self.client.post(LOGOUT, {'refresh': token}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        self.assertEqual(self.client.post(REFRESH, {'refresh': token}, format='json').status_code, 401)

    def test_logout_works_without_access_token_and_ignores_garbage(self):
        for body in ({}, {'refresh': ''}, {'refresh': 'yaroqsiz'}, {'refresh': 123}):
            self.assertEqual(self.client.post(LOGOUT, body, format='json').status_code, 200, body)
        self.assertEqual(OutstandingToken.objects.count(), 0)

    def test_logging_out_twice_is_fine(self):
        token = str(RefreshToken.for_user(self.user))
        self.assertEqual(self.client.post(LOGOUT, {'refresh': token}, format='json').status_code, 200)
        self.assertEqual(self.client.post(LOGOUT, {'refresh': token}, format='json').status_code, 200)


class OptionalPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='egasi', password='Kuchli-Parol-2026', role='fermer')
        self.farm = Farm.objects.create(owner=self.user, name='Baraka', location='Qarshi', farm_type='aralash')
        self.type = AnimalType.objects.create(name='Qoramol')
        for i in range(5):
            AnimalGroup.objects.create(farm=self.farm, animal_type=self.type, breed=f'J{i}', count=1)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_without_limit_returns_plain_list(self):
        data = self.client.get(GROUPS).json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 5)

    def test_with_limit_returns_page(self):
        data = self.client.get(GROUPS, {'limit': 2}).json()
        self.assertEqual(data['count'], 5)
        self.assertEqual(len(data['results']), 2)
        self.assertIsNotNone(data['next'])
        rest = self.client.get(GROUPS, {'limit': 2, 'offset': 4}).json()
        self.assertEqual(len(rest['results']), 1)

    def test_limit_is_capped(self):
        data = self.client.get(GROUPS, {'limit': 100000}).json()
        self.assertEqual(data['count'], 5)  # max_limit ichida bo'lsa ham sahifalangan shaklda keladi
