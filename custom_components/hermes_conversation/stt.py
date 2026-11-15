"""HA-owned PCM capture adapter, not speech recognition or a listen controller."""
from __future__ import annotations

import asyncio
from homeassistant.components import stt
from .const import DOMAIN
from .native import MAX_PCM


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HermesNativeCapture(entry.entry_id, hass.data[DOMAIN][entry.entry_id]["capture_store"])])


class HermesNativeCapture(stt.SpeechToTextEntity):
    _attr_name = "Hermes native audio capture"

    def __init__(self, entry_id, store):
        self._attr_unique_id = entry_id + "_native_capture"
        self.store = store

    @property
    def supported_languages(self):
        return ["en"]

    @property
    def supported_formats(self):
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self):
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self):
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self):
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self):
        return [stt.AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(self, metadata, stream):
        pcm = bytearray()
        try:
            if not self.check_metadata(metadata):
                return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
            # HA owns VAD/listen duration; do not impose a private 10-second cap.
            async with asyncio.timeout(60):
                async for chunk in stream:
                    if type(chunk) is not bytes or len(chunk) % 2 or len(pcm) + len(chunk) > MAX_PCM:
                        return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
                    if chunk:
                        pcm.extend(chunk)
                    await asyncio.sleep(0)
            return stt.SpeechResult(self.store.put(bytes(pcm)), stt.SpeechResultState.SUCCESS)
        except asyncio.CancelledError:
            raise
        except Exception:
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        finally:
            pcm.clear()
