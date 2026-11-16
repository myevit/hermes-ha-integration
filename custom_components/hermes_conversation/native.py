"""Entry-local, one-use HA audio handoff to the ordinary Hermes API."""
from __future__ import annotations

import base64
from collections import OrderedDict
import io
import time
import uuid
import wave

MAX_PCM = 1024 * 1024
TOKEN_PREFIX = "hermes-native:"
NATIVE_MODEL = "gpt-realtime-2.1"


class NativeError(Exception):
    """Fixed public error, never remote payloads or credentials."""


class CaptureStore:
    """Keep at most four captures in memory, expiring after thirty seconds."""

    def __init__(self):
        self._items = OrderedDict()

    def put(self, pcm: bytes) -> str:
        validate_pcm(pcm)
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


def validate_pcm(pcm: bytes):
    if type(pcm) is not bytes or not pcm or len(pcm) % 2 or len(pcm) > MAX_PCM:
        raise NativeError("audio_limit")


def audio_content(pcm: bytes) -> list[dict]:
    """Wrap the unchanged HA PCM in the existing API's native-audio shape."""
    validate_pcm(pcm)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return [{"type": "input_audio", "input_audio": {
        "format": "wav", "data": base64.b64encode(out.getvalue()).decode("ascii")}}]
