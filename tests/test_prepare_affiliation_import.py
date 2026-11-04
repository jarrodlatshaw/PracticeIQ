import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from practiceiq.prepare_affiliation_import import prepare


class ImportPreparationTests(unittest.TestCase):
    def test_escapes_text_and_refuses_changed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, manifest, output = root/'candidates.csv', root/'manifest.json', root/'import.sql'
            fields = ['practice_id','clinician_npi','cms_group_pac_id','cms_group_name','cms_address_1',
                      'cms_city','cms_zip','evidence','clinician_practice_count','group_practice_count']
            with data.open('w',newline='',encoding='utf-8') as stream:
                writer = csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(practice_id='p1',clinician_npi='1000000004',cms_group_pac_id='g1',
                    cms_group_name="O'Brien Clinic",cms_address_1='1 Main',cms_city='Richmond',cms_zip='23220',
                    evidence='exact match',clinician_practice_count='1',group_practice_count='1'))
            meta = {'cms_files':[{'sha256':'a'*64}], 'practice_export_sha256':'b'*64,
                    'nppes_source_sha256':'c'*64, 'candidate_file_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
                    'candidate_rows':1, 'matching_method':'test'}
            manifest.write_text(json.dumps(meta))
            self.assertFalse(prepare(data,manifest,output)['executed'])
            self.assertIn("O''Brien Clinic",output.read_text())
            self.assertIn('SET LOCAL standard_conforming_strings = on;',output.read_text())
            data.write_text('changed')
            with self.assertRaises(ValueError):
                prepare(data,manifest,root/'bad.sql')
            self.assertFalse((root/'bad.sql').exists())


if __name__ == '__main__':
    unittest.main()
