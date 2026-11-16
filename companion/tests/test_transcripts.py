"""Offline recognition: actual packaged factory/SessionDB, scripted provider only."""
import asyncio
import base64
import copy
import json
import time
import unittest
from unittest.mock import patch

import test_installed_engine as installed
from hermes_native_engine.engine import NativeLoop
from hermes_native_engine.pcm import resample_pcm16_16k_to_24k

WORDS = 'Synthetic recognition: blue lantern.'


def recognition(text=WORDS, item='audio_exact', index=0, failed=False):
    return {'type': 'conversation.item.input_audio_transcription.' + ('failed' if failed else 'completed'),
            'item_id': item, 'content_index': index, 'transcript': text}


class RecognitionWire(installed.ProviderWire):
    def __init__(self, mode='normal', events=None):
        super().__init__()
        self.mode = mode
        self.events = events if events is not None else [recognition()]
        self.finishing = asyncio.Event()

    async def send_json(self, event):
        typ = event['type']
        if self.mode == 'ack_flood' and typ in ('session.update', 'input_audio_buffer.commit', 'conversation.item.create'):
            for noise in RecognitionBudgets.noise(800): await self.queue.put(noise)
        if typ == 'session.update' and event['session']['audio']['input']['transcription']:
            if self.mode == 'config_error':
                self.sent.append(copy.deepcopy(event))
                await self.queue.put({'type': 'error', 'error': {'event_id': event['event_id'], 'code': 'invalid_value'}})
                return
            if self.mode in ('config_ignored', 'config_alternate'):
                self.sent.append(copy.deepcopy(event))
                accepted = copy.deepcopy(event['session'])
                accepted['audio']['input']['transcription'] = ({'model': 'UNREQUESTED'} if self.mode == 'config_alternate' else None)
                await self.queue.put({'type': 'session.updated', 'session': accepted})
                return
        if typ == 'input_audio_buffer.commit':
            self.sent.append(copy.deepcopy(event))
            if self.mode == 'early':
                for entry in self.events: await self.queue.put(entry)
            await self.queue.put({'type': 'input_audio_buffer.committed', 'item_id': None if self.mode == 'missing_item' else 'audio_exact'})
            if self.mode not in ('early', 'late', 'never', 'config_error', 'config_ignored', 'interrupt', 'during_response'):
                for entry in self.events: await self.queue.put(entry)
            if self.mode == 'interrupt':
                await self.queue.put({'type': 'error', 'error': {'code': 'synthetic_native_error'}})
            return
        await super().send_json(event)
        if typ == 'response.create' and self.mode == 'during_response':
            queued = []
            while not self.queue.empty(): queued.append(self.queue.get_nowait())
            for entry in queued[:1] + self.events + queued[1:]: await self.queue.put(entry)
        if typ == 'conversation.item.create' and event['item']['type'] == 'function_call_output':
            self.finishing.set()
            if self.mode == 'late':
                for entry in self.events: await self.queue.put(entry)
            if self.mode == 'late_socket_error':
                await self.queue.put({'type': 'session.closed'})


class RecognitionBudgets(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def noise(count):
        return [({'type': 'conversation.item.input_audio_transcription.delta',
                  'item_id': 'audio_exact', 'delta': 'DISCARDED'} if i % 2 else
                 recognition('FOREIGN', 'wrong_item')) for i in range(count)]

    async def test_response_final_after_asr_does_not_spend_native_budget(self):
        for count in (399, 800):
            with self.subTest(count=count):
                loop, wire = NativeLoop(), RecognitionWire()
                await wire.queue.put({'type': 'response.created', 'response': {'id': 'response_exact'}})
                for event in self.noise(count): await wire.queue.put(event)
                final = {'type': 'response.done', 'response': {
                    'id': 'response_exact', 'status': 'completed', 'output': []}}
                await wire.queue.put(final)
                self.assertEqual(await loop._response(wire, set()), final)
                self.assertTrue(wire.queue.empty())
                self.assertLessEqual(len(loop._early_transcripts), 8)
                self.assertIsNone(loop._transcript)

    async def test_acknowledgements_after_asr_do_not_spend_native_budget(self):
        for target in ('session.updated', 'input_audio_buffer.committed', 'item'):
            for count in (399, 800):
                with self.subTest(target=target, count=count):
                    loop, wire = NativeLoop(), RecognitionWire()
                    for event in self.noise(count): await wire.queue.put(event)
                    # One native intermediate makes the 399-ASR boundary fail too.
                    await wire.queue.put({'type': 'rate_limits.updated'})
                    item = {'id': 'output_exact', 'type': 'function_call_output',
                            'call_id': 'call_exact', 'output': '{}'}
                    final = ({'type': 'conversation.item.done', 'item': item}
                             if target == 'item' else {'type': target})
                    await wire.queue.put(final)
                    result = (await loop._wait_item(wire, item) if target == 'item'
                              else await loop._wait(wire, target))
                    self.assertEqual(result, final)
                    self.assertTrue(wire.queue.empty())

    async def test_asr_flood_has_separate_turn_bound(self):
        loop, wire = NativeLoop(), RecognitionWire()
        for event in self.noise(loop.TRANSCRIPT_EVENT_LIMIT + 1): await wire.queue.put(event)
        before = asyncio.all_tasks()
        with self.assertRaisesRegex(ValueError, 'recognition event budget'):
            await loop._wait(wire, 'session.updated')
        self.assertTrue(wire.queue.empty())
        self.assertLessEqual(len(loop._early_transcripts), 8)
        self.assertIsNone(loop._transcript)
        self.assertEqual(asyncio.all_tasks(), before)

    async def test_asr_budget_is_whole_turn_and_accepts_exact_limit(self):
        loop, wire = NativeLoop(), RecognitionWire()
        for count in (loop.TRANSCRIPT_EVENT_LIMIT - 1, 1):
            for event in self.noise(count): await wire.queue.put(event)
            await wire.queue.put({'type': 'session.updated'})
            self.assertEqual((await loop._wait(wire, 'session.updated'))['type'], 'session.updated')
        await wire.queue.put(recognition('FOREIGN', 'wrong_item'))
        with self.assertRaisesRegex(ValueError, 'recognition event budget'):
            await loop._wait(wire, 'session.updated')

    async def test_asr_flood_yields_to_existing_deadline_and_cancellation(self):
        class EndlessWire:
            async def receive_json(self):
                return recognition('FOREIGN', 'wrong_item')
        loop = NativeLoop()
        before = asyncio.all_tasks()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0):
                await loop._wait(EndlessWire(), 'session.updated')
        self.assertLess(loop._recognition_events, loop.TRANSCRIPT_EVENT_LIMIT)
        self.assertEqual(asyncio.all_tasks(), before)

    async def test_native_event_budget_is_unchanged(self):
        for target in ('response', 'item', 'session.updated'):
            with self.subTest(target=target):
                loop, wire = NativeLoop(), RecognitionWire()
                for _ in range(400): await wire.queue.put({'type': 'rate_limits.updated'})
                with self.assertRaisesRegex(ValueError, 'event budget'):
                    if target == 'response': await loop._response(wire, set())
                    elif target == 'item': await loop._wait_item(wire, {'id': 'output_exact'})
                    else: await loop._wait(wire, target)


class Transcripts(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = installed.InstalledEngine.asyncSetUp
    asyncTearDown = installed.InstalledEngine.asyncTearDown

    async def turn(self, wire=None, turn='turn_one'):
        self.wire = wire or RecognitionWire()
        self.engine.connect = self.wire.connect
        ids = self.real_bridge.ids('conversation', turn)
        answer = await self.engine(installed.PCM, ids)
        sid = self.engine.db.list_recent_sessions_bounded()[0]['id']
        rows = self.engine.db.get_messages(sid)
        records = [r for r in rows if r.get('display_kind') == 'native_audio_recognition']
        return answer, sid, rows, records

    def assert_record(self, records, status='available', count=1):
        self.assertEqual(len(records), count)
        row = records[-1]
        self.assertEqual(row['display_metadata']['status'], status)
        self.assertEqual(row['role'], 'system')
        self.assertTrue(row['content'])
        self.assertNotIn('input_summary', json.dumps(row))
        self.assertFalse(row['display_metadata']['audio_retained'])
        if status == 'available':
            self.assertEqual(row['content'], 'Speech recognition (may contain errors; not guaranteed verbatim):\n' + WORDS)
        else:
            self.assertNotIn(WORDS, row['content'])
        return row

    async def test_visible_record_pcm_only_and_final_order(self):
        answer, sid, rows, records = await self.turn()
        row = self.assert_record(records)
        self.assertEqual(answer, 'Offline answer?')
        self.assertLess(rows.index(row), len(rows) - 1)
        self.assertEqual(rows[-1]['content'], answer)
        sent = self.wire.sent
        raw = b''.join(base64.b64decode(e['audio']) for e in sent if e['type'] == 'input_audio_buffer.append')
        self.assertEqual(raw, resample_pcm16_16k_to_24k(installed.PCM))
        self.assertEqual(sum(e['type'] == 'input_audio_buffer.commit' for e in sent), 1)
        self.assertEqual(sum(e['type'] == 'response.create' for e in sent), 1)
        self.assertNotIn(WORDS, json.dumps(sent))
        self.assertNotIn(base64.b64encode(raw).decode(), json.dumps(rows))
        from hermes_state import SessionDB
        self.assertIsInstance(self.engine.db, SessionDB)

    async def test_answer_and_record_survive_response_asr_flood(self):
        wire = RecognitionWire('during_response', RecognitionBudgets.noise(800) + [recognition()])
        answer, _, rows, records = await self.turn(wire)
        self.assertEqual(answer, 'Offline answer?')
        self.assert_record(records)
        self.assertEqual(rows[-1]['content'], answer)
        self.assertNotIn(WORDS, json.dumps(wire.sent))

    async def test_answer_and_record_survive_acknowledgement_asr_floods(self):
        answer, _, rows, records = await self.turn(RecognitionWire('ack_flood'))
        self.assertEqual(answer, 'Offline answer?')
        self.assert_record(records)
        self.assertEqual(rows[-1]['content'], answer)
        self.assertNotIn(WORDS, json.dumps(self.wire.sent))

    async def test_early_exact_item(self):
        self.assert_record((await self.turn(RecognitionWire('early')))[3])

    async def test_early_foreign_then_exact(self):
        self.assert_record((await self.turn(RecognitionWire('early', [recognition('FOREIGN', 'wrong'), recognition()])))[3])

    async def test_interleaved_response_and_item_ack(self):
        events = [{'type': 'conversation.item.done', 'item': {'id': 'audio_exact', 'type': 'message', 'role': 'user'}}, recognition()]
        self.assert_record((await self.turn(RecognitionWire('during_response', events)))[3])

    async def test_missing_commit_identity_never_guesses(self):
        self.assert_record((await self.turn(RecognitionWire('missing_item')))[3], 'unavailable')

    async def test_empty_and_oversized_text_fail_without_native_outage(self):
        for index, text in enumerate(('', 'x' * 12001)):
            records = (await self.turn(RecognitionWire(events=[recognition(text)]), turn='invalid_' + str(index)))[3]
            self.assert_record(records, 'failed', count=index + 1)

    async def test_late_socket_failure_preserves_native_answer(self):
        self.assert_record((await self.turn(RecognitionWire('late_socket_error', [])))[3], 'late')

    async def test_grace_respects_existing_deadline_margin(self):
        loop = NativeLoop()
        loop._recognition_status = 'pending'
        loop._deadline = asyncio.get_running_loop().time() + 0.01
        start = time.monotonic()
        await loop._finish_recognition(RecognitionWire('never'))
        self.assertLess(time.monotonic() - start, 0.1)
        self.assertEqual(loop._recognition_status, 'late')

    async def test_unrelated_provider_error_not_suppressed(self):
        wire = RecognitionWire()
        await wire.queue.put({'type': 'error', 'error': {'event_id': 'FOREIGN_CONFIG', 'code': 'synthetic'}})
        loop = NativeLoop()
        with self.assertRaises(ValueError): await loop._receive(wire)

    async def test_wrong_item_then_exact_no_fusion(self):
        _, _, _, records = await self.turn(RecognitionWire(events=[recognition('FOREIGN', 'other'), recognition()]))
        self.assert_record(records)
        self.assertNotIn('FOREIGN', json.dumps(records))

    async def test_wrong_item_only(self):
        with patch.object(NativeLoop, 'TRANSCRIPT_GRACE', 0.01):
            self.assert_record((await self.turn(RecognitionWire(events=[recognition('FOREIGN', 'other')])))[3], 'late')

    async def test_wrong_content_index(self):
        with patch.object(NativeLoop, 'TRANSCRIPT_GRACE', 0.01):
            self.assert_record((await self.turn(RecognitionWire(events=[recognition(index=1)])))[3], 'late')

    async def test_repeated_conflicting_events_first_terminal_once(self):
        self.assert_record((await self.turn(RecognitionWire(events=[recognition(), recognition(), recognition('CONFLICT')])))[3])

    async def test_failure_not_words_or_native_outage(self):
        self.assert_record((await self.turn(RecognitionWire(events=[recognition(failed=True), recognition()])))[3], 'failed')

    async def test_delta_not_transcription(self):
        delta = {'type': 'conversation.item.input_audio_transcription.delta', 'item_id': 'audio_exact', 'delta': 'FAKE PARTIAL'}
        with patch.object(NativeLoop, 'TRANSCRIPT_GRACE', 0.01):
            self.assert_record((await self.turn(RecognitionWire(events=[delta])))[3], 'late')

    async def test_late_after_final_response_before_visible_final(self):
        self.assert_record((await self.turn(RecognitionWire('late')))[3])

    async def test_never_arrives_bounded_no_task_or_revision(self):
        start = time.monotonic()
        before = asyncio.all_tasks()
        with patch.object(NativeLoop, 'TRANSCRIPT_GRACE', 0.02):
            _, sid, rows, records = await self.turn(RecognitionWire('never'))
        self.assertLess(time.monotonic() - start, 1.5)
        self.assert_record(records, 'late')
        await self.wire.queue.put(recognition())  # After finalization cannot rewrite/append.
        await asyncio.sleep(0)
        self.assertEqual(rows, self.engine.db.get_messages(sid))
        self.assertEqual(asyncio.all_tasks(), before)
        self.assertFalse(self.engine.pending)

    async def test_optional_config_rejected_native_still_works(self):
        _, _, _, records = await self.turn(RecognitionWire('config_error'))
        self.assert_record(records, 'unavailable')
        updates = [e for e in self.wire.sent if e['type'] == 'session.update']
        self.assertEqual(len(updates), 2)
        self.assertIsNone(updates[1]['session']['audio']['input']['transcription'])

    async def test_optional_config_ignored_native_still_works(self):
        self.assert_record((await self.turn(RecognitionWire('config_ignored')))[3], 'unavailable')

    async def test_no_unrequested_model_or_paid_fallback(self):
        self.assert_record((await self.turn(RecognitionWire('config_alternate')))[3], 'unavailable')
        updates = [e for e in self.wire.sent if e['type'] == 'session.update']
        self.assertEqual(len(updates), 2)
        self.assertIsNone(updates[-1]['session']['audio']['input']['transcription'])
        self.assertEqual(sum(e['type'] == 'input_audio_buffer.commit' for e in self.wire.sent), 1)

    async def test_interrupted_one_visible_record_no_history_feedback(self):
        with self.assertRaises(ValueError): await self.turn(RecognitionWire('interrupt'))
        sid = self.engine.db.list_recent_sessions_bounded()[0]['id']
        records = [r for r in self.engine.db.get_messages(sid) if r.get('display_kind') == 'native_audio_recognition']
        self.assert_record(records, 'interrupted')
        self.assertNotIn('Speech recognition', json.dumps(self.engine.sessions.history(sid)))

    async def test_cancel_grace_one_record_no_background_task(self):
        wire = RecognitionWire('never')
        task = asyncio.create_task(self.turn(wire))
        await asyncio.wait_for(wire.finishing.wait(), 3)
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        sid = self.engine.db.list_recent_sessions_bounded()[0]['id']
        records = [r for r in self.engine.db.get_messages(sid) if r.get('display_kind') == 'native_audio_recognition']
        self.assert_record(records, 'cancelled')
        self.assertFalse(self.engine.pending)
        self.assertFalse(self.engine.lock.locked())

    async def test_legacy_summaries_and_recognition_never_replayed_two_turns(self):
        _, sid, _, _ = await self.turn()
        self.engine.db.append_message(sid, 'user', 'LEGACY INVENTED SUMMARY',
            display_metadata={'kind': 'same_model_semantic_derivative'})
        _, _, _, records = await self.turn(turn='turn_two')
        self.assert_record(records, count=2)
        wire = json.dumps(self.wire.sent)
        self.assertNotIn(WORDS, wire)
        self.assertNotIn('LEGACY INVENTED SUMMARY', wire)
        self.assertIn('Offline answer?', wire)

    async def test_actual_rest_and_desktop_history_projection(self):
        _, sid, _, records = await self.turn()
        # Official gateway imports may normalize sys.path/stdout for their own
        # process. Keep that bootstrap from contaminating later packaged tests.
        import sys
        original_path, original_stdout = sys.path[:], sys.stdout
        self.addCleanup(lambda: setattr(sys, 'path', original_path))
        self.addCleanup(lambda: setattr(sys, 'stdout', original_stdout))
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.session_controls import display_projection
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        adapter = object.__new__(APIServerAdapter)
        adapter._ensure_session_db_async = AsyncMock(return_value=self.engine.db)
        # Invoke the actual REST handler behind its auth decorator; no listener,
        # provider or production authority. Session resolution/paging stay real.
        response = await APIServerAdapter._handle_session_messages.__wrapped__(adapter,
            SimpleNamespace(match_info={'session_id': sid}, query={}))
        self.assertEqual(response.status, 200)
        api = json.loads(response.text)['data']
        projected = display_projection(self.engine.db.get_messages_as_conversation(sid, include_row_ids=True), self.home)
        for surface in (api, projected):
            matches = [r for r in surface if r.get('display_kind') == 'native_audio_recognition']
            self.assertEqual(len(matches), 1)
            self.assertIn(WORDS, matches[0].get('content') or matches[0].get('text') or '')
        # Optional private receipt for executing the unmodified Desktop hydration.
        import os
        from pathlib import Path
        if os.environ.get('HERMES_NATIVE_TRANSCRIPT_RECEIPT'):
            Path(os.environ['HERMES_NATIVE_TRANSCRIPT_RECEIPT']).write_text(json.dumps({'rest': api, 'desktop': projected}))


if __name__ == '__main__':
    unittest.main()
