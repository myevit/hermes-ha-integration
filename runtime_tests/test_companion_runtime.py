"""Actual HA entry -> capture token -> verified TLS companion -> final/history/events.

The default case uses an explicit synthetic inference boundary. The optional
installed case uses genuine plugin loader/factory/context/DB/MemoryManager;
only provider and MCP network boundaries are synthetic (see companion tests).
"""
import asyncio
from contextlib import asynccontextmanager
import importlib
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from aiohttp import web
from homeassistant.components import conversation, stt
from custom_components.hermes_conversation.stt import HermesNativeCapture
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hermes_conversation.const import *
from custom_components.hermes_conversation.native import NativeClient
from runtime_tests.loopback import HermesLoopbackApi, API_KEY


@asynccontextmanager
async def loopback():
    api = HermesLoopbackApi()
    await api.start()
    try:
        yield api
    finally:
        await api.stop()


@pytest.mark.parametrize('installed', [False, True], ids=['protocol-network-boundary', 'installed-engine-factory'])
async def test_companion_entry_capture_tls_history_events(hass_ready, enable_custom_integrations, socket_enabled, installed):
    hass = hass_ready
    if installed and not os.environ.get('HERMES_NATIVE_TEST_PLUGIN'):
        pytest.skip('separate installed native engine dependency not supplied')
    for path in os.environ.get('HERMES_NATIVE_TEST_PATHS', '').split(os.pathsep):
        if path and path not in sys.path:
            sys.path.append(path)
    test_path = str(Path(__file__).resolve().parents[1] / 'companion' / 'tests')
    sys.path.insert(0, test_path)
    protocol = importlib.import_module('test_protocol')
    if installed:
        fixtures = importlib.import_module('test_installed_engine')
        fixture = fixtures.InstalledEngine()
    else:
        fixture = protocol.Protocol()
    await fixture.asyncSetUp()
    try:
        profile = fixture.profile if installed else fixture.bridge.profile
        if installed:
            from hermes_native_companion import create_app
            await fixture.runner.cleanup()
            fixture.runner = web.AppRunner(create_app(fixture.real_bridge, protocol.KEY))
            await fixture.runner.setup()
            site = web.TCPSite(fixture.runner, '127.0.0.1', 0, ssl_context=fixture.server_tls)
            await site.start()
            fixture.origin = 'https://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        async with loopback() as api:
            entry = MockConfigEntry(domain=DOMAIN, title='Offline native', entry_id='tls-native', data={
                CONF_HOST: '127.0.0.1', CONF_PORT: api.port, CONF_API_KEY: API_KEY,
                CONF_USE_SSL: False, "native_audio_enabled": True,
                "native_audio_origin": fixture.origin, "native_audio_key": protocol.KEY,
                CONF_PROFILE: profile, CONF_PROFILE_ROUTE: "native"})
            entry.add_to_hass(hass)
            def trusted_client(session, origin, key, expected_profile):
                # Test CA is injected, never ssl=False and never production trust changes.
                return NativeClient(fixture.session, origin, key, expected_profile)
            with patch('custom_components.hermes_conversation.NativeClient', side_effect=trusted_client):
                assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done(wait_background_tasks=True)
            data = hass.data[DOMAIN][entry.entry_id]
            agent_id = er.async_get(hass).async_get_entity_id('conversation', DOMAIN, entry.entry_id)
            events = []
            unsub = hass.bus.async_listen('hermes_conversation_activity', events.append)
            try:
                capture = HermesNativeCapture(entry.entry_id, data['capture_store'])
                metadata = stt.SpeechMetadata(language='en', format=stt.AudioFormats.WAV,
                    codec=stt.AudioCodecs.PCM, bit_rate=stt.AudioBitRates.BITRATE_16,
                    sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                    channel=stt.AudioChannels.CHANNEL_MONO)
                async def stream():
                    yield protocol.PCM
                captured = await capture.async_process_audio_stream(metadata, stream())
                assert captured.result == stt.SpeechResultState.SUCCESS
                token = captured.text
                first = await conversation.async_converse(hass, token, context=Context(), agent_id=agent_id, conversation_id=None)
                assert first.continue_conversation is True
                if installed:
                    fixture.engine.connect = fixtures.ProviderWire().connect
                second = await conversation.async_converse(hass, data['capture_store'].put(protocol.PCM),
                    context=Context(), agent_id=agent_id, conversation_id=first.conversation_id)
                assert second.conversation_id == first.conversation_id
                assert second.continue_conversation is True
                await hass.async_block_till_done()
                assert [e.data['status'] for e in events] == ['started', 'completed', 'started', 'completed']
                assert all(e.data['active_requests'] == 0 for e in events[1::2])
                assert protocol.KEY not in str([e.data for e in events])
                assert token not in str([e.data for e in events])
                if installed:
                    assert fixture.engine.db.session_count() == 1
                else:
                    assert len(fixture.bridge.calls) == 2
            finally:
                unsub()
            assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await fixture.asyncTearDown()
