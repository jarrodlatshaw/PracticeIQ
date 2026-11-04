import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from practiceiq.cms_affiliations import match


def write(path, fields, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class CmsMatchingTests(unittest.TestCase):
    def test_exact_evidence_dedup_and_review_status(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            p, c, cms, out = (root / n for n in ('practices.csv', 'candidates.csv', 'cms.csv', 'out.csv'))
            write(p, ['practice_id','practice_name','legal_name','address_1','city','zip5'], [
                {'practice_id':'p1','practice_name':'EXAMPLE CLINIC LLC','legal_name':'EXAMPLE CLINIC LLC',
                 'address_1':'1 MAIN ST','city':'RICHMOND','zip5':'23220'}])
            write(c, ['practice_id','clinician_npi'], [{'practice_id':'p1','clinician_npi':'1000000004'}])
            base = {'State':'VA','NPI':'1000000004','org_pac_id':'123','Facility Name':'Example Clinic, LLC',
                    'adr_ln_1':'1 MAIN ST','ZIP Code':'232201234','City/Town':'Richmond'}
            other = {**base, 'Facility Name':'DIFFERENT GROUP'}
            write(cms, list(base), [base, base, other])
            report = match(p, c, [cms], out)
            self.assertEqual(report['unique_candidate_links'], 1)
            with out.open(newline='',encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]['review_status'], 'candidate_requires_review')
            with self.assertRaises(ValueError):
                match(p, c, [cms], out)


if __name__ == '__main__':
    unittest.main()
