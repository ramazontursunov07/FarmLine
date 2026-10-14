from datetime import date
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.assistant import actions
from apps.assistant.context import build_context
from apps.assistant.models import PendingAction
from apps.assistant.services import build_system, chat, AIError

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
        with self.assertRaises(AIError):
            chat([{'role': 'user', 'content': 'Salom'}])


from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.farms.models import Farm, Worker
from apps.finance.models import Transaction
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.users.models import User

# from . import actions
# from .models import PendingAction

CHAT_URL = '/api/assistant/chat/'


def confirm_url(pk):
    return f'/api/assistant/actions/{pk}/confirm/'


def cancel_url(pk):
    return f'/api/assistant/actions/{pk}/cancel/'


def make_user(username, role):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def ai_says(text):
    """AI javobini soxtalashtirish (tarmoqsiz)."""
    return patch('apps.assistant.views.chat', return_value=text)


class ExtractActionTests(TestCase):
    def test_plain_answer_has_no_action(self):
        self.assertEqual(actions.extract_action('Salom'), ('Salom', None))

    def test_json_list_is_split_from_text(self):
        text, raw = actions.extract_action('Tushundim.\n[[ACTION]] [{"type": "finance", "amount": 5}]')
        self.assertEqual(text, 'Tushundim.')
        self.assertEqual(raw, [{'type': 'finance', 'amount': 5}])

    def test_code_fence_and_single_object_tolerated(self):
        _, raw = actions.extract_action('Ok\n[[ACTION]] ```json\n{"type": "finance"}\n```')
        self.assertEqual(raw, [{'type': 'finance'}])

    def test_broken_json_never_leaks_to_user(self):
        text, raw = actions.extract_action('Ok\n[[ACTION]] [{"type": "fin')
        self.assertEqual(text, 'Ok')
        self.assertIsNone(raw)


class ActionBase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_user('egasi', 'fermer')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.feed = InventoryItem.objects.create(
            farm=self.farm, item_name='Omuxta yem', item_type='ozuqa', quantity=200, unit='kg',
            low_stock_threshold=100,
        )
        self.api = client_for(self.owner)

    def propose(self, raw_json, who=None):
        with ai_says(f'Tushundim.\n[[ACTION]] {raw_json}'):
            return (who or self.api).post(CHAT_URL, {'message': 'yoz'}, format='json')


class ProposeTests(ActionBase):
    def test_use_feed_creates_card_from_server_data(self):
        # AI «yem» deydi (to'liq nom emas), server haqiqiy mahsulotni topadi
        r = self.propose('[{"type": "inventory_use", "item": "yem", "quantity": 50}]')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn('tasdiqlasangiz', body['answer'].lower())
        card = body['action']
        self.assertEqual(len(card['items']), 1)
        details = ' '.join(card['items'][0]['details'])
        self.assertIn('Omuxta yem', details)
        self.assertIn('50 kg', details)
        self.assertIn('200 → 150', details)
        # taklif bosqichida ombor o'zgarmaydi
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)
        self.assertEqual(InventoryTransaction.objects.count(), 0)
        self.assertEqual(PendingAction.objects.get(pk=card['id']).status, 'kutilmoqda')

    def test_insufficient_stock_gives_no_action(self):
        body = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 500}]').json()
        self.assertNotIn('action', body)
        self.assertIn('yetarli emas', body['answer'])
        self.assertEqual(PendingAction.objects.count(), 0)

    def test_unknown_item_lists_what_exists(self):
        body = self.propose('[{"type": "inventory_use", "item": "bug\'doy", "quantity": 5}]').json()
        self.assertNotIn('action', body)
        self.assertIn('Omuxta yem', body['answer'])

    def test_ambiguous_item_asks_which(self):
        InventoryItem.objects.create(farm=self.farm, item_name='Yem qo\'shimchasi', item_type='ozuqa',
                                     quantity=10, unit='kg')
        body = self.propose('[{"type": "inventory_use", "item": "yem", "quantity": 5}]').json()
        self.assertNotIn('action', body)
        self.assertIn('bir nechta', body['answer'])

    def test_apostrophe_variants_match(self):
        InventoryItem.objects.create(farm=self.farm, item_name="O'rta yem", item_type='ozuqa', quantity=10, unit='kg')
        body = self.propose('[{"type": "inventory_use", "item": "oʻrta yem", "quantity": 5}]').json()
        self.assertIn('action', body)

    def test_finance_expense_with_spaced_number(self):
        body = self.propose(
            '[{"type": "finance", "kind": "chiqim", "category": "ozuqa", "amount": "200 000", '
            '"description": "yem uchun"}]'
        ).json()
        details = ' '.join(body['action']['items'][0]['details'])
        self.assertIn("200 000 so'm", details)
        self.assertIn('Ozuqa', details)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_future_date_and_bad_amount_rejected(self):
        future = (timezone.localdate() + timedelta(days=3)).isoformat()
        raw = ('[{"type": "finance", "kind": "chiqim", "amount": 1000, "date": "%s"},'
               ' {"type": "finance", "kind": "chiqim", "amount": -5}]') % future
        body = self.propose(raw).json()
        self.assertNotIn('action', body)

    def test_unknown_category_falls_back_to_other(self):
        body = self.propose('[{"type": "finance", "kind": "kirim", "category": "lotereya", "amount": 5000}]').json()
        self.assertIn('Boshqa', ' '.join(body['action']['items'][0]['details']))

    def test_garbage_types_ignored_and_limit_enforced(self):
        raw = '[{"type": "delete_farm"}, "salom", 5]'
        body = self.propose(raw).json()
        self.assertNotIn('action', body)
        many = ','.join(['{"type": "finance", "kind": "chiqim", "amount": 1000}'] * 6)
        body = self.propose(f'[{many}]').json()
        self.assertEqual(len(body['action']['items']), actions.MAX_ACTIONS)

    def test_new_proposal_cancels_previous(self):
        first = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 1000}]').json()['action']['id']
        second = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 2000}]').json()['action']['id']
        self.assertEqual(PendingAction.objects.get(pk=first).status, 'bekor')
        self.assertEqual(PendingAction.objects.get(pk=second).status, 'kutilmoqda')
        self.assertEqual(self.api.post(confirm_url(first)).status_code, 400)

    def test_plain_answer_unchanged_and_marker_never_shown(self):
        with ai_says('Bugun yaxshi kun.'):
            self.assertEqual(self.api.post(CHAT_URL, {'message': 'salom'}, format='json').json(),
                             {'answer': 'Bugun yaxshi kun.'})
        body = self.propose('[{"type": "finance", "kind": "chiqim"').json()  # buzuq JSON
        self.assertNotIn('[[ACTION]]', body['answer'])
        self.assertNotIn('action', body)

    def test_admin_gets_no_action_prompt(self):
        self.assertEqual(actions.build_action_prompt(make_user('adm', 'admin')), '')


class ConfirmTests(ActionBase):
    def test_confirm_use_decreases_stock_and_records_user(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 50}]').json()['action']
        r = self.api.post(confirm_url(card['id']))
        self.assertEqual(r.status_code, 200)
        self.assertIn('Omborda qoldi: 150 kg', r.json()['results'][0])
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 150)
        rec = InventoryTransaction.objects.get()
        self.assertEqual((rec.transaction_type, rec.quantity, rec.recorded_by), ('sarf', Decimal('50'), self.owner))
        self.assertIn('AI orqali', rec.note)
        self.assertEqual(PendingAction.objects.get(pk=card['id']).status, 'bajarildi')

    def test_confirm_crossing_threshold_warns_in_result_and_telegram(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 150}]').json()['action']
        with patch('apps.inventory.views.notify_users') as notify:
            r = self.api.post(confirm_url(card['id']))
        self.assertIn('kam qoldi', r.json()['results'][0])
        notify.assert_called_once()  # oddiy API dagi ogohlantirish mantig'i ishladi

    def test_confirm_finance(self):
        card = self.propose(
            '[{"type": "finance", "kind": "chiqim", "category": "ozuqa", "amount": 200000, "description": "yem"}]'
        ).json()['action']
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 200)
        tx = Transaction.objects.get()
        self.assertEqual((tx.transaction_type, tx.category, tx.amount, tx.date, tx.recorded_by),
                         ('chiqim', 'ozuqa', Decimal('200000'), timezone.localdate(), self.owner))

    def test_double_confirm_applies_once(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 50}]').json()['action']
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 200)
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 409)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 150)

    def test_expired_proposal_not_executed(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 50}]').json()['action']
        PendingAction.objects.filter(pk=card['id']).update(created_at=timezone.now() - timedelta(hours=1))
        r = self.api.post(confirm_url(card['id']))
        self.assertEqual(r.status_code, 400)
        self.assertIn("muddati", r.json()['detail'])
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)

    def test_cancel(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 50}]').json()['action']
        self.assertEqual(self.api.post(cancel_url(card['id'])).status_code, 200)
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 400)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)

    def test_stock_changed_after_proposal_is_rechecked(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 150}]').json()['action']
        InventoryItem.objects.filter(pk=self.feed.pk).update(quantity=20)  # orada boshqa kishi sarflab yubordi
        r = self.api.post(confirm_url(card['id']))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(PendingAction.objects.get(pk=card['id']).status, 'kutilmoqda')

    def test_batch_is_all_or_nothing(self):
        raw = ('[{"type": "finance", "kind": "chiqim", "amount": 1000},'
               ' {"type": "inventory_use", "item": "omuxta yem", "quantity": 150}]')
        card = self.propose(raw).json()['action']
        InventoryItem.objects.filter(pk=self.feed.pk).update(quantity=20)
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 400)
        self.assertEqual(Transaction.objects.count(), 0)  # birinchi amal ham yozilmadi

    def test_batch_success(self):
        raw = ('[{"type": "finance", "kind": "chiqim", "amount": 1000},'
               ' {"type": "inventory_use", "item": "omuxta yem", "quantity": 10}]')
        card = self.propose(raw).json()['action']
        r = self.api.post(confirm_url(card['id']))
        self.assertEqual(len(r.json()['results']), 2)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(InventoryTransaction.objects.count(), 1)

    def test_unauthenticated(self):
        self.assertEqual(APIClient().post(confirm_url(1)).status_code, 401)


class PermissionTests(ActionBase):
    def setUp(self):
        super().setUp()
        self.other = make_user('boshqa', 'fermer')
        self.other_farm = Farm.objects.create(owner=self.other, name='Yashirin', location='Buxoro',
                                              farm_type='aralash')
        InventoryItem.objects.create(farm=self.other_farm, item_name='Maxfiy dori', item_type='dori',
                                     quantity=9, unit='dona')
        self.worker = make_user('ishchi1', 'ishchi')
        self.link = Worker.objects.create(user=self.worker, farm=self.farm)

    def test_cannot_touch_other_farms_stock(self):
        body = self.propose('[{"type": "inventory_use", "item": "maxfiy dori", "quantity": 1}]').json()
        self.assertNotIn('action', body)
        self.assertNotIn('Maxfiy', body['answer'])  # begona ombor nomi ham chiqib ketmasin
        self.assertNotIn('Maxfiy', actions.build_action_prompt(self.owner))

    def test_cannot_confirm_someone_elses_proposal(self):
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 5}]').json()['action']
        self.assertEqual(client_for(self.other).post(confirm_url(card['id'])).status_code, 404)
        self.assertEqual(client_for(self.other).post(cancel_url(card['id'])).status_code, 404)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)

    def test_worker_can_use_stock_but_not_finance_by_default(self):
        w = client_for(self.worker)
        card = self.propose('[{"type": "inventory_use", "item": "omuxta yem", "quantity": 30}]', w).json()['action']
        self.assertEqual(w.post(confirm_url(card['id'])).status_code, 200)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 170)
        rec = InventoryTransaction.objects.get()
        self.assertEqual(rec.recorded_by, self.worker)

        body = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 5000}]', w).json()
        self.assertNotIn('action', body)
        self.assertIn('huquqi yo', body['answer'])
        self.assertNotIn('finance', actions.build_action_prompt(self.worker).split('Harakat turlari:')[1]
                         .split('Bugungi sana')[0])

    def test_worker_with_finance_permission(self):
        Worker.objects.filter(pk=self.link.pk).update(can_view_finance=True)
        w = client_for(self.worker)
        card = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 5000}]', w).json()['action']
        self.assertEqual(w.post(confirm_url(card['id'])).status_code, 200)
        self.assertEqual(Transaction.objects.get().recorded_by, self.worker)

    def test_permission_revoked_between_propose_and_confirm(self):
        Worker.objects.filter(pk=self.link.pk).update(can_view_finance=True)
        w = client_for(self.worker)
        card = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 5000}]', w).json()['action']
        Worker.objects.filter(pk=self.link.pk).update(can_view_finance=False)
        self.assertEqual(w.post(confirm_url(card['id'])).status_code, 403)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_multiple_farms_require_farm_name(self):
        second = Farm.objects.create(owner=self.owner, name='Nur', location='Shahrisabz', farm_type='aralash')
        body = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 5000}]').json()
        self.assertNotIn('action', body)
        self.assertIn('Qaysi fermaga', body['answer'])
        body = self.propose('[{"type": "finance", "kind": "chiqim", "amount": 5000, "farm": "nur"}]').json()
        self.assertIn('Nur', ' '.join(body['action']['items'][0]['details']))
        self.assertEqual(Farm.objects.filter(pk=second.pk).count(), 1)


class InventoryPurchaseAITests(ActionBase):
    """AI omborga kirim yozganda narxni so'raydi; tasdiqlangach moliyada chiqim yoziladi."""

    ADD = '[{"type": "inventory_add", "item": "omuxta yem", "quantity": 50%s}]'

    def add(self, amount=None, who=None):
        extra = '' if amount is None else f', "amount": {amount}'
        return self.propose(self.ADD % extra, who)

    def make_worker(self, can_view_finance=False):
        worker = make_user('ishchi2', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm, can_view_finance=can_view_finance)
        return worker, client_for(worker)

    def test_add_without_price_asks_for_it(self):
        body = self.add().json()
        self.assertNotIn('action', body)
        self.assertIn("necha so'mga", body['answer'])
        self.assertNotIn('Buni bajara olmayman', body['answer'])
        self.assertEqual(PendingAction.objects.count(), 0)

    def test_add_with_price_creates_expense_on_confirm(self):
        card = self.add(450000).json()['action']
        self.assertIn("450 000 so'm", ' '.join(card['items'][0]['details']))

        r = self.api.post(confirm_url(card['id']))
        self.assertEqual(r.status_code, 200)
        self.assertIn('Moliyada chiqim', r.json()['results'][0])
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 250)
        tx = Transaction.objects.get()
        self.assertEqual((tx.transaction_type, tx.category, tx.amount), ('chiqim', 'ozuqa', Decimal('450000')))
        self.assertEqual(tx.recorded_by, self.owner)

    def test_zero_price_means_no_expense(self):
        card = self.add(0).json()['action']
        self.assertIn('kiritilmadi', ' '.join(card['items'][0]['details']))
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 200)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 250)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_negative_price_rejected(self):
        body = self.add(-5).json()
        self.assertNotIn('action', body)
        self.assertIn('narx aniq emas', body['answer'])

    def test_worker_without_finance_right_is_not_asked_for_price(self):
        _, w = self.make_worker()
        card = self.add(who=w).json()['action']
        self.assertEqual(w.post(confirm_url(card['id'])).status_code, 200)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 250)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_worker_without_finance_right_cannot_give_price(self):
        _, w = self.make_worker()
        body = self.add(450000, who=w).json()
        self.assertNotIn('action', body)
        self.assertIn('moliya huquqi', body['answer'])

    def test_worker_with_finance_right_is_asked_and_pays(self):
        worker, w = self.make_worker(can_view_finance=True)
        self.assertIn("necha so'mga", self.add(who=w).json()['answer'])
        card = self.add(120000, who=w).json()['action']
        self.assertEqual(w.post(confirm_url(card['id'])).status_code, 200)
        self.assertEqual(Transaction.objects.get().recorded_by, worker)

    def test_prompt_asks_for_price_only_if_user_can_pay(self):
        worker, _ = self.make_worker()
        self.assertIn("Necha so'mga oldingiz", actions.build_action_prompt(self.owner))
        self.assertNotIn("Necha so'mga oldingiz", actions.build_action_prompt(worker))


class DuplicatePurchaseTests(ActionBase):
    """AI bitta xarid uchun ham «inventory_add» (narxi bilan), ham «finance» chiqim yozsa, balans ikki marta kamaymasin."""

    RAW = (
        '[{"type": "inventory_add", "item": "omuxta yem", "quantity": 1000, "amount": 15000000},'
        ' {"type": "finance", "kind": "chiqim", "category": "ozuqa", "amount": %s, "description": "yem sotib olindi"}]'
    )

    def test_duplicate_finance_expense_is_dropped(self):
        body = self.propose(self.RAW % 15000000).json()
        self.assertEqual([i['title'] for i in body['action']['items']], ['📥 Omborga kirim'])
        self.assertIn('Takror', body['answer'])

    def test_confirm_writes_only_one_expense(self):
        card = self.propose(self.RAW % 15000000).json()['action']
        self.assertEqual(self.api.post(confirm_url(card['id'])).status_code, 200)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_different_amount_is_kept(self):
        body = self.propose(self.RAW % 500000).json()
        self.assertEqual(len(body['action']['items']), 2)

    def test_warns_if_same_amount_was_just_recorded_via_inventory(self):
        card = self.propose('[{"type": "inventory_add", "item": "omuxta yem", "quantity": 10, "amount": 700000}]'
                            ).json()['action']
        self.api.post(confirm_url(card['id']))
        body = self.propose('[{"type": "finance", "kind": "chiqim", "category": "ozuqa", "amount": 700000}]').json()
        self.assertIn('Diqqat', ' '.join(body['action']['items'][0]['details']))
