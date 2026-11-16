"""Real HA STT platform and conversation boundary; no provider or device calls."""
from unittest.mock import AsyncMock, patch
import pytest
from homeassistant.components import stt
from homeassistant.helpers import entity_registry as er
from custom_components.hermes_conversation.const import (
    CONF_CONTINUED_CONVERSATION_MODE, DOMAIN,
    FOLLOW_UP_MODE_ALWAYS, FOLLOW_UP_MODE_AUTO, FOLLOW_UP_MODE_OFF,
)
from custom_components.hermes_conversation.native import CaptureStore, NativeResult
from custom_components.hermes_conversation.stt import HermesNativeCapture
from runtime_tests.test_activity_runtime import _setup, _process


async def test_real_native_setup_capture_conversation_unload(hass_ready, hermes_api):
    hass = hass_ready
    hermes_api.native['voice-example'] = hermes_api.root
    entry = await _setup(hass, hermes_api)
    hass.config_entries.async_update_entry(entry, options={
        'profile': 'voice-example', 'profile_route': 'native',
        'native_audio_enabled': True,
        'native_audio_origin': 'https://example.org',
        'native_audio_key': 'synthetic-test-token-not-real-' + 'x' * 40,
    })
    await hass.async_block_till_done(wait_background_tasks=True)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id('stt', DOMAIN, entry.entry_id + '_native_capture')
    runtime = hass.data[DOMAIN][entry.entry_id]
    capture = HermesNativeCapture(entry.entry_id, runtime['capture_store'])
    metadata = stt.SpeechMetadata(language='en', format=stt.AudioFormats.WAV,
        codec=stt.AudioCodecs.PCM, bit_rate=stt.AudioBitRates.BITRATE_16,
        sample_rate=stt.AudioSampleRates.SAMPLERATE_16000,
        channel=stt.AudioChannels.CHANNEL_MONO)
    async def stream():
        yield b'\0\0' * 160
    result = await capture.async_process_audio_stream(metadata, stream())
    assert result.result == stt.SpeechResultState.SUCCESS
    before = hermes_api.count_paths('/v1/chat/completions')
    with patch.object(runtime['native_client'], 'exchange', AsyncMock(return_value=NativeResult('Ready?', True))) as exchange:
        response = await _process(hass, entry, result.text)
        assert response.continue_conversation is False  # Default entry policy overrides the model.
        assert response.response.speech['plain']['speech'] == 'Ready?'
        exchange.assert_awaited_once()
        replay = await _process(hass, entry, result.text)
        assert replay.response.as_dict()['response_type'] == 'error'
    assert hermes_api.count_paths('/v1/chat/completions') == before
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


@pytest.mark.parametrize('mode', [FOLLOW_UP_MODE_OFF, FOLLOW_UP_MODE_ALWAYS, FOLLOW_UP_MODE_AUTO])
@pytest.mark.parametrize('model_flag', [False, True])
@pytest.mark.parametrize('reply,question,silent', [
    ('Ready?', True, False),
    ('Done.', False, False),
    ('**Ready?**', True, False),
    ('Ready? Done.', False, False),
    ('NO_REPLY', False, True),
])
async def test_native_follow_up_matches_real_entry_policy(
    hass_ready, hermes_api, mode, model_flag, reply, question, silent,
):
    hass = hass_ready
    hermes_api.native['voice-example'] = hermes_api.root
    entry = await _setup(hass, hermes_api)
    hass.config_entries.async_update_entry(entry, options={
        'profile': 'voice-example', 'profile_route': 'native', 'native_audio_enabled': True,
        'native_audio_origin': 'https://example.org', 'native_audio_key': 'x' * 40,
        CONF_CONTINUED_CONVERSATION_MODE: mode,
    })
    await hass.async_block_till_done(wait_background_tasks=True)
    runtime = hass.data[DOMAIN][entry.entry_id]
    before = len(hermes_api.chat_requests)
    with patch.object(runtime['native_client'], 'exchange', AsyncMock(
        return_value=NativeResult(reply, model_flag),
    )) as exchange:
        result = await _process(hass, entry, runtime['capture_store'].put(b'\0\0'))
        exchange.assert_awaited_once()
    expected = not silent and (mode == FOLLOW_UP_MODE_ALWAYS or
                              mode == FOLLOW_UP_MODE_AUTO and question)
    assert result.continue_conversation is expected
    assert result.response.as_dict()['response_type'] != 'error'
    assert bool(result.response.speech) is not silent
    assert len(hermes_api.chat_requests) == before
    hermes_api.chat_response = reply
    ordinary = await _process(hass, entry, 'Synthetic explicit text')
    assert ordinary.continue_conversation is result.continue_conversation
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_error_burns_capture_without_text_retry(hass_ready, hermes_api):
    from custom_components.hermes_conversation.native import NativeError
    hass = hass_ready
    hermes_api.native['voice-example'] = hermes_api.root
    entry = await _setup(hass, hermes_api)
    hass.config_entries.async_update_entry(entry, options={
        'profile': 'voice-example', 'profile_route': 'native', 'native_audio_enabled': True,
        'native_audio_origin': 'https://example.org', 'native_audio_key': 'x' * 40,
    })
    await hass.async_block_till_done(wait_background_tasks=True)
    runtime = hass.data[DOMAIN][entry.entry_id]
    token = runtime['capture_store'].put(b'\0\0' * 160)
    before = len(hermes_api.chat_requests)
    with patch.object(runtime['native_client'], 'exchange', AsyncMock(side_effect=NativeError('native_exchange_failed'))) as exchange:
        failed = await _process(hass, entry, token)
        assert failed.response.as_dict()['response_type'] == 'error'
        replay = await _process(hass, entry, token)
        assert replay.response.as_dict()['response_type'] == 'error'
        exchange.assert_awaited_once()
    assert len(hermes_api.chat_requests) == before
    # Explicit text remains a separate supported route, never an automatic replay.
    result = await _process(hass, entry, 'Synthetic explicit text')
    assert result.response.speech['plain']['speech'] == 'synthetic response'
    assert len(hermes_api.chat_requests) == before + 1
    assert token not in str(hermes_api.chat_requests)
    assert await hass.config_entries.async_unload(entry.entry_id)


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
