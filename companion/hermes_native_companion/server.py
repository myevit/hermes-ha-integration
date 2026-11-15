"""Version-one peer for the HA adapter, wrapping a profile-owned native engine.

The engine, not this transport, owns admission, tools, memory and conversation.
The credential is bound to ONE explicitly configured device/satellite principal.
Replay reservations survive cancellation, failure and restart in the engine DB.
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import re
import sqlite3
from pathlib import Path

from aiohttp import WSMsgType, web

MAX_PCM = 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def identifier(value):
    if type(value) is not str or not ID.fullmatch(value):
        raise ValueError("invalid identity")
    return value


class EngineBridge:
    """Adapter for an actual installed plugin's Engine(pcm, ids) factory result.

    There is no native-engine registry in Hermes 0.23.1. This explicit optional
    dependency is NOT an inference implementation shipped by Hermes core.
    """

    def __init__(self, engine, *, profile, device_id, satellite_id, bindings=None):
        from hermes_cli.plugins import PluginContext

        self.profile = identifier(profile)
        if profile == "default":
            raise ValueError("explicit non-default profile required")
        self.device_id = identifier(device_id)
        if type(satellite_id) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", satellite_id):
            raise ValueError("invalid satellite identity")
        self.satellite_id = satellite_id
        self.engine = engine
        self.host = engine.host
        if not isinstance(self.host.ctx, PluginContext):
            raise TypeError("genuine owning PluginContext required")
        with self.host.scope_home():
            if self.host.ctx.profile_name != profile:
                raise ValueError("owning profile mismatch")
        home = Path(self.host.ctx._manager.home_path).resolve()
        if Path(self.host.home).resolve() != home:
            raise ValueError("engine home mismatch")
        self.db_path = Path(engine.db.db_path).resolve()
        if not self.db_path.is_relative_to(home):
            raise ValueError("engine database outside owning profile")
        if not callable(engine) or not callable(engine.take_followup):
            raise TypeError("native engine interface unavailable")
        # Check the exact authenticated binding BEFORE advertising capabilities.
        engine.policy.binding(self.ids("probe", "probe"))
        self.bindings = {(self.device_id, self.satellite_id)}
        if bindings is not None:
            if type(bindings) is not list or not 1 <= len(bindings) <= 64:
                raise ValueError("finite bindings required")
            for pair in bindings:
                if type(pair) is not list or len(pair) != 2 or any(type(v) is not str for v in pair):
                    raise ValueError("invalid binding")
                engine.policy.binding(dict(session_id="probe", turn_id="probe",
                    device_id=identifier(pair[0]), satellite_id=pair[1]))
            self.bindings = {tuple(pair) for pair in bindings}
            if (self.device_id, self.satellite_id) not in self.bindings:
                raise ValueError("primary binding must be explicitly allowed")

    def origin_ids(self, session_id, turn_id, origin):
        if type(origin) is not dict or set(origin) != {"device_id", "satellite_id", "area_id"}:
            raise ValueError("physical origin required")
        if any(type(v) is not str or not 1 <= len(v) <= 128 for v in origin.values()):
            raise ValueError("invalid physical origin")
        if (origin["device_id"], origin["satellite_id"]) not in self.bindings:
            raise ValueError("origin outside credential binding")
        ids = dict(session_id=identifier(session_id), turn_id=identifier(turn_id),
                   device_id=identifier(origin["device_id"]), satellite_id=origin["satellite_id"])
        binding = self.engine.policy.binding(ids)
        if origin["area_id"] != binding["area_id"]:
            raise ValueError("origin area mismatch")
        return ids

    def ids(self, session_id, turn_id):
        return {"session_id": identifier(session_id), "turn_id": identifier(turn_id),
                "device_id": self.device_id, "satellite_id": self.satellite_id}

    async def exchange(self, pcm, ids):
        text = await self.engine(pcm, ids)
        followup = self.engine.take_followup(ids)
        if (type(text) is not str or not 1 <= len(text) <= 2000
                or "hermes-native:" in text or type(followup) is not bool):
            raise ValueError("invalid engine final")
        return text, followup


class Reservations:
    """A transport journal, NOT session rows or a second conversation database.

    Same SQLite file as the engine. Unique profile/principal/turn IDs, independent
    of session IDs: changing a conversation must not bypass uncertain admission.
    No TTL eviction: fail closed at capacity rather than permit old turn replay.
    """

    def __init__(self, bridge):
        self.db = sqlite3.connect(bridge.db_path, timeout=2)
        self.db.execute("CREATE TABLE IF NOT EXISTS hermes_native_reservations "
                        "(profile TEXT, device TEXT, satellite TEXT, turn TEXT, "
                        "PRIMARY KEY(profile, device, satellite, turn))")
        self.db.commit()
        self.principal = (bridge.profile, bridge.device_id, bridge.satellite_id)

    def reserve(self, turn, ids=None):
        principal = self.principal if ids is None else (self.principal[0], ids["device_id"], ids["satellite_id"])
        with self.db:
            # BEGIN IMMEDIATE makes capacity + reservation atomic across workers.
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute("SELECT COUNT(*) FROM hermes_native_reservations").fetchone()[0] >= 100000:
                raise ValueError("reservation capacity")
            self.db.execute("INSERT INTO hermes_native_reservations VALUES (?, ?, ?, ?)",
                            (*principal, turn))

    def close(self):
        self.db.close()


def create_app(bridge: EngineBridge, key: str):
    """Build an inert app; caller owns verified TLS and lifecycle, never HA config."""
    if type(key) is not str or len(key) < 40 or not key.isascii() or any(c.isspace() for c in key):
        raise ValueError("managed credential required")
    journal = Reservations(bridge)
    active = set()
    busy = False

    @web.middleware
    async def authenticate(request, handler):
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + key).encode()):
            raise web.HTTPUnauthorized()
        if not request.secure:
            raise web.HTTPForbidden()
        return await handler(request)

    async def capabilities(request):
        return web.json_response({"version": 1, "profile": bridge.profile,
            "format": "pcm_s16le", "sample_rate": 16000, "max_pcm_bytes": MAX_PCM,
            "cancel_on_disconnect": True, "replay_protection": True, "final_only": True},
            headers={"Cache-Control": "no-store"})

    async def exchange(request):
        nonlocal busy
        socket = web.WebSocketResponse(max_msg_size=65536)
        await socket.prepare(request)
        if busy:
            await socket.close(code=1013)
            return socket
        busy = True
        worker = watcher = None
        pcm = bytearray()
        task = asyncio.current_task()
        active.add(task)
        try:
            async with asyncio.timeout(55):
                start = await socket.receive_json(timeout=10)
                required = {"type", "version", "profile", "session_id", "turn_id", "sample_rate"}
                if (type(start) is not dict or set(start) not in (required, required | {"origin"})
                        or start["type"] != "start" or type(start["version"]) is not int
                        or start["version"] != 1 or start["profile"] != bridge.profile
                        or type(start["sample_rate"]) is not int or start["sample_rate"] != 16000):
                    raise ValueError("handshake")
                ids = bridge.ids(start["session_id"], start["turn_id"])
                if "origin" in start:
                    ids = bridge.origin_ids(start["session_id"], start["turn_id"], start["origin"])
                elif len(getattr(bridge, "bindings", (None,))) != 1:
                    raise ValueError("physical origin required for multiple bindings")
                # Burn admission BEFORE PCM receipt or inference; never clear on failure.
                journal.reserve(ids["turn_id"], ids)
                while True:
                    message = await socket.receive(timeout=10)
                    if message.type == WSMsgType.BINARY:
                        if len(message.data) > 32000 or len(message.data) % 2 or len(pcm) + len(message.data) > MAX_PCM:
                            raise ValueError("audio budget")
                        pcm.extend(message.data)
                    elif message.type == WSMsgType.TEXT and message.json() == {"type": "end"}:
                        break
                    else:
                        raise ValueError("capture interrupted")
                if not pcm:
                    raise ValueError("empty capture")
                worker = asyncio.create_task(bridge.exchange(bytes(pcm), ids))
                pcm.clear()
                # A close, extra frame, or explicit cancel all invalidate this turn.
                watcher = asyncio.create_task(socket.receive())
                done, _ = await asyncio.wait((worker, watcher), return_when=asyncio.FIRST_COMPLETED)
                if watcher in done or socket.closed:
                    raise ValueError("caller disconnected or cancelled")
                text, followup = worker.result()
                await socket.send_json({"type": "final", "session_id": ids["session_id"],
                    "turn_id": ids["turn_id"], "text": text,
                    "continue_conversation": followup})
        except asyncio.CancelledError:
            raise
        except Exception:
            # No raw provider, policy, profile paths or credentials on the wire/log.
            with contextlib.suppress(Exception):
                await socket.send_json({"type": "error", "category": "native_failed"})
        finally:
            pcm.clear()
            for future in (watcher, worker):
                if future is not None:
                    if not future.done():
                        future.cancel()
                    with contextlib.suppress(BaseException):
                        await future
            # Engine.pending retains uncancellable tool workers; its admission policy
            # remains authoritative after local cancellation. Never retry here.
            active.discard(task)
            busy = False
            await socket.close()
        return socket

    async def shutdown(app):
        for task in tuple(active):
            task.cancel()
        await asyncio.gather(*tuple(active), return_exceptions=True)

    async def cleanup(app):
        journal.close()

    app = web.Application(middlewares=[authenticate], client_max_size=MAX_PCM)
    app.router.add_get("/v1/native/capabilities", capabilities)
    app.router.add_get("/v1/native", exchange)
    app.on_shutdown.append(shutdown)
    app.on_cleanup.append(cleanup)
    return app
