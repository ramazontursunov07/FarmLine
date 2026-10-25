from unittest.mock import patch

import requests
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.farms.models import Farm, Worker
from apps.users.models import User
from apps.weather import services

URL = '/api/weather/'

GEO = {'results': [{'latitude': 38.86, 'longitude': 65.79, 'name': 'Qarshi'}]}
FORECAST = {
    'current': {'temperature_2m': 21.46, 'relative_humidity_2m': 40, 'wind_speed_10m': 9.0, 'weather_code': 1},
    'daily': {
        'time': ['2026-10-17', '2026-10-18', '2026-10-19'],
        'weather_code': [0, 63, 95],
        'temperature_2m_max': [24.0, 36.2, 18.0],
        'temperature_2m_min': [8.0, -1.5, 5.0],
        'precipitation_sum': [0, 12.4, 0.2],
        'precipitation_probability_max': [0, 90, 20],
        'wind_speed_10m_max': [12, 45.5, 10],
    },
}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def fake_get(url, params=None, timeout=None):
    return FakeResponse(GEO if url == services.GEOCODE_URL else FORECAST)


def make_user(username, role='fermer'):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class WeatherTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_user('egasi')
        self.other = make_user('boshqa')
        self.worker = make_user('ishchi1', role='ishchi')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi, Qashqadaryo',
                                        farm_type='chorvachilik')
        Worker.objects.create(user=self.worker, farm=self.farm)

    def test_forecast_and_alerts(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', side_effect=fake_get):
            r = self.client.get(URL, {'farm': self.farm.id})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d['status'], 'ok')
        self.assertEqual(d['current']['temp'], 21.5)
        self.assertEqual(len(d['days']), 3)
        self.assertEqual(d['days'][1]['text'], "Yomg'ir")
        types = {a['type'] for a in d['alerts']}
        self.assertEqual(types, {'frost', 'heat', 'wind', 'rain'})
        self.farm.refresh_from_db()
        self.assertEqual(self.farm.latitude, 38.86)

    def test_worker_can_see_other_cannot(self):
        with patch('apps.weather.services.requests.get', side_effect=fake_get):
            self.client.force_authenticate(self.worker)
            self.assertEqual(self.client.get(URL, {'farm': self.farm.id}).status_code, 200)
            self.client.force_authenticate(self.other)
            self.assertEqual(self.client.get(URL, {'farm': self.farm.id}).status_code, 404)

    def test_requires_login_and_farm_param(self):
        self.assertEqual(self.client.get(URL, {'farm': self.farm.id}).status_code, 401)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(URL).status_code, 400)

    def test_location_not_found(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', return_value=FakeResponse({})):
            r = self.client.get(URL, {'farm': self.farm.id})
        self.assertEqual(r.json()['status'], 'no_location')

    def test_service_down(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', side_effect=requests.ConnectionError()):
            r = self.client.get(URL, {'farm': self.farm.id})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'unavailable')

    def test_service_down_shows_last_good_forecast(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', side_effect=fake_get):
            self.assertEqual(self.client.get(URL, {'farm': self.farm.id}).json()['status'], 'ok')
        # Yangi natija muddati o'tdi, lekin eski nusxa qoldi
        farm = Farm.objects.get(pk=self.farm.pk)
        cache.delete(f'weather:{round(farm.latitude, 2)}:{round(farm.longitude, 2)}')
        with patch('apps.weather.services.requests.get', side_effect=requests.ConnectionError()):
            r = self.client.get(URL, {'farm': self.farm.id})
        body = r.json()
        self.assertEqual((r.status_code, body['status']), (200, 'ok'))
        self.assertTrue(body['stale'])
        self.assertTrue(body['updated_at'])
        self.assertEqual(len(body['days']), 3)

    def test_fresh_forecast_is_not_marked_stale(self):
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', side_effect=fake_get):
            body = self.client.get(URL, {'farm': self.farm.id}).json()
        self.assertNotIn('stale', body)

    def test_geocode_falls_back_to_parts_and_caches_coords(self):
        calls = []

        def get(url, params=None, timeout=None):
            if url == services.GEOCODE_URL:
                calls.append(params['name'])
                return FakeResponse(GEO if params['name'] == 'Qashqadaryo' else {})
            return FakeResponse(FORECAST)

        self.farm.location = 'Nomalum qishloq, Qashqadaryo'
        self.farm.save()
        self.client.force_authenticate(self.owner)
        with patch('apps.weather.services.requests.get', side_effect=get):
            self.client.get(URL, {'farm': self.farm.id})
            self.client.get(URL, {'farm': self.farm.id})
        self.assertEqual(calls, ['Nomalum qishloq, Qashqadaryo', 'Nomalum qishloq', 'Qashqadaryo'])

    def test_changing_location_resets_coords(self):
        self.farm.latitude, self.farm.longitude = 1.0, 2.0
        self.farm.save()
        self.client.force_authenticate(self.owner)
        r = self.client.patch(f'/api/farms/{self.farm.id}/', {'location': 'Samarqand'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.farm.refresh_from_db()
        self.assertIsNone(self.farm.latitude)
