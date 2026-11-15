"""Public wheel factory/Host qualification; only provider/MCP networks synthetic."""
import asyncio
import contextlib
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from hermes_native_companion import EngineBridge
from hermes_native_companion.__main__ import load_engine
import test_protocol as protocol
PCM = protocol.PCM


class ProviderWire:
    """Provider NETWORK seam only; Engine/NativeLoop/SessionDB/memory stay real."""
    def __init__(self):
        self.queue = asyncio.Queue()
        self.sent = []
        self.counter = 0
        self.bad_catalog = False
        self.late_ack = False

    async def send_json(self, event):
        self.sent.append(copy.deepcopy(event))
        typ = event['type']
        if typ == 'session.update':
            accepted = copy.deepcopy(event['session'])
            if self.bad_catalog:
                accepted['tools'] = []
            await self.queue.put({'type': 'session.updated', 'session': accepted})
        elif typ == 'input_audio_buffer.commit':
            await self.queue.put({'type': 'input_audio_buffer.committed'})
        elif typ == 'conversation.item.create':
            item = copy.deepcopy(event['item'])
            if self.late_ack and item['type'] == 'function_call_output':
                return
            if item['type'] == 'message':
                item['status'] = 'completed'
            await self.queue.put({'type': 'conversation.item.done', 'item': item})
        elif typ == 'response.create':
            self.counter += 1
            rid = 'response_' + str(self.counter)
            await self.queue.put({'type': 'response.created', 'response': {'id': rid}})
            await self.queue.put({'type': 'response.done', 'response': {'id': rid,
                'status': 'completed', 'output': [{'type': 'function_call', 'name': 'finish_turn',
                    'call_id': 'call_' + str(self.counter), 'arguments': json.dumps({
                    'answer': 'Offline answer?', 'followup': True})}]}})

    async def receive_json(self):
        return await self.queue.get()

    @contextlib.asynccontextmanager
    async def connect(self):
        yield self


class InstalledEngine(unittest.IsolatedAsyncioTestCase):
    """Runs inherited real TLS protocol cases with the ACTUAL plugin factory too."""
    async def asyncSetUp(self):
        # Protocol sets up TLS first. Replace only its inference boundary below.
        await protocol.Protocol.asyncSetUp(self)
        from hermes_cli.plugins import PluginManager, _plugin_home_scope
        from hermes_cli.plugins_manifest import parse_manifest_file
        self.profile = 'voice-example'
        self.home = Path(self.tmp.name) / 'profiles' / self.profile
        self.home.mkdir(parents=True)
        (self.home.parent.parent / 'config.yaml').write_text('{}\n')
        (self.home / 'config.yaml').write_text('memory:\n  provider: mnemosyne\n  mnemosyne:\n    shared_surface_read: false\n    sync_roles: []\n')
        (self.home / 'SOUL.md').write_text('# Offline assistant\nOnly synthetic isolated qualification.\n')
        memory = self.home / 'plugins' / 'mnemosyne'
        memory.mkdir(parents=True)
        (memory / '__init__.py').write_text('from mnemosyne_hermes import MnemosyneMemoryProvider\n')
        self.env = patch.dict(os.environ, HERMES_HOME=str(self.home))
        self.env.start()
        self.scope = _plugin_home_scope(self.home)
        self.scope.__enter__()
        from hermes_native_engine.install import install
        source = install(self.home)
        manifest = parse_manifest_file(source / 'plugin.yaml', source, 'user', '')
        self.plugin_name = manifest.name
        self.manager = PluginManager(scope_key=str(self.home))
        # Actual installed loader calls register(ctx); no manufactured runtime/profile.
        self.manager._load_plugin(manifest)
        self.manager._discovered = True
        self.module = self.manager._plugins[manifest.name].module
        ctx = self.module.get_ctx()
        ctx.register_tool('mcp__homeassistant__ha_get_state', 'offline', {
            'name': 'mcp__homeassistant__ha_get_state', 'description': 'Synthetic offline read boundary',
            'parameters': {'type': 'object', 'properties': {'entity_id': {'type': 'string'}},
                           'required': ['entity_id'], 'additionalProperties': False}},
            lambda args, **kw: json.dumps({'entity_id': args['entity_id'], 'state': 'off', 'attributes': {}}))
        policy = {'version': 1, 'approved': True, 'bindings': [{
            'device_id': 'device', 'satellite_id': 'assist_satellite.example',
            'area_id': 'example', 'area_name': 'Example'}],
            'entities': {'light.example': {'name': 'Example light', 'area_id': 'example', 'actions': []}}}
        policy_path = self.home / 'policy.json'
        policy_path.write_text(json.dumps(policy))
        # Discovery is the separate household NETWORK seam: never connect real MCP.
        with patch('tools.mcp_tool_discovery.discover_mcp_tools') as discovery:
            self.engine = load_engine(self.manager, manifest.name, {'policy_path': str(policy_path)})
            discovery.assert_called_once_with(allowed_mcp_names=['homeassistant'])
        import hermes_native_engine
        self.assertIn('site-packages', hermes_native_engine.__file__)
        import sysconfig
        installed_root = Path(sysconfig.get_paths()['purelib']).resolve()
        for name in ('hermes_native_engine', 'mnemosyne_hermes', 'hermes_native_companion'):
            self.assertTrue(Path(__import__(name).__file__).resolve().is_relative_to(installed_root))
        self.assertFalse({'backend', 'native_home', 'talk_auth', 'talk_wire'} & sys.modules.keys())
        self.wire = ProviderWire()
        self.engine.connect = self.wire.connect
        self.real_bridge = EngineBridge(self.engine, profile=self.profile,
            device_id='device', satellite_id='assist_satellite.example')

    async def asyncTearDown(self):
        if hasattr(self, 'engine'):
            if self.engine.pending:
                await asyncio.gather(*tuple(self.engine.pending), return_exceptions=True)
            self.engine.db.close()
        if hasattr(self, 'scope'):
            self.scope.__exit__(None, None, None)
        if hasattr(self, 'env'):
            self.env.stop()
        await protocol.Protocol.asyncTearDown(self)

    async def test_actual_factory_tls_two_turn_memory_and_session(self):
        from aiohttp import web
        from hermes_native_companion import create_app
        from test_protocol import KEY, native
        from agent.memory_manager import MemoryManager
        # Restart ONLY this test listener with the real bridge, not a second backend.
        await self.runner.cleanup()
        self.runner = web.AppRunner(create_app(self.real_bridge, KEY))
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0, ssl_context=self.server_tls)
        await site.start()
        origin = 'https://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        client = native.NativeClient(self.session, origin, KEY, self.profile)
        memory_instances = []
        memory_paths = []
        original = self.engine.memory_factory
        def capture(sid, key):
            try:
                manager = original(sid, key)
                self.assertIsInstance(manager, MemoryManager)
                memory_instances.append(manager)
                provider = manager.get_provider('mnemosyne')
                self.assertIsNotNone(provider)
                path = Path(provider._beam.db_path).resolve()
                self.assertTrue(path.is_relative_to(self.home))
                self.assertEqual(provider._agent_identity, self.profile)
                memory_paths.append(path)
                return manager
            except BaseException:
                import traceback
                traceback.print_exc()
                raise
        self.engine.memory_factory = capture
        first = await client.exchange(PCM, 'conversation')
        self.assertEqual(first.text, 'Offline answer?')
        self.assertTrue(first.follow_up)
        second_wire = ProviderWire()
        self.engine.connect = second_wire.connect
        second = await client.exchange(PCM, 'conversation')
        self.assertTrue(second.follow_up)
        rows = self.engine.db.list_recent_sessions_bounded()
        self.assertEqual(len(rows), 1)
        sid = rows[0]['id']
        messages = self.engine.db.get_messages(sid)
        self.assertEqual(sum(m.get('display_kind') == 'native_audio' for m in messages), 2)
        self.assertEqual(sum(m.get('display_kind') == 'native_audio_semantic_summary' for m in messages), 0)
        self.assertIn('Offline answer?', json.dumps(second_wire.sent))
        self.assertNotIn('Synthetic PCM qualification', json.dumps(second_wire.sent))
        self.assertEqual(len(memory_instances), 2)
        self.assertEqual(self.engine.db.get_session(sid)['profile_name'], self.profile)
        # Tell the operator the actual storage implementation, never rename it.
        print('ACTUAL_SESSION_DB', type(self.engine.db).__module__ + '.' + type(self.engine.db).__name__)
        self.assertEqual(memory_paths[0], memory_paths[1])
        print('ACTUAL_ONE_DB', memory_paths[0] == Path(self.engine.db.db_path).resolve())

    async def test_actual_factory_origin_and_device_history_isolation(self):
        from aiohttp import web
        from hermes_native_companion import create_app
        from test_protocol import KEY, native
        # Both bindings are synthetic; use the actual policy/session implementation.
        binding = {'device_id': 'second', 'satellite_id': 'assist_satellite.second',
                   'area_id': 'second_room', 'area_name': 'Second room'}
        self.engine.policy.bindings[('second', 'assist_satellite.second')] = binding
        bridge = EngineBridge(self.engine, profile=self.profile, device_id='device',
            satellite_id='assist_satellite.example',
            bindings=[['device', 'assist_satellite.example'], ['second', 'assist_satellite.second']])
        await self.runner.cleanup()
        self.runner = web.AppRunner(create_app(bridge, KEY))
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0, ssl_context=self.server_tls)
        await site.start()
        origin = 'https://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        client = native.NativeClient(self.session, origin, KEY, self.profile)
        first_origin = dict(device_id='device', satellite_id='assist_satellite.example', area_id='example')
        second_origin = dict(device_id='second', satellite_id='assist_satellite.second', area_id='second_room')
        for physical in (first_origin, second_origin, first_origin):
            self.engine.connect = ProviderWire().connect
            result = await client.exchange(PCM, 'shared_conversation', origin=physical)
            self.assertTrue(result.follow_up)
        rows = self.engine.db.list_recent_sessions_bounded()
        self.assertEqual(len(rows), 2)
        counts = {}
        for row in rows:
            receipt = json.loads(self.engine.db.get_session(row['id'])['origin_json'])
            counts[receipt['device_id']] = sum(m.get('display_kind') == 'native_audio'
                for m in self.engine.db.get_messages(row['id']))
            self.assertEqual(receipt['area_id'], 'example' if receipt['device_id'] == 'device' else 'second_room')
        self.assertEqual(counts, {'device': 2, 'second': 1})
        with self.assertRaises(native.NativeError):
            await client.exchange(PCM, 'shared_conversation', origin={**first_origin, 'area_id': 'forged'})
        self.assertEqual(self.engine.db.session_count(), 2)

    async def test_normal_session_contract_and_foreign_profile_scope(self):
        import hashlib
        default_db = self.home.parent.parent / 'state.db'
        before = hashlib.sha256(default_db.read_bytes()).hexdigest()
        from hermes_cli.plugins import _plugin_home_scope
        from hermes_state_registry import acquire
        from plugins.memory import load_memory_provider
        from hermes_cli.config import load_config_readonly
        foreign = self.home.parent / 'unrelated'
        foreign.mkdir()
        (foreign / 'config.yaml').write_text('{}\n')
        with _plugin_home_scope(foreign):
            with self.engine.host.scope_home():
                normal = acquire()
                try:
                    self.assertIs(type(normal), type(self.engine.db))
                    self.assertEqual(Path(normal.db_path).resolve(), Path(self.engine.db.db_path).resolve())
                    provider = load_memory_provider(load_config_readonly()['memory']['provider'])
                    # Normal memory-provider loading and native both select Mnemosyne;
                    # neither changes Hermes' session storage class into a memory store.
                    self.assertEqual(type(provider).__name__, 'MnemosyneMemoryProvider')
                finally:
                    normal.close()
            result = await self.real_bridge.exchange(PCM, self.real_bridge.ids('scope', 'scope_turn'))
            self.assertEqual(result[0], 'Offline answer?')
            from hermes_constants import get_hermes_home
            self.assertEqual(Path(get_hermes_home()).resolve(), foreign.resolve())
        self.assertFalse((foreign / 'state.db').exists())
        self.assertEqual(hashlib.sha256(default_db.read_bytes()).hexdigest(), before)

    async def test_actual_factory_cancel_dispatched_effect_no_retry(self):
        import threading
        started, release = threading.Event(), threading.Event()
        calls = []
        self.engine.policy.entities['light.example']['actions'] = ['turn_on']
        def network(args, **kwargs):
            calls.append(args)
            started.set()
            if not release.wait(10):
                raise TimeoutError('synthetic network timeout')
            return json.dumps({'success': True})
        self.engine.host.ctx.register_tool('ha_call_service', 'offline', {
            'name': 'ha_call_service', 'description': 'Synthetic effect NETWORK boundary',
            'parameters': {'type': 'object', 'properties': {k: {'type': 'string'} for k in
                ('domain', 'service', 'entity_id', 'data')}, 'required': ['domain', 'service', 'entity_id', 'data'],
                'additionalProperties': False}}, network)
        class EffectWire(ProviderWire):
            async def send_json(self, event):
                if event['type'] != 'response.create':
                    return await super().send_json(event)
                self.sent.append(copy.deepcopy(event))
                await self.queue.put({'type': 'response.created', 'response': {'id': 'effect_response'}})
                await self.queue.put({'type': 'response.done', 'response': {'id': 'effect_response',
                    'status': 'completed', 'output': [{'type': 'function_call', 'name': 'home_control',
                    'call_id': 'effect_call', 'arguments': json.dumps({'entity_id': 'light.example',
                        'action': 'turn_on', 'data': {}})}]}})
        wire = EffectWire()
        self.engine.connect = wire.connect
        ids = self.real_bridge.ids('effect', 'effect_turn')
        task = asyncio.create_task(self.real_bridge.exchange(PCM, ids))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 5))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(self.engine.pending)
            with self.assertRaisesRegex(ValueError, 'busy'):
                await self.real_bridge.exchange(PCM, self.real_bridge.ids('effect', 'different_turn'))
            self.assertEqual(len(calls), 1)
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, *tuple(self.engine.pending), return_exceptions=True)
        with self.assertRaisesRegex(ValueError, 'replayed'):
            await self.real_bridge.exchange(PCM, ids)
        self.assertEqual(len(calls), 1)
        messages = self.engine.db.get_messages(self.engine.db.list_recent_sessions_bounded()[0]['id'])
        self.assertTrue(any('Effects may be uncertain' in str(m) for m in messages))
        self.assertFalse(any(m.get('role') == 'assistant' and m.get('content') == 'Offline answer?' for m in messages))

    async def test_packaged_cli_real_factory_tls_turn(self):
        import fcntl
        import socket
        executable = os.environ.get('HERMES_NATIVE_PACKAGED_PYTHON')
        if not executable:
            self.skipTest('installed wheel interpreter not supplied')
        from test_protocol import KEY, native
        root = Path(self.tmp.name)
        options, credential = root / 'factory.json', root / 'credential'
        options.write_text(json.dumps({'policy_path': str(self.home / 'policy.json')}))
        with (self.home / 'config.yaml').open('a') as config:
            config.write('plugins:\n  enabled:\n    - ' + self.plugin_name + '\n')
        credential.write_text(KEY)
        for path in (options, credential):
            path.chmod(0o600)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        self.engine.db.close()
        # Actual packaged main(), loader, factory, TLS app and shutdown. Only
        # external catalog/provider networks are synthetic, as in other tests.
        script = '''import sys
from pathlib import Path
import hermes_native_companion.__main__ as cli
assert 'site-packages' in cli.__file__, cli.__file__
from unittest.mock import patch
from test_installed_engine import ProviderWire
original = cli.load_engine
def discovery(**kwargs):
    from hermes_cli.plugins import get_plugin_manager
    manager = get_plugin_manager()
    loaded = [p for p in manager._plugins.values() if getattr(p.module, 'create_engine', None)]
    assert len(loaded) == 1
    loaded[0].module.get_ctx().register_tool('mcp__homeassistant__ha_get_state', 'offline', {
        'name': 'mcp__homeassistant__ha_get_state', 'description': 'Synthetic catalog network',
        'parameters': {'type': 'object', 'properties': {'entity_id': {'type': 'string'}},
            'required': ['entity_id'], 'additionalProperties': False}},
        lambda args, **kw: '{}')
def selected(*args, **kwargs):
    engine = original(*args, **kwargs)
    engine.connect = ProviderWire().connect
    return engine
with patch('tools.mcp_tool_discovery.discover_mcp_tools', side_effect=discovery), patch.object(cli, 'load_engine', selected):
    cli.main()
'''
        process = await asyncio.create_subprocess_exec(executable, '-c', script,
            '--home', str(self.home), '--profile', self.profile, '--engine-plugin', self.plugin_name,
            '--factory-options', str(options), '--device-id', 'device',
            '--satellite-id', 'assist_satellite.example', '--credential-file', str(credential),
            '--tls-cert', str(root / 'cert.pem'), '--tls-key', str(root / 'key.pem'),
            '--exclusive-lock', str(root / 'owner.lock'), '--port', str(port),
            env={k: v for k, v in {**os.environ, 'PYTHONPATH': str(Path(__file__).parent)}.items()
                 if k not in ('HERMES_NATIVE_TEST_PATHS', 'HERMES_NATIVE_TEST_PLUGIN')},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        origin = 'https://127.0.0.1:' + str(port)
        try:
            for _ in range(100):
                if process.returncode is not None:
                    _, error = await process.communicate()
                    self.fail(error.decode()[-3000:])
                try:
                    async with self.session.get(origin + '/v1/native/capabilities',
                            headers={'Authorization': 'Bearer ' + KEY}) as response:
                        if response.status == 200:
                            break
                except Exception:
                    pass
                await asyncio.sleep(.1)
            else:
                self.fail('packaged CLI did not become ready')
            final = await native.NativeClient(self.session, origin, KEY, self.profile).exchange(PCM, 'packaged')
            self.assertEqual(final.text, 'Offline answer?')
            with (root / 'owner.lock').open('a') as lock:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            if process.returncode is None:
                process.terminate()
            _, errors = await asyncio.wait_for(process.communicate(), 20)
        self.assertEqual(process.returncode, 0, errors.decode()[-3000:])
        with (root / 'owner.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    async def test_public_factory_declared_auth_and_origin_rejection(self):
        # Actual SDK identifies the installed shim and manifest before auth/network.
        from hermes_cli.plugin_provider_requests import credentialed_provider_request
        with self.assertRaises(PermissionError):
            credentialed_provider_request('openai-codex', 'POST', 'https://api.openai.com/v1/realtime/client_secrets')
        with self.engine.host.scope_home():
            with self.assertRaisesRegex(PermissionError, 'Refusing to send'):
                self.module.signed_request('POST', 'https://untrusted.invalid/client_secrets')
        self.assertEqual(self.engine.db.session_count(), 0)

    async def test_actual_factory_requires_completed_item_not_added(self):
        original = self.wire.send_json
        blocked = asyncio.Event()
        async def send(event):
            if event['type'] == 'conversation.item.create':
                await self.wire.queue.put({'type': 'conversation.item.added', 'item': copy.deepcopy(event['item'])})
                blocked.set()
                return
            await original(event)
        self.wire.send_json = send
        task = asyncio.create_task(self.real_bridge.exchange(PCM, self.real_bridge.ids('added', 'added')))
        await asyncio.wait_for(blocked.wait(), 5)
        await asyncio.sleep(.05)
        self.assertFalse(task.done())
        sid = self.engine.sessions.open(self.real_bridge.ids('added', 'added'))[0]
        self.assertFalse(any(m.get('display_kind') == 'native_audio_semantic_summary'
                             for m in self.engine.db.get_messages(sid)))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        rows = self.engine.db.list_recent_sessions_bounded()
        messages = self.engine.db.get_messages(rows[0]['id'])
        self.assertEqual(messages[-1]['display_metadata']['status'], 'interrupted')
        self.assertFalse(any(m.get('display_kind') == 'native_audio_semantic_summary' for m in messages))

    async def test_actual_factory_wrong_profile(self):
        with self.assertRaises(ValueError):
            EngineBridge(self.engine, profile='other', device_id='device', satellite_id='assist_satellite.example')

    async def test_actual_factory_provider_catalog_before_pcm(self):
        self.wire.bad_catalog = True
        with self.assertRaises(ValueError):
            await self.real_bridge.exchange(PCM, self.real_bridge.ids('catalog', 'catalog'))
        self.assertFalse(any(e['type'] == 'input_audio_buffer.append' for e in self.wire.sent))

    async def test_actual_factory_late_ack_cancel_no_final(self):
        self.wire.late_ack = True
        ids = self.real_bridge.ids('late', 'late')
        task = asyncio.create_task(self.real_bridge.exchange(PCM, ids))
        for _ in range(200):
            if any(e['type'] == 'conversation.item.create' and e['item']['type'] == 'function_call_output' for e in self.wire.sent):
                break
            await asyncio.sleep(.01)
        self.assertFalse(task.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        sid = self.engine.sessions.open(ids)[0]
        messages = self.engine.db.get_messages(sid)
        self.assertFalse(any(m.get('display_kind') == 'native_audio_semantic_summary' for m in messages))
        self.assertEqual(messages[-1]['display_metadata']['status'], 'interrupted')
