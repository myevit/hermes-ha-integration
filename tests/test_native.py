"""Native boundary tests; transport peers below are synthetic, not providers."""
import base64
import io
import wave
import unittest
from unittest.mock import patch

from tests.test_support import FakeConfigEntry, FakeConversationInput, FakeHass
from tests.test_conversation import FakeClient
from custom_components.hermes_conversation.conversation import HermesConversationAgent
from custom_components.hermes_conversation.const import DOMAIN
from custom_components.hermes_conversation.native import (
    CaptureStore, MAX_PCM, NativeError, audio_content,
)


class StoreTests(unittest.TestCase):
    def test_one_use(self):
        store = CaptureStore(); token = store.put(b'\0\0')
        self.assertEqual(store.take(token), b'\0\0')
        with self.assertRaises(NativeError): store.take(token)

    def test_expiry(self):
        store = CaptureStore()
        with patch('time.monotonic', return_value=1): token = store.put(b'\0\0')
        with patch('time.monotonic', return_value=32):
            with self.assertRaises(NativeError): store.take(token)

    def test_limit_and_clear(self):
        store = CaptureStore()
        for pcm in (b'', b'x', b'x' * (MAX_PCM + 2)):
            with self.assertRaises(NativeError): store.put(pcm)
        tokens = [store.put(b'\0\0') for _ in range(4)]
        with self.assertRaises(NativeError): store.put(b'\0\0')
        store.clear()
        for token in tokens:
            with self.assertRaises(NativeError): store.take(token)

    def test_wav_preserves_all_pcm(self):
        pcm = b'\0\0' * 240000
        part = audio_content(pcm)[0]
        with wave.open(io.BytesIO(base64.b64decode(part['input_audio']['data']))) as wav:
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.readframes(wav.getnframes()), pcm)


class NativeConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_uses_normal_api_stream_and_refuses_marker_replay(self):
        hass = FakeHass(); entry = FakeConfigEntry(data={'api_key': 'synthetic-key'})
        api = FakeClient(stream_chunks=['Ready.'])
        store = CaptureStore()
        hass.data[DOMAIN] = {entry.entry_id: {'capture_store': store}}
        sessions = {}
        agent = HermesConversationAgent(hass, entry, api, session_map=sessions)
        token = store.put(b'\0\0')
        user = FakeConversationInput(text=token, conversation_id='same')
        await agent.async_process(user)
        self.assertEqual(api.calls[0]['method'], 'stream')
        self.assertEqual(api.calls[0]['messages'][-1]['content'], audio_content(b'\0\0'))
        self.assertNotIn(token, repr(api.calls))
        replay = await agent.async_process(user)
        self.assertTrue(replay.response.error)
        self.assertEqual(len(api.calls), 1)
        await agent.async_process(FakeConversationInput(text=store.put(b'\0\0'), conversation_id='same'))
        self.assertEqual(api.calls[1]['session_id'], 'sess-1')
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(agent._history), 0)
