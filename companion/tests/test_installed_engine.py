"""Opt-in qualification against a separately installed native engine plugin.

No private plugin is distributed. Set HERMES_NATIVE_TEST_PLUGIN (directory),
HERMES_NATIVE_TEST_PROFILE (its genuine named profile), and PYTHONPATH for the
installed Hermes + memory dependencies. No real provider/MCP network is used.
"""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
                    'answer': 'Offline answer?', 'input_summary': 'Synthetic PCM qualification', 'followup': True})}]}})

    async def receive_json(self):
        return await self.queue.get()

    @contextlib.asynccontextmanager
    async def connect(self):
        yield self


@unittest.skipUnless(os.environ.get('HERMES_NATIVE_TEST_PLUGIN'), 'separate installed engine dependency not supplied')
class InstalledEngine(unittest.IsolatedAsyncioTestCase):
    """Runs inherited real TLS protocol cases with the ACTUAL plugin factory too."""
    async def asyncSetUp(self):
        # Protocol sets up TLS first. Replace only its inference boundary below.
        await protocol.Protocol.asyncSetUp(self)
        from hermes_cli.plugins import PluginManager, _plugin_home_scope
        from hermes_cli.plugins_manifest import parse_manifest_file
        self.profile = os.environ['HERMES_NATIVE_TEST_PROFILE']
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
        source = Path(os.environ['HERMES_NATIVE_TEST_PLUGIN'])
        manifest = parse_manifest_file(source / 'plugin.yaml', source, 'user', '')
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
        self.assertEqual(sum(m.get('display_kind') == 'native_audio_semantic_summary' for m in messages), 2)
        self.assertIn('Offline answer?', json.dumps(second_wire.sent))
        self.assertIn('Synthetic PCM qualification', json.dumps(second_wire.sent))
        self.assertEqual(len(memory_instances), 2)
        self.assertEqual(self.engine.db.get_session(sid)['profile_name'], self.profile)
        # Tell the operator the actual storage implementation, never rename it.
        print('ACTUAL_SESSION_DB', type(self.engine.db).__module__ + '.' + type(self.engine.db).__name__)
        self.assertEqual(memory_paths[0], memory_paths[1])
        print('ACTUAL_ONE_DB', memory_paths[0] == Path(self.engine.db.db_path).resolve())

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
