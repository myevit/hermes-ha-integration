"""Real HTTPS/WSS/client interoperability; inference is a synthetic boundary.

Run separately from HA stubs: python -m unittest discover -s companion/tests -v
Requires aiohttp, cryptography and the integration source, not Hermes or HA.
"""
import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.util
import ipaddress
import os
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest

import aiohttp
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get("HERMES_NATIVE_PACKAGED_PYTHON"):
    sys.path.insert(0, str(ROOT / "companion"))
from hermes_native_companion.server import create_app, Reservations
spec = importlib.util.spec_from_file_location("native_client", ROOT / "custom_components/hermes_conversation/native.py")
native = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = native
spec.loader.exec_module(native)

KEY = "synthetic-offline-credential-" + "x" * 48
PCM = b"\x01\x00" * 160


def tls_contexts(directory, *, expired=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Offline loopback")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), False)
        .sign(key, hashes.SHA256()))
    certfile, keyfile = Path(directory) / "cert.pem", Path(directory) / "key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(certfile, keyfile)
    client = ssl.create_default_context(cafile=str(certfile))
    return server, client


class Boundary:
    """Protocol-only deterministic boundary, never a claimed Hermes engine."""
    profile = "voice"
    device_id = "device"
    satellite_id = "assist_satellite.example"

    def __init__(self, path):
        self.db_path = path
        self.calls = []
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.hold = False
        self.fail = False

    def ids(self, session, turn):
        from hermes_native_companion.server import identifier
        return dict(session_id=identifier(session), turn_id=identifier(turn),
                    device_id=self.device_id, satellite_id=self.satellite_id)

    async def exchange(self, pcm, ids):
        self.calls.append((pcm, ids))
        self.entered.set()
        try:
            if self.hold:
                await asyncio.Event().wait()
            if self.fail:
                raise ValueError("synthetic post-effect failure must not leak")
            return "Ready?", True
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class Protocol(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.server_tls, self.client_tls = tls_contexts(self.tmp.name)
        self.bridge = Boundary(Path(self.tmp.name) / "state.db")
        self.runner = web.AppRunner(create_app(self.bridge, KEY))
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0, ssl_context=self.server_tls)
        await site.start()
        self.origin = "https://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=self.client_tls))
        self.client = native.NativeClient(self.session, self.origin, KEY, "voice")

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.tmp.cleanup()

    async def socket(self, turn="turn", **changes):
        ws = await self.session.ws_connect(self.origin + "/v1/native", headers={"Authorization": "Bearer " + KEY})
        start = dict(type="start", version=1, profile="voice", session_id="conversation", turn_id=turn, sample_rate=16000)
        start.update(changes)
        await ws.send_json(start)
        return ws

    async def submit(self, ws, pcm=PCM):
        await ws.send_bytes(pcm)
        await ws.send_json({"type": "end"})
        return await ws.receive_json()

    async def test_real_verified_tls_client_final(self):
        result = await self.client.exchange(PCM, "conversation")
        self.assertEqual((result.text, result.follow_up), ("Ready?", True))
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_wrong_auth(self):
        for token in ("", "Bearer wrong"):
            async with self.session.get(self.origin + "/v1/native/capabilities", headers={"Authorization": token}) as response:
                self.assertEqual(response.status, 401)
        self.assertFalse(self.bridge.calls)

    async def test_tls_untrusted(self):
        async with aiohttp.ClientSession() as session:
            with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                await session.get(self.origin + "/v1/native/capabilities")

    async def test_wrong_profile_no_pcm_dispatch(self):
        client = native.NativeClient(self.session, self.origin, KEY, "other")
        with self.assertRaises(native.NativeError):
            await client.exchange(PCM, "conversation")
        self.assertFalse(self.bridge.calls)

    async def test_expired_trusted_certificate(self):
        certdir = Path(self.tmp.name) / 'expired'
        certdir.mkdir()
        server_tls, client_tls = tls_contexts(certdir, expired=True)
        runner = web.AppRunner(create_app(self.bridge, KEY))
        await runner.setup()
        try:
            site = web.TCPSite(runner, '127.0.0.1', 0, ssl_context=server_tls)
            await site.start()
            origin = 'https://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=client_tls)) as session:
                with self.assertRaises(native.NativeError):
                    await native.NativeClient(session, origin, KEY, 'voice').exchange(PCM, 'conversation')
            self.assertFalse(self.bridge.calls)
        finally:
            await runner.cleanup()

    async def test_reservation_process_restart_and_bounded_capacity(self):
        journal = Reservations(self.bridge)

        journal.reserve('before_restart')
        script = ('from pathlib import Path; from hermes_native_companion.server import Reservations; '
                  'b=type("Owner",(),dict(db_path=Path(__import__("sys").argv[1]),profile="voice",'
                  'device_id="device",satellite_id="assist_satellite.example"))(); '
                  'j=Reservations(b); j.reserve("before_restart")')
        proc = await asyncio.create_subprocess_exec(sys.executable, '-c', script, str(self.bridge.db_path),
            env={**os.environ, 'PYTHONPATH': str(ROOT / 'companion')},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, error = await proc.communicate()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b'IntegrityError', error)
        import sqlite3
        with sqlite3.connect(self.bridge.db_path) as db:
            db.executemany('INSERT INTO hermes_native_reservations VALUES (?,?,?,?)',
                [('voice', 'device', 'assist_satellite.example', 'fill_' + str(i)) for i in range(99999)])
        with self.assertRaisesRegex(ValueError, 'capacity'):
            journal.reserve('must_not_evict')
        with self.assertRaisesRegex(ValueError, 'capacity'):
            journal.reserve('before_restart')

    async def test_handshake_types(self):
        for i, changes in enumerate(({"profile": "other"}, {"version": True}, {"sample_rate": True}, {"session_id": "../bad"})):
            async with await self.socket("bad" + str(i), **changes) as ws:
                self.assertEqual((await ws.receive_json())["type"], "error")
        self.assertFalse(self.bridge.calls)

    async def test_replay_even_changed_session_and_restart(self):
        async with await self.socket() as ws:
            self.assertEqual((await self.submit(ws))["type"], "final")
        async with await self.socket(session_id="different") as ws:
            self.assertEqual((await ws.receive_json())["type"], "error")
        self.assertEqual(len(self.bridge.calls), 1)
        # A fresh journal/connection still rejects; no in-memory-only replay defense.
        journal = Reservations(self.bridge)
        try:
            with self.assertRaises(Exception):
                journal.reserve("turn")
        finally:
            journal.close()

    async def test_overflow_no_inference(self):
        async with await self.socket() as ws:
            for _ in range(33):
                await ws.send_bytes(b"\0" * 32000)
            self.assertEqual((await ws.receive_json())["type"], "error")
        self.assertFalse(self.bridge.calls)

    async def test_disconnect_cancels_and_burns_turn(self):
        self.bridge.hold = True
        ws = await self.socket()
        await ws.send_bytes(PCM)
        await ws.send_json({"type": "end"})
        await asyncio.wait_for(self.bridge.entered.wait(), 2)
        await ws.close()
        await asyncio.wait_for(self.bridge.cancelled.wait(), 2)
        async with await self.socket() as retry:
            self.assertEqual((await retry.receive_json())["type"], "error")
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_failure_after_effect_no_replay_or_error_leak(self):
        self.bridge.fail = True
        async with await self.socket() as ws:
            self.assertEqual(await self.submit(ws), {"type": "error", "category": "native_failed"})
        async with await self.socket() as retry:
            self.assertEqual((await retry.receive_json())["type"], "error")
        self.assertEqual(len(self.bridge.calls), 1)

    async def test_explicit_cancel_no_late_final(self):
        self.bridge.hold = True
        async with await self.socket() as ws:
            await ws.send_bytes(PCM)
            await ws.send_json({"type": "end"})
            await self.bridge.entered.wait()
            await ws.send_json({"type": "cancel"})
            self.assertEqual((await ws.receive_json())["type"], "error")
            await asyncio.wait_for(self.bridge.cancelled.wait(), 2)
