"""Two bounded read-only REST operations; profile secrets remain host-owned.

The finite capability dispatcher selects the paths, never the model. No default
HA origin or auth path exists. Standard HASS_URL/HASS_TOKEN use Hermes secret scope.
"""
import asyncio
from urllib.parse import urlsplit


async def _api_json(method, path, timeout, payload=None):
    import aiohttp
    from agent.secret_scope import get_secret
    origin = get_secret('HASS_URL', '') or ''
    token = get_secret('HASS_TOKEN', '') or ''
    parsed = urlsplit(origin)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or not token):
        raise ValueError('explicit profile HA origin and credential required')
    if not ((method == 'GET' and path.startswith('/api/history/period?')) or
            (method == 'POST' and path == '/api/services/weather/get_forecasts?return_response')):
        raise ValueError('read-only operation not granted')
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
        async with session.request(method, origin.rstrip('/') + path, json=payload,
                headers={'Authorization': 'Bearer ' + token}, allow_redirects=False) as response:
            if response.status != 200:
                raise ValueError('HA read unavailable')
            if response.content_length is not None and response.content_length > 1024 * 1024:
                raise ValueError('HA read budget')
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise ValueError('HA read budget')
            import json
            return json.loads(body)


def _run_async(coro):
    # Called only from the awaited capability worker, never the owning event loop.
    return asyncio.run(coro)
