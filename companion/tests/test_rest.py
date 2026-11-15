"""Real loopback HA REST network seam; no Host or engine substitutes."""
import os
import unittest
from unittest.mock import patch
from aiohttp import web
from hermes_native_engine import rest


class RestReads(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redirect_target_called = False
        async def history(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer synthetic-read-only-fixture')
            response = web.StreamResponse(headers={'Content-Type': 'application/json'})
            await response.prepare(request)
            await response.write(b'[{"state":')
            import asyncio
            await asyncio.sleep(.05)
            await response.write(b'"synthetic"}]')
            await response.write_eof()
            return response
        async def redirect(request):
            raise web.HTTPFound('/ungranted')
        async def ungranted(request):
            self.redirect_target_called = True
            return web.json_response({})
        app = web.Application()
        app.router.add_get('/api/history/period', history)
        app.router.add_post('/api/services/weather/get_forecasts', redirect)
        app.router.add_get('/ungranted', ungranted)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        self.env = patch.dict(os.environ, {'HASS_URL': 'http://127.0.0.1:' + str(port),
                                          'HASS_TOKEN': 'synthetic-read-only-fixture'})
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        await self.runner.cleanup()

    async def test_chunked_history_is_complete_and_bounded(self):
        self.assertEqual(await rest._api_json('GET', '/api/history/period?filter_entity_id=sensor.example', 3),
                         [{'state': 'synthetic'}])

    async def test_forecast_redirect_does_not_forward_credential(self):
        with self.assertRaises(ValueError):
            await rest._api_json('POST', '/api/services/weather/get_forecasts?return_response', 3,
                                 {'entity_id': 'weather.example', 'type': 'daily'})
        self.assertFalse(self.redirect_target_called)
