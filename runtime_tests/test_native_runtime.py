"""Real HA STT platform and conversation boundary; no provider or device calls."""
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.components import stt
from homeassistant.helpers import entity_registry as er
from custom_components.hermes_conversation.const import DOMAIN
from custom_components.hermes_conversation.native import CaptureStore
from custom_components.hermes_conversation.stt import HermesNativeCapture
from runtime_tests.test_activity_runtime import _setup, _process


async def test_real_native_setup_capture_conversation_unload(hass_ready, hermes_api, tmp_path):
    import aiohttp
    from aiohttp import web
    import base64, io, wave, ssl, ipaddress
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    hass = hass_ready
    entry = await _setup(hass, hermes_api)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True).sign(key, hashes.SHA256()))
    cp, kp = tmp_path / 'cert.pem', tmp_path / 'key.pem'
    cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    kp.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cp, kp)
    tls_site = web.TCPSite(hermes_api._runner, '127.0.0.1', 0, ssl_context=server_context)
    await tls_site.start()
    port = tls_site._server.sockets[0].getsockname()[1]
    trust = ssl.create_default_context(cafile=str(cp))
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=trust)) as session:
        with patch('custom_components.hermes_conversation.async_get_clientsession', return_value=session):
            hass.config_entries.async_update_entry(entry,
                data={**entry.data, 'port': port, 'use_ssl':True, 'verify_ssl':True},
                options={**entry.options, 'native_audio_enabled':True, 'continued_conversation_mode':'auto'})
            await hass.async_block_till_done(wait_background_tasks=True)
            registry = er.async_get(hass)
            assert registry.async_get_entity_id('stt', DOMAIN, entry.entry_id + '_native_capture')
            runtime = hass.data[DOMAIN][entry.entry_id]
            assert 'native_client' not in runtime
            capture = HermesNativeCapture(entry.entry_id, runtime['capture_store'])
            metadata = stt.SpeechMetadata(language='en', format=stt.AudioFormats.WAV,
                codec=stt.AudioCodecs.PCM, bit_rate=stt.AudioBitRates.BITRATE_16,
                sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
                channel=stt.AudioChannels.CHANNEL_MONO)
            pcm = b'\0\0' * 160
            async def stream(): yield pcm
            result = await capture.async_process_audio_stream(metadata, stream())
            assert result.result == stt.SpeechResultState.SUCCESS
            before = hermes_api.count_paths('/v1/chat/completions')
            hermes_api.chat_response = 'Ready?'
            hermes_api.chat_session_id = 'native-normal-session'
            response = await _process(hass, entry, result.text)
            assert response.continue_conversation
            assert response.response.speech['plain']['speech'] == 'Ready?'
            payload = hermes_api.chat_requests[-1]
            assert payload['model'] == 'gpt-realtime-2.1'
            part = payload['messages'][-1]['content'][0]
            with wave.open(io.BytesIO(base64.b64decode(part['input_audio']['data']))) as wav:
                assert wav.readframes(wav.getnframes()) == pcm
            assert result.text not in str(payload)
            replay = await _process(hass, entry, result.text)
            assert replay.response.as_dict()['response_type'] == 'error'
            assert hermes_api.count_paths('/v1/chat/completions') == before + 1
            assert await hass.config_entries.async_unload(entry.entry_id)
            assert entry.entry_id not in hass.data.get(DOMAIN, {})
    await tls_site.stop()


@pytest.mark.parametrize('pcm', [b'', b'x', b'x' * (1024 * 1024 + 2)])
async def test_real_capture_bounds(pcm):
    capture = HermesNativeCapture('test', CaptureStore())
    metadata = stt.SpeechMetadata(language='en', format=stt.AudioFormats.WAV,
        codec=stt.AudioCodecs.PCM, bit_rate=stt.AudioBitRates.BITRATE_16,
        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
        channel=stt.AudioChannels.CHANNEL_MONO)
    async def stream(): yield pcm
    result = await capture.async_process_audio_stream(metadata, stream())
    assert result.result == stt.SpeechResultState.ERROR


async def test_capture_inherits_ha_ceiling_not_private_ten_seconds():
    import asyncio
    capture = HermesNativeCapture('offline-duration', CaptureStore())
    metadata = stt.SpeechMetadata(language='en', format=stt.AudioFormats.WAV,
        codec=stt.AudioCodecs.PCM, bit_rate=stt.AudioBitRates.BITRATE_16,
        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
        channel=stt.AudioChannels.CHANNEL_MONO)
    pcm = b'\0\0' * 16000 * 15  # Fifteen seconds, 16-bit mono at 16 kHz.
    async def stream():
        await asyncio.sleep(15.05)
        yield pcm
    result = await capture.async_process_audio_stream(metadata, stream())
    assert result.result == stt.SpeechResultState.SUCCESS
    assert capture.store.take(result.text) == pcm
