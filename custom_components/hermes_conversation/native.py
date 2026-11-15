"""Bounded, single-use capture storage and optional native transport.

No provider, policy, transcript, microphone control or automatic text replay.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import time
from urllib.parse import urlsplit
import uuid

MAX_PCM = 1024 * 1024
TOKEN_PREFIX = "hermes-native:"


class NativeError(Exception):
    """Fixed public error, never include remote payloads or credentials."""


class CaptureStore:
    """Entry-local memory only; one-use handles expire after thirty seconds."""

    def __init__(self):
        self._items = OrderedDict()

    def put(self, pcm: bytes) -> str:
        if type(pcm) is not bytes or not pcm or len(pcm) % 2 or len(pcm) > MAX_PCM:
            raise NativeError("audio_limit")
        now = time.monotonic()
        for key, (_, deadline) in list(self._items.items()):
            if deadline <= now:
                self._items.pop(key)
        if len(self._items) >= 4:
            raise NativeError("capture_busy")
        token = TOKEN_PREFIX + uuid.uuid4().hex
        self._items[token] = (pcm, now + 30)
        return token

    def take(self, token: str) -> bytes:
        item = self._items.pop(token, None)
        if item is None or item[1] <= time.monotonic():
            raise NativeError("capture_unavailable")
        return item[0]

    def clear(self):
        self._items.clear()


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise NativeError("invalid_native_origin")
    return origin.rstrip("/")


@dataclass(frozen=True)
class NativeResult:
    text: str
    follow_up: bool


class NativeClient:
    """Version-one companion client; TLS and redirects always fail closed."""

    def __init__(self, session, origin, key, profile):
        self.session = session
        self.origin = validate_origin(origin)
        if not isinstance(key, str) or len(key) < 40 or not profile:
            raise NativeError("invalid_native_configuration")
        self.headers = {"Authorization": "Bearer " + key}
        self.profile = profile
        self._active = set()

    async def exchange(self, pcm: bytes, session_id: str, *, origin=None) -> NativeResult:
        """A fresh turn is never retried, including after ambiguous disconnect."""
        import aiohttp

        async def refuse_redirect(*args):
            raise NativeError("native_redirect")

        trace = aiohttp.TraceConfig()
        trace.on_request_redirect.append(refuse_redirect)
        # Reuse HA's verified connector, but do not mutate its shared session.
        async with aiohttp.ClientSession(
            connector=self.session.connector, connector_owner=False,
            trace_configs=[trace],
        ) as session:
            return await self._exchange(session, pcm, session_id, origin=origin)

    async def _exchange(self, session, pcm: bytes, session_id: str, *, origin=None) -> NativeResult:
        """Protocol body separated for deterministic transport tests."""
        if not pcm or len(pcm) % 2 or len(pcm) > MAX_PCM:
            raise NativeError("audio_limit")
        task = asyncio.current_task()
        self._active.add(task)
        try:
            async with asyncio.timeout(55):
                async with session.get(
                    self.origin + "/v1/native/capabilities", headers=self.headers,
                    allow_redirects=False, ssl=True,
                ) as response:
                    if response.status != 200 or response.content_length and response.content_length > 4096:
                        raise NativeError("native_capabilities")
                    raw = bytearray()
                    while chunk := await response.content.read(4097 - len(raw)):
                        raw.extend(chunk)
                        if len(raw) > 4096:
                            raise NativeError("native_capabilities")
                    import json
                    caps = json.loads(raw)
                required = {"version": 1, "profile": self.profile,
                            "format": "pcm_s16le", "sample_rate": 16000,
                            "max_pcm_bytes": MAX_PCM, "cancel_on_disconnect": True,
                            "replay_protection": True, "final_only": True}
                if type(caps) is not dict or any(type(caps.get(k)) is not type(v) or caps.get(k) != v for k, v in required.items()):
                    raise NativeError("native_capabilities")
                ids = {"session_id": session_id, "turn_id": uuid.uuid4().hex}
                async with session.ws_connect(
                    self.origin + "/v1/native", headers=self.headers,
                    ssl=True, max_msg_size=8192,
                ) as socket:
                    await socket.send_json({"type": "start", "version": 1,
                                            "profile": self.profile, **ids,
                                            "sample_rate": 16000,
                                            **({"origin": origin} if origin is not None else {})})
                    for offset in range(0, len(pcm), 32000):
                        await socket.send_bytes(pcm[offset:offset + 32000])
                    await socket.send_json({"type": "end"})
                    result = await socket.receive_json()
                    if (type(result) is not dict or set(result) != {"type", "text", "continue_conversation", *ids}
                            or result["type"] != "final"
                            or any(result[k] != v for k, v in ids.items())
                            or type(result["continue_conversation"]) is not bool
                            or type(result["text"]) is not str
                            or not 1 <= len(result["text"]) <= 2000
                            or TOKEN_PREFIX in result["text"]):
                        raise NativeError("native_result")
                    return NativeResult(result["text"], result["continue_conversation"])
        except asyncio.CancelledError:
            raise
        except Exception:
            raise NativeError("native_exchange_failed") from None
        finally:
            self._active.discard(task)

    def shutdown(self):
        for task in tuple(self._active):
            task.cancel()
