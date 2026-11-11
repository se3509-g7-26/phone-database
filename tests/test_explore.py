"""Numerical regression cases for the dependency-free EDA calculations."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from explore import correlation,coverage,paired_bootstrap,pearson,quantile,ranks


class ExploreTests(unittest.TestCase):
    def test_tied_spearman_uses_average_ranks(self):
        self.assertEqual(ranks([10,20,20,40]),[1,2.5,2.5,4])
        result=correlation([dict(ram=x,price=y) for x,y in [(1,1),(2,3),(2,2),(4,4)]])
        self.assertAlmostEqual(result['spearman'],3/math.sqrt(10))

    def test_pearson_constant_and_short_are_undefined(self):
        self.assertIsNone(pearson([1,1,1],[2,3,4]))
        self.assertIsNone(pearson([1,2],[3,4]))
        self.assertAlmostEqual(pearson([1,2,3],[6,4,2]),-1)

    def test_percentile_interpolates_and_keeps_singleton(self):
        self.assertEqual(quantile([0,10,20,30],.25),7.5)
        self.assertEqual(quantile([17],.95),17)
        self.assertIsNone(quantile([],.5))

    def test_coverage_counts_unpriced_models_in_denominator(self):
        rows=[dict(brand='A',year=2020,price=v,ram=1 if v else None) for v in [100,200,None,None]]
        params=dict(min_models=4,min_prices=2,min_coverage=.5)
        row=coverage(rows,params)[0]
        self.assertEqual((row['catalog_n'],row['price_n'],row['joint_n']),(4,2,2))
        self.assertTrue(row['eligible'])
        self.assertEqual(row['median'],150)
        self.assertFalse(coverage(rows,dict(params,min_coverage=.51))[0]['eligible'])

    def test_paired_blocks_preserve_constant_contrast(self):
        params=dict(seed=42,bootstrap_reps=100)
        self.assertEqual(paired_bootstrap([12]*7,params,2),[12,12])
        values=[-60,0,105,-55,-60,-10,-19.08]
        a=paired_bootstrap(values,params,2)
        self.assertEqual(a,paired_bootstrap(values,params,2))
        self.assertLess(a[0],0);self.assertGreater(a[1],0)
        with self.assertRaises(ValueError):paired_bootstrap([1,2],params,2)


if __name__=='__main__':unittest.main()
