"""Opt-in proof that qualification uses the immutable official Hermes runtime.

Set HERMES_NATIVE_QUALIFIED_CORE to the existing official install root. This
checks import origins and the API boundary without starting a gateway/provider.
"""
import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('HERMES_NATIVE_QUALIFIED_CORE'),
                     'official runtime path not supplied')
class OfficialRuntimeBoundary(unittest.TestCase):
    def test_core_origins_are_official_not_experimental(self):
        import hermes_cli.plugins_context as context
        import hermes_state
        import agent.prompt_builder as prompt
        import tools.registry as tools
        from hermes_cli.version_info import get_version_info
        root = Path(os.environ['HERMES_NATIVE_QUALIFIED_CORE']).resolve(strict=True)
        for module in (context, hermes_state, prompt, tools):
            self.assertTrue(Path(module.__file__).resolve().is_relative_to(root), module.__file__)
        self.assertEqual(get_version_info().base_version, '0.23.1')
        self.assertTrue(callable(context.PluginContext.dispatch_tool))
        # No assertion that a native registry exists: create_engine is our
        # package API and load_engine explicitly documents the private seam.

    def test_ordinary_api_rejects_audio_without_a_request(self):
        from gateway.platforms.api_server import _normalize_multimodal_content
        with self.assertRaisesRegex(ValueError, '^unsupported_content_type:'):
            _normalize_multimodal_content([{
                'type': 'input_audio',
                'input_audio': {'format': 'wav', 'data': 'AA=='},
            }])
        self.assertEqual(_normalize_multimodal_content('Explicit text'), 'Explicit text')
