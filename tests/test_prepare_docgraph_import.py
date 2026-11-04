from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from practiceiq.prepare_docgraph_import import prepare

class DocgraphImportTests(unittest.TestCase):
    def test_staged_import_and_bad_input(self):
        with TemporaryDirectory() as d:
            root=Path(d); source=root/'edges.csv'; output=root/'out.sql'
            source.write_text('FROM_NPI,TO_NPI,PATIENT_COUNT,TRANSACTION_COUNT\n1000000004,1000000012,60,70\n')
            result=prepare(source,output,year=2024,version='synthetic',synthetic=True)
            self.assertEqual(result['rows'],1)
            self.assertIn('SYNTHETIC - NOT DOCGRAPH',output.read_text())
            self.assertIn("'staged',true",output.read_text())
            source.write_text('FROM_NPI,TO_NPI,PATIENT_COUNT\n1000000004,1000000012,-1\n')
            with self.assertRaises(ValueError):prepare(source,root/'bad.sql',year=2024,version='bad')
            self.assertFalse((root/'bad.sql').exists())

if __name__ == '__main__': unittest.main()
