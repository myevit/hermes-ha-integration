"""Public policy/library regressions; no engine substitutes or live calls."""
import copy
import json
from pathlib import Path
import unittest

from hermes_native_engine.policy import Policy


def fixture():
    return json.loads((Path(__file__).parents[1] / 'hermes_native_engine' / 'examples' /
                       'policy.example.json').read_text())


class FinitePolicy(unittest.TestCase):
    def test_approval_must_be_boolean(self):
        for invalid in ('false', 'true', 1, [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Policy({**fixture(), 'approved': invalid})

    def test_no_default_switch_grants(self):
        data = fixture()
        data['entities']['switch.example'] = dict(name='Example outlet', area_id='example_room', actions=['turn_on'])
        with self.assertRaises(ValueError):
            Policy(data)
        policy = Policy(data, reviewed_switches=['switch.example'])
        self.assertEqual(policy.entities['switch.example']['actions'], ['turn_on'])
        with self.assertRaises(ValueError):
            Policy(data, reviewed_switches=['switch.*'])

    def test_select_options_are_explicit_and_cannot_widen_policy(self):
        from jsonschema.exceptions import ValidationError
        data = fixture()
        data['entities']['select.example'] = dict(name='Example selector', area_id='example_room',
            actions=['select_option'], arguments={'select_option': {'option': {'type': 'string', 'enum': ['example_one']}}})
        with self.assertRaises(ValueError):
            Policy(data)
        policy = Policy(data, select_options={'select.example': ['example_one', 'example_two']})
        policy.action({'entity_id': 'select.example', 'action': 'select_option', 'data': {'option': 'example_one'}})
        with self.assertRaises(ValidationError):
            policy.action({'entity_id': 'select.example', 'action': 'select_option', 'data': {'option': 'example_two'}})
        self.assertNotEqual(policy.digest, Policy(fixture()).digest)

    def test_fictional_example_is_not_approved(self):
        self.assertFalse(Policy(fixture()).approved)

    def test_unknown_and_dangerous_services_denied(self):
        for target, action in [('lock.example', 'unlock'), ('script.example', 'turn_on'),
                               ('light.example', 'toggle'), ('light.example', '*')]:
            data = fixture()
            data['entities'][target] = dict(name='Example', area_id='example_room', actions=[action])
            with self.subTest(target=target, action=action), self.assertRaises(ValueError):
                Policy(data)

    def test_unsupported_memory_adapter_refused_before_database(self):
        from hermes_native_engine.factory import create_engine
        from unittest.mock import patch
        with patch('importlib.metadata.version', return_value='3.1.0'), patch('hermes_state.SessionDB') as db:
            with self.assertRaisesRegex(ValueError, 'qualified memory dependency'):
                create_engine(None, 'unused', signed_request=None)
            db.assert_not_called()

    def test_policy_cannot_wildcard_binding(self):
        data = fixture()
        data['bindings'][0]['satellite_id'] = '*'
        with self.assertRaises(ValueError):
            Policy(data)

    def test_terminal_duplicate_keys_and_nonfinite_rejected(self):
        from hermes_native_engine.engine import NativeLoop
        for value in ('{"answer":"a","answer":"b","input_summary":"x","followup":false}',
                      '{"answer":"a","input_summary":"x","followup":NaN}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                NativeLoop.structured_final(value)


if __name__ == '__main__':
    unittest.main()
