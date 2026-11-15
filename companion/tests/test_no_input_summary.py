"""Generated descriptions must never stand in for user speech."""
import unittest
from types import SimpleNamespace
from hermes_native_engine.engine import NativeLoop, Sessions
from hermes_native_engine.capabilities import FINISH_TOOL

class NoInputSummary(unittest.TestCase):
    def test_terminal_has_no_summary(self):
        self.assertEqual(set(FINISH_TOOL['parameters']['properties']), {'answer', 'followup'})
        self.assertEqual(NativeLoop.structured_final('{"answer":"OK","followup":false}'), {'answer':'OK','followup':False})
    def test_summary_rejected(self):
        with self.assertRaises(ValueError):
            NativeLoop.structured_final('{"answer":"OK","followup":false,"input_summary":"Invented words"}')
    def test_legacy_summary_not_replayed(self):
        obj = object.__new__(Sessions)
        obj.db = SimpleNamespace(get_messages=lambda sid: [
            {'role':'user','content':'Invented words','display_metadata':{'kind':'same_model_semantic_derivative'}},
            {'role':'assistant','content':'Actual answer','display_metadata':{}}])
        history = Sessions.history(obj, 'test')
        self.assertEqual(len(history), 1)
        self.assertNotIn('Invented words', str(history))

if __name__ == '__main__':
    unittest.main()
