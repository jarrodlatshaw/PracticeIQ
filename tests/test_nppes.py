import csv
from pathlib import Path
import tempfile
import unittest
import zipfile
from practiceiq.nppes import stage


class NppesTests(unittest.TestCase):
    def test_extracts_selected_entity_types_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source.csv', Path(temp) / 'selected.csv'
            source.write_text('NPI,Entity Type Code,Provider First Name,Provider Organization Name (Legal Business Name)\n'
                              '1000000004,1,Jane,\n1000000012,2,,Example Clinic\n1000000038,1,Other,\n')
            report = stage(source, output, {'1000000004', '1000000012', '1000000020'})
            self.assertEqual((report['requested'], report['matched'], report['not_found']), (3, 2, 1))
            with output.open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['Entity Type Code'] for r in rows], ['1', '2'])
            self.assertEqual(report['unmatched_npis'], ['1000000020'])
            with self.assertRaises(ValueError):
                stage(source, output, {'1000000004'})

    def test_reads_explicit_zip_member_without_extracting(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source.zip', Path(temp) / 'selected.csv'
            with zipfile.ZipFile(source, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('data.csv', 'NPI,Entity Type Code\n1000000004,1\n')
                archive.writestr('other.txt', 'unused')
            report = stage(source, output, {'1000000004'}, member='data.csv')
            self.assertEqual(report['matched'], 1)
            self.assertFalse((Path(temp) / 'data.csv').exists())
            with self.assertRaises(KeyError):
                stage(source, Path(temp) / 'missing.csv', {'1000000004'}, member='absent.csv')

    def test_rejects_duplicate_and_invalid_entity_without_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / 'source.csv', Path(temp) / 'out.csv'
            for content in ('NPI,Entity Type Code\n1000000004,1\n1000000004,1\n',
                            'NPI,Entity Type Code\n1000000004,9\n', 'NPI\n1000000004\n'):
                source.write_text(content)
                with self.assertRaises(ValueError):
                    stage(source, output, {'1000000004'})
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
