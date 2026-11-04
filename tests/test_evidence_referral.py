from datetime import date
from decimal import Decimal
import unittest
from practiceiq.evidence_referral import analyze_evidence

SRC, A, B = '1000000004', '1000000012', '1000000020'
CANDIDATES = [dict(practice_id='client', clinician_npi=A, cms_group_pac_id='g1'),
              dict(practice_id='competitor', clinician_npi=B, cms_group_pac_id='g2')]
EDGES = [dict(from_npi=SRC, to_npi=A, patient_count=60),
         dict(from_npi=SRC, to_npi=B, patient_count=140)]
REVIEWS = [{**c, 'decision':'approved', 'reviewer':'test-reviewer', 'effective_from':date(2024,1,1)} for c in CANDIDATES]

class EvidenceReferralTests(unittest.TestCase):
    def run_case(self, candidates=CANDIDATES, reviews=REVIEWS, edges=EDGES, **kwargs):
        settings = dict(client_practice_id='client', competitor_practice_ids={'competitor'},
                        as_of=date(2024,12,31), coverage_complete=True, collections_per_patient=1800)
        settings.update(kwargs)
        return analyze_evidence(SRC, edges, candidates, reviews, **settings)

    def test_reviewed_fixture_produces_expected_opportunity(self):
        r = self.run_case()
        self.assertEqual(r['estimates']['leakage'], Decimal(140))
        self.assertEqual(r['estimates']['revenue'], {'low':Decimal(12600),'base':Decimal(25200),'high':Decimal(37800)})

    def test_candidates_and_missing_data_never_imply_zero_opportunity(self):
        r = self.run_case(reviews=[])
        self.assertEqual(r['unreviewed_candidate_count'], 2)
        self.assertIsNone(r['estimates'])
        self.assertIsNone(self.run_case(edges=[EDGES[0], {**EDGES[1], 'patient_count':None}])['estimates'])
        self.assertIsNone(self.run_case(coverage_complete=False)['estimates'])
        self.assertIsNone(self.run_case(reviews=[REVIEWS[0], {**REVIEWS[1], 'effective_to':date(2024,6,1)}])['estimates'])

    def test_conflicting_practice_assignments_and_unknown_review_rejected(self):
        extra = dict(practice_id='competitor', clinician_npi=A, cms_group_pac_id='g3')
        with self.assertRaises(ValueError):
            self.run_case(candidates=CANDIDATES+[extra], reviews=REVIEWS+[{**extra,'decision':'approved','reviewer':'r','effective_from':date(2024,1,1)}])
        with self.assertRaises(ValueError):
            self.run_case(reviews=REVIEWS+[{**REVIEWS[0], 'cms_group_pac_id':'unknown'}])

if __name__ == '__main__':
    unittest.main()
