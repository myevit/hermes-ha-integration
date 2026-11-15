"""Native boundary tests; transport peers below are synthetic, not providers."""
import asyncio
import json
import unittest
from unittest.mock import patch

from tests.test_support import FakeConfigEntry, FakeConversationInput, FakeHass
from tests.test_conversation import FakeClient
from custom_components.hermes_conversation.conversation import HermesConversationAgent
from custom_components.hermes_conversation.const import DOMAIN
from custom_components.hermes_conversation.native import (
    CaptureStore, MAX_PCM, NativeClient, NativeError, NativeResult, validate_origin,
)


class Context:
    def __init__(self, value): self.value = value
    async def __aenter__(self): return self.value
    async def __aexit__(self, *args): pass


class Socket:
    def __init__(self, final=None): self.start = None; self.pcm = b''; self.final = final
    async def send_json(self, data):
        if data['type'] == 'start': self.start = data
    async def send_bytes(self, data): self.pcm += data
    async def receive_json(self):
        return self.final or {'type': 'final', 'text': 'Ready?', 'continue_conversation': True,
                             **{k: self.start[k] for k in ('session_id', 'turn_id')}}


class Peer:
    def __init__(self, caps=None, final=None):
        self.caps = caps or dict(version=1, profile='worker', format='pcm_s16le',
                                sample_rate=16000, max_pcm_bytes=MAX_PCM,
                                cancel_on_disconnect=True, replay_protection=True, final_only=True)
        self.socket = Socket(final); self.connections = 0
    def get(self, *args, **kwargs):
        class Body:
            consumed = False
            async def read(inner, limit):
                if inner.consumed:
                    return b''
                inner.consumed = True
                return json.dumps(self.caps).encode()
        class Response:
            status = 200; content_length = None; content = Body()
        return Context(Response())
    def ws_connect(self, *args, **kwargs):
        self.connections += 1
        return Context(self.socket)


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

    def test_origins(self):
        self.assertEqual(validate_origin('https://example.org/'), 'https://example.org')
        for url in ('http://example.org', 'https://a:b@example.org', 'https://example.org/path', 'https://example.org/?key=x'):
            with self.assertRaises(NativeError): validate_origin(url)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_and_correlation(self):
        peer = Peer(); client = NativeClient(None, 'https://example.org', 'x' * 40, 'worker')
        result = await client._exchange(peer, b'\0\0', 'session')
        self.assertEqual(result, NativeResult('Ready?', True))
        self.assertEqual(peer.socket.pcm, b'\0\0')
        self.assertEqual(peer.connections, 1)

    async def test_profile_mismatch_no_audio_dispatch(self):
        peer = Peer(); peer.caps['profile'] = 'other'
        client = NativeClient(None, 'https://example.org', 'x' * 40, 'worker')
        with self.assertRaisesRegex(NativeError, '^native_exchange_failed$'):
            await client._exchange(peer, b'\0\0', 'session')
        self.assertEqual(peer.connections, 0)

    async def test_bad_final_no_retry(self):
        peer = Peer(final={'type': 'final', 'text': 'private server error'})
        client = NativeClient(None, 'https://example.org', 'x' * 40, 'worker')
        with self.assertRaisesRegex(NativeError, '^native_exchange_failed$'):
            await client._exchange(peer, b'\0\0', 'session')
        self.assertEqual(peer.connections, 1)

    async def test_cancel(self):
        peer = Peer(); waiting = asyncio.Event()
        async def receive():
            waiting.set(); await asyncio.Future()
        peer.socket.receive_json = receive
        client = NativeClient(None, 'https://example.org', 'x' * 40, 'worker')
        task = asyncio.create_task(client._exchange(peer, b'\0\0', 'session'))
        await waiting.wait(); client.shutdown()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(client._active)

    async def test_native_conversation_no_text_dispatch_and_replay_refused(self):
        hass = FakeHass(); entry = FakeConfigEntry(); text = FakeClient()
        store = CaptureStore()
        class Native:
            async def exchange(self, pcm, session_id): return NativeResult('Ready?', True)
        hass.data[DOMAIN] = {entry.entry_id: dict(capture_store=store, native_client=Native())}
        agent = HermesConversationAgent(hass, entry, text, session_map={})
        token = store.put(b'\0\0')
        user = FakeConversationInput(text=token, conversation_id='session')
        result = await agent.async_process(user)
        self.assertTrue(result.continue_conversation)
        result = await agent.async_process(user)
        self.assertFalse(result.continue_conversation)
        self.assertTrue(result.response.error)
        self.assertEqual(text.calls, [])
