import unittest
from model import train, probability, wilson
from bot import timestamp
class ModelTests(unittest.TestCase):
    def test_small_sample_blocks(self):
        _,_,m=train([])
        self.assertFalse(m['approved']);self.assertIsNone(m['accuracy'])
    def test_prior(self):
        r,_,_=train([])
        self.assertGreater(probability(r,'A','B'),.5)
    def test_simultaneous_results_do_not_change_same_time_forecasts(self):
        games=[dict(date='2026-01-01',home_id='A',away_id='B',home_score=3,away_score=1),dict(date='2026-01-01',home_id='A',away_id='C',home_score=1,away_score=3)]
        r1,_,m1=train(games);r2,_,m2=train(list(reversed(games)))
        self.assertAlmostEqual(r1['A'],r2['A']);self.assertEqual(m1,m2)
    def test_interval(self):
        self.assertLess(wilson(6,6),.65);self.assertGreater(wilson(48,60),.5)
    def test_timestamp_normalization(self):
        self.assertEqual(timestamp('2026-10-16T10:00:00+03:00').hour,7)
if __name__=='__main__':unittest.main()
