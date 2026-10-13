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

from apps.assistant import actions
from apps.assistant.models import PendingAction

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
