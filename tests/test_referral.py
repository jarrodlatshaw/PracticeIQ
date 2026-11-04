from decimal import Decimal
import unittest
from practiceiq.referral import analyze_source

SOURCE, CLIENT, COMPETITOR = '1000000004', '1000000012', '1000000020'
EDGES = [{'from_npi': SOURCE, 'to_npi': CLIENT, 'patient_count': 60},
         {'from_npi': SOURCE, 'to_npi': COMPETITOR, 'patient_count': 140}]


class ReferralTests(unittest.TestCase):
    def run_analysis(self, edges=EDGES, **kwargs):
        options = dict(client_npis={CLIENT}, competitor_npis={COMPETITOR},
                       coverage_complete=True, collections_per_patient=1800)
        options.update(kwargs)
        return analyze_source(SOURCE, edges, **options)

    def test_example_produces_requested_scenarios(self):
        result = self.run_analysis()
        self.assertEqual(result['visible_client_edge_volume'], 60)
        self.assertEqual(result['visible_competitor_edge_volume'], 140)
        self.assertEqual(result['estimates']['leakage'], Decimal(140))
        self.assertEqual(result['estimates']['revenue']['base'], Decimal(25200))

    def test_missing_or_incomplete_data_does_not_become_zero_revenue(self):
        edges = [EDGES[0], {**EDGES[1], 'patient_count': None}]
        result = self.run_analysis(edges)
        self.assertEqual(result['missing_eligible_edge_counts'], 1)
        self.assertIsNone(result['estimates'])
        self.assertIsNone(self.run_analysis(coverage_complete=False)['estimates'])
        self.assertIsNone(self.run_analysis(collections_per_patient=None)['estimates']['revenue']['base'])

    def test_ambiguous_or_invalid_edges_are_rejected(self):
        for edges, extra in ((EDGES + EDGES[:1], {}),
                             ([{**EDGES[0], 'patient_count': -1}], {}),
                             (EDGES, {'competitor_npis': {CLIENT}})):
            with self.subTest(edges=edges, extra=extra), self.assertRaises(ValueError):
                self.run_analysis(edges, **extra)


if __name__ == '__main__':
    unittest.main()
