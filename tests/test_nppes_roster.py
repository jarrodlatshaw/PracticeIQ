import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from practiceiq.nppes_roster import FIELDS, STATE, stage_virginia


class VirginiaRosterTests(unittest.TestCase):
    def test_only_individuals_with_virginia_primary_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / 'source.zip'
            output = Path(tmp) / 'roster.csv'
            content = io.StringIO(newline='')
            writer = csv.DictWriter(content, fieldnames=FIELDS)
            writer.writeheader()
            for npi, entity, state in (('1000000004', '1', 'VA'),
                                       ('1000000012', '2', 'VA'),
                                       ('1000000020', '1', 'MD')):
                writer.writerow({'NPI': npi, 'Entity Type Code': entity, STATE: state})
            with zipfile.ZipFile(archive_path, 'w') as archive:
                archive.writestr('source.csv', content.getvalue())
            report = stage_virginia(archive_path, 'source.csv', output)
            self.assertEqual((report['rows_scanned'], report['virginia_individual_records']), (3, 1))
            with output.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]['NPI'], '1000000004')
            with self.assertRaises(ValueError):
                stage_virginia(archive_path, 'source.csv', output)


if __name__ == '__main__':
    unittest.main()
