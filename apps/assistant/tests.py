from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem
from apps.users.models import User

from .context import build_context
from .services import build_system

CHAT_URL = '/api/assistant/chat/'


def make_user(username, role):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


class AssistantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_user('fermer1', 'fermer')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.owner)

    def test_requires_login(self):
        self.assertEqual(APIClient().post(CHAT_URL, {'message': 'salom'}, format='json').status_code, 401)

    def test_empty_and_long_message_rejected(self):
        self.assertEqual(self.client_api.post(CHAT_URL, {'message': '  '}, format='json').status_code, 400)
        self.assertEqual(self.client_api.post(CHAT_URL, {'message': 'a' * 1001}, format='json').status_code, 400)

    @patch('apps.assistant.views.chat', return_value='Yaxshi')
    def test_answer_and_context_passed(self, mocked):
        Transaction.objects.create(
            farm=self.farm, transaction_type='kirim', category='sotuv', amount=500000,
            date=date.today(), recorded_by=self.owner,
        )
        r = self.client_api.post(CHAT_URL, {'message': 'Bugun qanday?'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['answer'], 'Yaxshi')
        messages, context = mocked.call_args.args
        self.assertEqual(messages[-1], {'role': 'user', 'content': 'Bugun qanday?'})
        self.assertIn('Baraka', context)

    @patch('apps.assistant.views.chat', side_effect=RuntimeError('tarmoq uzildi'))
    def test_unexpected_error_hidden_from_user(self, _):
        r = self.client_api.post(CHAT_URL, {'message': 'salom'}, format='json')
        self.assertEqual(r.status_code, 502)
        self.assertNotIn('tarmoq', r.json()['detail'])

    @patch('apps.assistant.views.chat', return_value='ok')
    def test_rate_limit(self, _):
        with patch('rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES', {'assistant': '2/hour'}):
            codes = [self.client_api.post(CHAT_URL, {'message': 'salom'}, format='json').status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class ContextPrivacyTests(TestCase):
    def setUp(self):
        self.owner = make_user('egasi', 'fermer')
        self.other = make_user('boshqa', 'fermer')
        self.farm = Farm.objects.create(owner=self.owner, name='Ozoda', location='Toshkent', farm_type='chorvachilik')
        self.other_farm = Farm.objects.create(owner=self.other, name='Yashirin', location='Buxoro', farm_type='aralash')

    def test_owner_sees_only_own_farms(self):
        ctx = build_context(self.owner)
        self.assertIn('Ozoda', ctx)
        self.assertNotIn('Yashirin', ctx)

    def test_low_stock_in_context(self):
        InventoryItem.objects.create(farm=self.farm, item_name='Omuxta yem', item_type='ozuqa', quantity=3, unit='kg',
                                     low_stock_threshold=10)
        self.assertIn('Omuxta yem', build_context(self.owner))

    def test_worker_gets_no_finance(self):
        worker = make_user('ishchi1', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        Transaction.objects.create(
            farm=self.farm, transaction_type='kirim', category='sotuv', amount=123456,
            date=date.today(), recorded_by=self.owner,
        )
        ctx = build_context(worker)
        self.assertNotIn('123 456', ctx)
        self.assertNotIn('Ozoda', ctx.split('\n')[0] if ctx else '')

    def test_month_totals_and_loss(self):
        today = date(2026, 10, 13)
        Transaction.objects.create(farm=self.farm, transaction_type='kirim', category='sotuv',
                                   amount=1000000, date=date(2026, 10, 2), recorded_by=self.owner)
        Transaction.objects.create(farm=self.farm, transaction_type='chiqim', category='ozuqa',
                                   amount=1500000, date=date(2026, 10, 5), recorded_by=self.owner)
        Transaction.objects.create(farm=self.farm, transaction_type='chiqim', category='ozuqa',
                                   amount=700000, date=date(2026, 9, 20), recorded_by=self.owner)
        ctx = build_context(self.owner, today)
        self.assertIn('Shu oy', ctx)
        self.assertIn('zarar 500 000', ctx)
        self.assertIn("O'tgan oy: kirim 0, chiqim 700 000", ctx)

    def test_animals_in_context(self):
        from apps.animals.models import AnimalGroup, AnimalType
        t = AnimalType.objects.create(name='Sigir')
        AnimalGroup.objects.create(farm=self.farm, animal_type=t, count=100)
        self.assertIn('Sigir — 100 ta', build_context(self.owner))

    def test_admin_gets_empty_context(self):
        self.assertEqual(build_context(make_user('adm', 'admin')), '')

    def test_system_prompt(self):
        self.assertNotIn('ferma holati', build_system(''))
        self.assertIn('Ozoda', build_system('Ozoda'))


class ProviderTests(TestCase):
    """AI_PROVIDER=openai (Groq/OpenRouter): tarmoqsiz, requests.post soxtalashtirilgan."""

    @staticmethod
    def _resp(status, body):
        class R:
            status_code = status
            text = str(body)

            @staticmethod
            def json():
                return body

        return R()

    @override_settings(AI_PROVIDER='openai', AI_API_KEY='k', AI_BASE_URL='https://x.test/v1', AI_MODEL=None)
    def test_openai_success_and_payload(self):
        from .services import chat
        ok = self._resp(200, {'choices': [{'message': {'content': ' Salom! '}}]})
        with patch('apps.assistant.services.requests.post', return_value=ok) as post:
            answer = chat([{'role': 'user', 'content': 'Salom'}], context='Ozoda ferma')
        self.assertEqual(answer, 'Salom!')
        url = post.call_args.args[0]
        body = post.call_args.kwargs['json']
        self.assertEqual(url, 'https://x.test/v1/chat/completions')
        self.assertEqual(body['messages'][0]['role'], 'system')
        self.assertIn('Ozoda ferma', body['messages'][0]['content'])
        self.assertEqual(body['messages'][-1], {'role': 'user', 'content': 'Salom'})
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer k')

    @override_settings(AI_PROVIDER='openai', AI_API_KEY='k')
    def test_openai_rate_limit_becomes_ai_error(self):
        from .services import AIError, chat
        with patch('apps.assistant.services.requests.post', return_value=self._resp(429, {'error': 'limit'})):
            with self.assertRaises(AIError) as ctx:
                chat([{'role': 'user', 'content': 'Salom'}])
        self.assertEqual(ctx.exception.code, 429)

    @override_settings(AI_PROVIDER='openai', AI_API_KEY='k')
    def test_view_shows_limit_message_for_429(self):
        owner = make_user('f2', 'fermer')
        c = APIClient()
        c.force_authenticate(owner)
        with patch('apps.assistant.services.requests.post', return_value=self._resp(429, {})):
            r = c.post(CHAT_URL, {'message': 'salom'}, format='json')
        self.assertEqual(r.status_code, 502)
        self.assertIn('limit', r.json()['detail'].lower())

    @override_settings(AI_PROVIDER='nomalum')
    def test_unknown_provider(self):
        from .services import AIError, chat
        with self.assertRaises(AIError):
            chat([{'role': 'user', 'content': 'Salom'}])
