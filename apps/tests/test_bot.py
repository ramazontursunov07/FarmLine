"""Telegram bot: matn/ovozdan sut, ombor va kirim-chiqim yozish (AI taklif qiladi, tasdiqlagach yoziladi)."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.animals.models import Animal, AnimalGroup, AnimalType, MilkRecord
from apps.assistant import actions, bot_service, speech
from apps.assistant.models import PendingAction
from apps.assistant.services import AIError
from apps.farms.models import Farm, Worker
from apps.inventory.models import InventoryItem, InventoryTransaction
from apps.users.models import User


def make_user(username, role='fermer', **extra):
    return User.objects.create_user(username=username, password='Kuchli-Parol-2026', role=role, **extra)


def ai_says(text):
    return patch('apps.assistant.views.chat', return_value=text)


class BotBase(TestCase):
    def setUp(self):
        # Ob-havo uchun haqiqiy internetga chiqilmasin
        patcher = patch('apps.assistant.bot_service.build_context', return_value='')
        patcher.start()
        self.addCleanup(patcher.stop)
        bot_service._history.clear()
        bot_service._calls.clear()
        self.owner = make_user('egasi', telegram_chat_id='1001')
        self.farm = Farm.objects.create(owner=self.owner, name='Baraka', location='Qarshi', farm_type='aralash')
        self.group = AnimalGroup.objects.create(
            farm=self.farm, animal_type=AnimalType.objects.create(name='Qoramol'), count=4)
        self.today = timezone.localdate()
        old = self.today - timedelta(days=1500)
        self.cow14 = Animal.objects.create(farm=self.farm, group=self.group, tag_number='14', name='Oqqosh',
                                           birth_date=old)
        self.cow15 = Animal.objects.create(farm=self.farm, group=self.group, tag_number='15', birth_date=old)
        self.bull = Animal.objects.create(farm=self.farm, group=self.group, tag_number='7', sex='erkak',
                                          birth_date=old)
        self.feed = InventoryItem.objects.create(
            farm=self.farm, item_name='Omuxta yem', item_type='ozuqa', quantity=200, unit='kg',
            low_stock_threshold=10)

    def milk(self, entries, **extra):
        raw = {'type': 'milk', 'entries': entries}
        raw.update(extra)
        return actions.create_proposal(self.owner, [raw])


class MilkActionTests(BotBase):
    def test_card_from_server_data(self):
        pending, problems = self.milk([{'animal': '14', 'liters': 12}, {'animal': '15', 'liters': 9.5}],
                                      session='ertalab')
        self.assertIsNotNone(pending)
        self.assertEqual(problems, [])
        details = ' | '.join(pending.actions[0]['details'])
        self.assertIn('№14 · Oqqosh: 12 l', details)
        self.assertIn('№15: 9.5 l', details)
        self.assertIn('Jami: 21.5 l (2 ta sigir)', details)
        self.assertIn('Ertalab', details)
        self.assertEqual(MilkRecord.objects.count(), 0)  # taklif bosqichida hech narsa yozilmaydi

    def test_confirm_writes_each_cow(self):
        pending, _ = self.milk([{'animal': '14', 'liters': 12}, {'animal': '15', 'liters': 9.5}], session='kechqurun')
        done, text = bot_service.confirm_action(self.owner, pending.pk)
        self.assertTrue(done, text)
        self.assertIn('2 ta sigir, jami 21.5 l', text)
        rec = MilkRecord.objects.get(animal=self.cow14)
        self.assertEqual((rec.liters, rec.session, rec.date, rec.recorded_by), (
            Decimal('12.0'), 'kechqurun', self.today, self.owner))
        self.assertEqual(MilkRecord.objects.count(), 2)

    def test_tag_written_in_different_ways(self):
        for ref in ('№14', '14-sigir', 'sigir 14', 14, 'oqqosh'):
            pending, problems = self.milk([{'animal': ref, 'liters': 5}])
            self.assertIsNotNone(pending, (ref, problems))
            self.assertIn('№14', ' '.join(pending.actions[0]['details']))

    def test_session_defaults_to_whole_day(self):
        pending, _ = self.milk([{'animal': '14', 'liters': 5}])
        self.assertEqual(pending.actions[0]['data']['records'][0]['session'], 'kun')

    def test_unknown_cow_and_bull_rejected(self):
        pending, problems = self.milk([{'animal': '99', 'liters': 5}])
        self.assertIsNone(pending)
        self.assertIn('99', problems[0])
        pending, problems = self.milk([{'animal': '7', 'liters': 5}])  # buqa
        self.assertIsNone(pending)

    def test_bad_liters(self):
        for liters in (0, -3, 'ko\'p', 101, 12.25):
            pending, problems = self.milk([{'animal': '14', 'liters': liters}])
            self.assertIsNone(pending, liters)
            self.assertTrue(problems, liters)

    def test_partial_proposal_keeps_valid_rows_and_reports_the_rest(self):
        pending, problems = self.milk([{'animal': '14', 'liters': 12}, {'animal': '99', 'liters': 5}])
        self.assertIsNotNone(pending)
        self.assertEqual(len(pending.actions[0]['data']['records']), 1)
        self.assertEqual(len(problems), 1)

    def test_same_cow_twice_in_one_message(self):
        pending, problems = self.milk([{'animal': '14', 'liters': 5}, {'animal': '14', 'liters': 6}])
        self.assertEqual(len(pending.actions[0]['data']['records']), 1)
        self.assertIn('ikki marta', problems[0])

    def test_already_recorded_is_explained(self):
        MilkRecord.objects.create(animal=self.cow14, date=self.today, session='ertalab', liters=Decimal('8'),
                                  recorded_by=self.owner)
        pending, problems = self.milk([{'animal': '14', 'liters': 5}], session='ertalab')
        self.assertIsNone(pending)
        self.assertIn('allaqachon', problems[0])
        pending, problems = self.milk([{'animal': '14', 'liters': 5}], session='kun')  # ertalab bor: aralashmaydi
        self.assertIsNone(pending)

    def test_future_date_rejected(self):
        pending, problems = self.milk([{'animal': '14', 'liters': 5}], date=str(self.today + timedelta(days=1)))
        self.assertIsNone(pending)

    def test_total_without_cows_asks_which_cows(self):
        pending, problems = actions.create_proposal(self.owner, [{'type': 'milk', 'liters': 85}])
        self.assertIsNone(pending)
        self.assertTrue(all(isinstance(p, actions.Question) for p in problems))
        self.assertIn('Qaysi sigirdan', problems[0])

    def test_stale_proposal_is_rechecked_on_confirm(self):
        pending, _ = self.milk([{'animal': '14', 'liters': 5}], session='ertalab')
        MilkRecord.objects.create(animal=self.cow14, date=self.today, session='ertalab', liters=Decimal('8'),
                                  recorded_by=self.owner)
        done, text = bot_service.confirm_action(self.owner, pending.pk)
        self.assertFalse(done)
        self.assertEqual(MilkRecord.objects.count(), 1)

    def test_worker_can_record_but_stranger_cannot_see_cows(self):
        worker = make_user('ishchi', 'ishchi')
        Worker.objects.create(user=worker, farm=self.farm)
        pending, _ = actions.create_proposal(worker, [{'type': 'milk', 'entries': [{'animal': '14', 'liters': 4}]}])
        done, text = bot_service.confirm_action(worker, pending.pk)
        self.assertTrue(done, text)
        self.assertEqual(MilkRecord.objects.get().recorded_by, worker)

        stranger = make_user('begona')
        pending, problems = actions.create_proposal(stranger,
                                                    [{'type': 'milk', 'entries': [{'animal': '15', 'liters': 4}]}])
        self.assertIsNone(pending)

    def test_prompt_lists_cows_and_explains_totals(self):
        prompt = actions.build_action_prompt(self.owner)
        self.assertIn('"type": "milk"', prompt)
        self.assertIn('№14 — Oqqosh — Baraka', prompt)
        self.assertNotIn('№7', prompt)  # buqa ro'yxatda yo'q
        self.assertIn('85 litr', prompt)
        self.assertIn('qop', prompt)


class BotServiceTests(BotBase):
    def test_get_user(self):
        self.assertEqual(bot_service.get_user('1001'), self.owner)
        self.assertIsNone(bot_service.get_user('555'))
        make_user('admin1', 'admin', telegram_chat_id='999')
        self.assertIsNone(bot_service.get_user('999'))

    def test_plain_question_answered_without_card(self):
        with ai_says('Sut narxi 5000 so\'m.'):
            reply, pending_id = bot_service.ask(self.owner, 'Sut qancha?')
        self.assertEqual((reply, pending_id), ("Sut narxi 5000 so'm.", None))

    def test_text_message_becomes_confirmable_card(self):
        with ai_says('Tushundim.\n[[ACTION]] [{"type": "inventory_use", "item": "yem", "quantity": 25}]'):
            reply, pending_id = bot_service.ask(self.owner, '25 kg yem ishlatdim')
        self.assertTrue(reply.startswith('Quyidagini bajaraymi?'))
        self.assertIn('Omuxta yem', reply)
        self.assertIn('200 → 175', reply)
        self.assertNotIn('[[ACTION]]', reply)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)  # tasdiqlanmaguncha o'zgarmaydi

        done, text = bot_service.confirm_action(self.owner, pending_id)
        self.assertTrue(done, text)
        self.assertIn('Omborda qoldi: 175 kg', text)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 175)
        self.assertEqual(InventoryTransaction.objects.get().recorded_by, self.owner)

    def test_double_confirm_applies_once(self):
        with ai_says('[[ACTION]] [{"type": "inventory_use", "item": "yem", "quantity": 25}]'):
            _, pending_id = bot_service.ask(self.owner, '25 kg yem')
        self.assertTrue(bot_service.confirm_action(self.owner, pending_id)[0])
        done, text = bot_service.confirm_action(self.owner, pending_id)
        self.assertFalse(done)
        self.assertIn('allaqachon', text)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 175)

    def test_cannot_confirm_or_cancel_someone_elses_card(self):
        with ai_says('[[ACTION]] [{"type": "inventory_use", "item": "yem", "quantity": 25}]'):
            _, pending_id = bot_service.ask(self.owner, '25 kg yem')
        other = make_user('boshqa')
        self.assertEqual(bot_service.confirm_action(other, pending_id), (False, 'Amal topilmadi.'))
        bot_service.cancel_action(other, pending_id)
        self.assertEqual(PendingAction.objects.get(pk=pending_id).status, 'kutilmoqda')

    def test_cancel_writes_nothing(self):
        with ai_says('[[ACTION]] [{"type": "inventory_use", "item": "yem", "quantity": 25}]'):
            _, pending_id = bot_service.ask(self.owner, '25 kg yem')
        self.assertIn('Bekor qilindi', bot_service.cancel_action(self.owner, pending_id))
        done, text = bot_service.confirm_action(self.owner, pending_id)
        self.assertFalse(done)
        self.feed.refresh_from_db()
        self.assertEqual(self.feed.quantity, 200)

    def test_confirm_failure_is_explained_and_rolled_back(self):
        with ai_says('[[ACTION]] [{"type": "inventory_use", "item": "yem", "quantity": 150}]'):
            _, pending_id = bot_service.ask(self.owner, '150 kg yem')
        InventoryItem.objects.filter(pk=self.feed.pk).update(quantity=100)  # taklifdan keyin zaxira kamaydi
        done, text = bot_service.confirm_action(self.owner, pending_id)
        self.assertFalse(done)
        self.assertIn('Bajarib bo\'lmadi', text)
        self.assertEqual(InventoryTransaction.objects.count(), 0)
        self.assertEqual(PendingAction.objects.get(pk=pending_id).status, 'kutilmoqda')

    def test_follow_up_answer_sees_previous_messages(self):
        with ai_says('Necha so\'mga oldingiz?') as mocked:
            bot_service.ask(self.owner, '300 kg yem keldi')
        with ai_says('Yaxshi') as mocked:
            bot_service.ask(self.owner, '2 million')
        messages = mocked.call_args.args[0]
        self.assertEqual([m['role'] for m in messages], ['user', 'assistant', 'user'])
        self.assertEqual(messages[0]['content'], '300 kg yem keldi')

    def test_new_conversation_forgets(self):
        with ai_says('Salom'):
            bot_service.ask(self.owner, 'salom')
        bot_service.reset_history(self.owner.pk)
        with ai_says('Yaxshi') as mocked:
            bot_service.ask(self.owner, 'yana')
        self.assertEqual(len(mocked.call_args.args[0]), 1)

    @override_settings(BOT_AI_PER_HOUR=2)
    def test_rate_limit(self):
        with ai_says('ok') as mocked:
            bot_service.ask(self.owner, 'bir')
            bot_service.ask(self.owner, 'ikki')
            reply, _ = bot_service.ask(self.owner, 'uch')
        self.assertEqual(reply, bot_service.RATE_ERROR)
        self.assertEqual(mocked.call_count, 2)

    def test_empty_and_long_text(self):
        with ai_says('ok') as mocked:
            self.assertEqual(bot_service.ask(self.owner, '   ')[1], None)
            reply, _ = bot_service.ask(self.owner, 'a' * 1001)
        self.assertIn('juda uzun', reply)
        mocked.assert_not_called()

    def test_ai_errors_are_friendly(self):
        with patch('apps.assistant.views.chat', side_effect=AIError('secret key leaked', code=429)):
            self.assertEqual(bot_service.ask(self.owner, 'salom')[0], bot_service.LIMIT_ERROR)
        with patch('apps.assistant.views.chat', side_effect=AIError('secret key leaked')):
            self.assertEqual(bot_service.ask(self.owner, 'salom')[0], bot_service.GENERIC_ERROR)
        with patch('apps.assistant.views.chat', side_effect=RuntimeError('tarmoq uzildi')):
            reply = bot_service.ask(self.owner, 'salom')[0]
        self.assertEqual(reply, bot_service.GENERIC_ERROR)
        self.assertNotIn('secret', reply)

    def test_milk_by_text_end_to_end(self):
        raw = '[{"type": "milk", "entries": [{"animal": "14", "liters": 12}, {"animal": "15", "liters": 9}]}]'
        with ai_says(f'Tushundim.\n[[ACTION]] {raw}'):
            reply, pending_id = bot_service.ask(self.owner, '14-sigir 12 litr, 15-sigir 9 litr sut berdi')
        self.assertIn('Jami: 21 l (2 ta sigir)', reply)
        self.assertTrue(bot_service.confirm_action(self.owner, pending_id)[0])
        self.assertEqual(MilkRecord.objects.count(), 2)

    def test_partial_card_shows_what_was_skipped(self):
        raw = '[{"type": "milk", "entries": [{"animal": "14", "liters": 12}, {"animal": "99", "liters": 9}]}]'
        with ai_says(f'[[ACTION]] {raw}'):
            reply, pending_id = bot_service.ask(self.owner, 'sut')
        self.assertIsNotNone(pending_id)
        self.assertIn('Bajarib bo\'lmaydiganlari', reply)
        self.assertIn('99', reply)

    def test_error_text_flattens_nested_errors(self):
        exc = ValidationError({'liters': ['Juda ko\'p'], 'x': {'y': ['Xato']}})
        self.assertEqual(bot_service.error_text(exc), "Juda ko'p; Xato")


class SpeechTests(TestCase):
    class FakeResponse:
        def __init__(self, status=200, payload=None, text=''):
            self.status_code, self._payload, self.text = status, payload, text

        def json(self):
            return self._payload

    @override_settings(STT_PROVIDER='openai', AI_API_KEY='k', AI_BASE_URL='http://stt.test/v1', STT_MODEL=None)
    def test_openai_compatible_transcription(self):
        resp = self.FakeResponse(payload={'text': ' 14-sigir 12 litr sut '})
        with patch('apps.assistant.speech.requests.post', return_value=resp) as post:
            text = speech.transcribe(b'OggS-data')
        self.assertEqual(text, '14-sigir 12 litr sut')
        url = post.call_args.args[0]
        self.assertEqual(url, 'http://stt.test/v1/audio/transcriptions')
        self.assertEqual(post.call_args.kwargs['data']['language'], 'uz')
        self.assertEqual(post.call_args.kwargs['data']['model'], 'whisper-large-v3')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer k')

    @override_settings(STT_PROVIDER='openai', AI_API_KEY='k', AI_BASE_URL='http://stt.test/v1')
    def test_provider_errors_become_ai_error(self):
        with patch('apps.assistant.speech.requests.post', return_value=self.FakeResponse(429, text='limit')):
            with self.assertRaises(AIError) as ctx:
                speech.transcribe(b'x')
        self.assertEqual(ctx.exception.code, 429)
        with patch('apps.assistant.speech.requests.post', return_value=self.FakeResponse(payload={'text': '  '})):
            with self.assertRaises(AIError):
                speech.transcribe(b'x')

    @override_settings(STT_PROVIDER='gemini')
    def test_gemini_branch_used_and_text_cleaned(self):
        with patch('apps.assistant.speech._transcribe_gemini', return_value=' "Bugun 85 litr" ') as fake:
            self.assertEqual(speech.transcribe(b'x'), 'Bugun 85 litr')
        self.assertEqual(fake.call_args.args[1], 'audio/ogg')

    @override_settings(STT_PROVIDER=None, AI_PROVIDER='gemini')
    def test_follows_ai_provider_by_default(self):
        with patch('apps.assistant.speech._transcribe_gemini', return_value='salom'):
            self.assertEqual(speech.transcribe(b'x'), 'salom')

    def test_empty_and_huge_audio_rejected(self):
        with self.assertRaises(AIError):
            speech.transcribe(b'')
        with self.assertRaises(AIError):
            speech.transcribe(b'x' * (speech.MAX_AUDIO_BYTES + 1))

    @override_settings(STT_PROVIDER='nomalum')
    def test_unknown_provider(self):
        with self.assertRaises(AIError):
            speech.transcribe(b'x')

    def test_voice_to_text_never_raises(self):
        with patch('apps.assistant.speech.transcribe', side_effect=AIError('xato')):
            self.assertIsNone(bot_service.voice_to_text(b'x'))
        with patch('apps.assistant.speech.transcribe', side_effect=RuntimeError('kutilmagan')):
            self.assertIsNone(bot_service.voice_to_text(b'x'))
        with patch('apps.assistant.speech.transcribe', return_value='salom'):
            self.assertEqual(bot_service.voice_to_text(b'x'), 'salom')
