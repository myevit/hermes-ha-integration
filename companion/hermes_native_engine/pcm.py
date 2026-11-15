"""PCM conversion extracted from the qualified backend, without its service code."""
def resample_pcm16_16k_to_24k(pcm):
    import audioop
    out, _state = audioop.ratecv(pcm, 2, 1, 16000, 24000, None)
    return out
