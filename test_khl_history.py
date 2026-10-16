import datetime as dt
import unittest
from khl_history import completed, team_stats

class KHLHistoryTests(unittest.TestCase):
    def setUp(self):
        self.game = {'id':'42','date':'2026-10-01T15:00:00+00:00','home':'A','away':'B',
                     'home_id':'a','away_id':'b','status':'final','home_score':3,'away_score':2}
    def test_valid(self):
        self.assertEqual(completed(self.game)['home_score'],3)
    def test_pending(self):
        self.assertIsNone(completed({**self.game,'status':'pre'}))
    def test_missing_score(self):
        self.assertIsNone(completed({**self.game,'away_score':None}))
    def test_tied_score(self):
        self.assertIsNone(completed({**self.game,'away_score':3}))
    def test_stats(self):
        result = team_stats({'42':completed(self.game)})
        self.assertEqual(result['a']['wins'],1)
        self.assertEqual(result['b']['losses'],1)

if __name__ == '__main__':
    unittest.main()
