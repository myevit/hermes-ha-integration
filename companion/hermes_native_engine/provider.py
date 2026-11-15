"""Subscription-only Talk auth subset, through Hermes's supported signing API.

Adapted from hermes-talk talk_auth.codex_request (MIT, TALK-LICENSE). This module
never resolves token files, refreshes credentials or falls back to metered keys.
The installed plugin shim supplies the signing function so Hermes can validate
its installed directory and requires_auth declaration without bypassing the SDK.
"""
import asyncio
import contextlib

from .policy import MODEL
from .talk_wire import CLIENT_SECRETS_URL, OPENAI_REALTIME_WS_URL, parse_client_secret


@contextlib.asynccontextmanager
async def subscription_connection(host, signed_request):
    import aiohttp
    # The credential scope is the genuine owner, not an implicit default profile.
    with host.scope_home():
        response = await asyncio.to_thread(signed_request, 'POST', CLIENT_SECRETS_URL,
            json={'session': {'type': 'realtime', 'model': MODEL, 'output_modalities': ['text']}},
            headers={'Content-Type': 'application/json'}, timeout=20)
    if response.status != 200:
        raise ValueError('subscription session refused')
    key, _ = parse_client_secret(response.json())
    del response
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
        async with session.ws_connect(OPENAI_REALTIME_WS_URL + '?model=' + MODEL,
                headers={'Authorization': 'Bearer ' + key}, max_msg_size=4*1024*1024) as ws:
            del key
            yield ws
