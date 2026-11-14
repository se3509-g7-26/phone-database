"""Numerical regression cases for the dependency-free EDA calculations."""
import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from explore import correlation,coverage,display_split,markdown_table,paired_bootstrap,pearson,quantile,ram_levels,ranks,summary
from explore_report import edge_sentence,word,write_report


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

    def test_display_split_puts_threshold_in_large_group_and_skips_missing(self):
        rows=[dict(brand=b,display_in=d,ram=r,price=p) for b,d,r,p in
              [('A',5.0,1,100),('A',6.9,2,200),('B',5.5,3,250),('B',7.0,1,150),
               ('A',10.1,2,300),('B',8.0,12,1500),('B',None,4,400)]]
        result=display_split(rows,7.0)
        self.assertEqual(result['display_missing'],1)
        self.assertEqual((result['phone_sized']['n'],result['large_screen']['n']),(3,3))
        self.assertEqual(result['large_screen_by_brand'],{'A':1,'B':2})
        self.assertAlmostEqual(result['phone_sized']['spearman'],1)
        self.assertEqual(display_split(rows,20)['large_screen']['n'],0)

    def test_ram_levels_split_screens_and_mark_thin_levels(self):
        rows=[dict(ram=2,price=p,display_in=d) for p,d in [(100,5.0),(200,6.0),(300,10.1),(400,None)]]
        rows.append(dict(ram=8,price=900,display_in=6.5))
        two,eight=ram_levels(rows,dict(min_joint=3,large_display_in=7.0))
        self.assertEqual((two['ram'],two['n'],two['median'],two['q1'],two['q3']),(2,4,250,175,325))
        self.assertTrue(two['eligible'])
        self.assertEqual((two['phone_n'],two['phone_median'],two['phone_eligible']),(2,150,False))
        self.assertEqual((eight['n'],eight['eligible'],eight['phone_n']),(1,False,1))

    def test_summary_of_empty_group_has_no_statistics(self):
        self.assertEqual(summary([]),dict(n=0,mean=None,median=None,p95=None,min=None,max=None))
        self.assertEqual(summary([3,1,2])['median'],2)

    def test_markdown_table_formats_missing_flags_and_floats(self):
        table=markdown_table([dict(a=None,b=True,c=1.23456,d=7)],['a','b','c','d'])
        self.assertEqual(table.splitlines()[-1],'| NA | yes | 1.235 | 7 |')

    def test_edge_sentence_names_every_brand(self):
        annual=[dict(brand='A',year=2010,price_n=5,catalog_n=8,eligible=False)]
        text=edge_sentence(annual,dict(brands=['A','B']),2010,'left')
        self.assertEqual(text,'At the 2010 left edge: A 5/8 usable prices (fails the rule), B no retained entries.')
        self.assertEqual((word(7),word(23)),('seven','23'))

    def test_queries_bind_every_value(self):
        for path in sorted((ROOT/'sql/queries').glob('m4_*.sql')):
            sql=path.read_text()
            self.assertNotRegex(sql,r'\{|%s|\?',path.name)
            self.assertTrue(re.search(r':[a-z_]+',sql),path.name)

    def test_report_regenerates_from_committed_results(self):
        results=json.loads((ROOT/'docs/m4/results.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);shutil.copytree(ROOT/'sql',tmp/'sql');(tmp/'docs').mkdir()
            write_report(results,tmp)
            self.assertEqual((tmp/'docs/eda_report.md').read_text(encoding='utf-8'),
                             (ROOT/'docs/eda_report.md').read_text(encoding='utf-8'))


if __name__=='__main__':unittest.main()
