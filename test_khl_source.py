import datetime as dt
import unittest
from khl_source import normalize, _unwrap

class TestKHL(unittest.TestCase):
    def test_nested_event(self):
        obj = {'event': {'id': 123, 'team_a': {'id': 1, 'name': 'Ак Барс'}, 'team_b': {'id': 2, 'name': 'СКА'}, 'start_at': '2026-10-19T19:00:00+03:00'}}
        result = normalize(obj)
        self.assertEqual(result['sport'], 'KHL')
        self.assertEqual(result['home'], 'Ак Барс')
        self.assertEqual(result['away'], 'СКА')
        self.assertEqual(result['date'], '2026-10-19T16:00:00+00:00')
    def test_legacy_flat(self):
        self.assertEqual(normalize({'id': 4, 'home': 'A', 'away': 'B', 'start_time': 1792440000})['id'], '4')
    def test_unknown_schema(self):
        self.assertIsNone(normalize({'event': {'unknown': 1}}))
    def test_unwrap(self):
        self.assertEqual(_unwrap({'data': {'events': [{'event': {'id': 1}}]}})[0]['event']['id'], 1)

if __name__ == '__main__':
    unittest.main()
