import datetime as dt
import unittest
from khl_source import normalize
from khl_history import completed

class KHLTests(unittest.TestCase):
    def test_finished_score(self):
        raw = {'event': {'id': 345, 'start_at': 1790000000000, 'team_a': {'id': 1, 'name': 'А'}, 'team_b': {'id': 2, 'name': 'Б'}, 'game_state_key': 'finished', 'score': '3:2'}}
        e = normalize(raw)
        self.assertEqual(e['status'], 'final')
        self.assertEqual((e['home_score'],e['away_score']), (3,2))
        self.assertIsNotNone(completed(e, now=dt.datetime(2027,1,1,tzinfo=dt.timezone.utc)))
    def test_not_started(self):
        raw = {'event': {'id': 345, 'start_at': 1790000000000, 'team_a': {'name': 'А'}, 'team_b': {'name': 'Б'}, 'game_state_key': 'not_yet_started', 'score': '0:0'}}
        self.assertIsNone(completed(normalize(raw), now=dt.datetime(2027,1,1,tzinfo=dt.timezone.utc)))
    def test_missing_score(self):
        raw = {'event': {'id': 345, 'start_at': 1790000000000, 'team_a': {'name': 'А'}, 'team_b': {'name': 'Б'}, 'game_state_key': 'finished', 'score': ''}}
        self.assertIsNone(completed(normalize(raw), now=dt.datetime(2027,1,1,tzinfo=dt.timezone.utc)))

if __name__ == '__main__': unittest.main()
