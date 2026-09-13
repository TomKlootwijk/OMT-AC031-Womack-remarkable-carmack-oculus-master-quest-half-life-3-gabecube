"""Reject replay artifacts and misleading empty-cache measurements."""
import csv
import io
import unittest
from scripts.probe_cache_residency import GROUPS,PASSES,parse_measurement,summarize_observations


def csv_output(group,counts,passes=1):
    out = io.StringIO()
    writer = csv.writer(out,quoting=csv.QUOTE_ALL)
    writer.writerow(('ID','Process ID','Kernel Name','Metric Name','Metric Unit','Metric Value'))
    for name,value in zip((*GROUPS[group]['metrics'],PASSES),(*counts,passes)):
        writer.writerow(('0','123',GROUPS[group]['kernel']+'()',name,'pass' if name==PASSES else 'sector',value))
    return out.getvalue()


class CacheResidencyMetrics(unittest.TestCase):
    def test_warm_cache_requires_one_profiler_pass(self):
        self.assertEqual(parse_measurement(csv_output('texture_l1',(75,25)),'texture_l1')['hit_pct'],75)
        for group,counts in (('texture_l1',(75,25)),('texture_l2_hit',(75,))):
            for passes in (0,2,3,4):
                with self.subTest(group=group,passes=passes),self.assertRaises(ValueError):
                    parse_measurement(csv_output(group,counts,passes),group)

    def test_missing_nonfinite_duplicate_and_empty_texture_counts_fail(self):
        for counts in ((0,0),('NaN',25),(-1,25)):
            with self.subTest(counts=counts),self.assertRaises(ValueError):
                parse_measurement(csv_output('texture_l1',counts),'texture_l1')
        with self.assertRaises(ValueError):
            parse_measurement('profiler returned no metrics','texture_l1')
        output = csv_output('texture_l1',(75,25))
        with self.assertRaises(ValueError):
            parse_measurement(output+output.splitlines()[-1]+'\n','texture_l1')

    def test_independent_l2_counts_never_claim_a_same_launch_hit_rate(self):
        self.assertEqual(len(GROUPS),7)
        for group in GROUPS:
            if group == 'texture_l1':
                continue
            for count in (0,123):
                with self.subTest(group=group,count=count):
                    result = parse_measurement(csv_output(group,(count,)),group)
                    self.assertEqual(result['counter_value'],count)
                    self.assertNotIn('hit_pct',result)
                    self.assertFalse(result['same_launch_hit_rate_available'])

    def test_l2_summary_retains_only_independently_measured_counter_statistics(self):
        group = 'global_l2_miss'
        observations = [parse_measurement(csv_output(group,(count,)),group) for count in (0,7,14)]
        summary = summarize_observations(group,observations)
        self.assertEqual(summary['counter_median'],7)
        self.assertEqual(summary['counter_range'],[0,14])
        self.assertNotIn('hit_pct_median',summary)
        self.assertFalse(summary['same_launch_hit_rate_available'])


if __name__ == '__main__':
    unittest.main()
