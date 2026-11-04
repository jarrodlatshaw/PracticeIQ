import csv
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from practiceiq.calculations import Scenarios, opportunity, weighted_score
from practiceiq.docgraph import stage
from practiceiq.identity import affiliation_evidence, normalize_npi

FIXTURE = Path(__file__).parent / "fixtures" / "virginia_docgraph.csv"


class IdentityTests(unittest.TestCase):
    def test_npi_checksum_and_format(self):
        self.assertEqual(normalize_npi(" 1234567893 "), "1234567893")
        for invalid in ("1234567890", "123456789", "123-456-7893", "0000000000", 1234567893):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalize_npi(invalid)

    def test_conservative_affiliation(self):
        self.assertEqual(affiliation_evidence(organization_npi_match=True), "high")
        self.assertEqual(affiliation_evidence(organization_npi_match=True, conflict=True), "conflict_review")
        self.assertEqual(affiliation_evidence(name_match=True, address_match=True, phone_match=True), "candidate_review")
        self.assertEqual(affiliation_evidence(name_match=True, address_match=True), "insufficient")


class CalculationTests(unittest.TestCase):
    def test_example_and_missing_benchmark(self):
        result = opportunity(200, 60, 1800)
        self.assertEqual(result["leakage"], Decimal(140))
        self.assertEqual(result["revenue"], {"low": Decimal(12600), "base": Decimal(25200), "high": Decimal(37800)})
        self.assertIsNone(opportunity(200, 60, None)["revenue"]["base"])

    def test_invalid_inputs(self):
        for args in ((10, 11, 100), (-1, 0, 1), ("NaN", 0, 0), (10, 0, -1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                opportunity(*args)
        with self.assertRaises(ValueError):
            Scenarios(low=Decimal("0.2"), base=Decimal("0.1"))

    def test_score_availability(self):
        result = weighted_score({"flow": 80, "distance": None}, {"flow": 3, "distance": 1})
        self.assertEqual(result["score"], 80)
        self.assertEqual(result["coverage"], 0.75)
        self.assertIsNone(weighted_score({"flow": 80, "distance": None}, {"flow": 1, "distance": 3})["score"])
        with self.assertRaises(ValueError):
            weighted_score({"flow": 101}, {"flow": 1})


class ImportTests(unittest.TestCase):
    def test_synthetic_virginia_fixture_and_reimport(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "stage.csv"
            info = stage(FIXTURE, output, "synthetic", "2024")
            self.assertEqual(info["rows"], 2)
            with output.open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(sum(int(r["PATIENT_COUNT"]) for r in rows), 200)
            self.assertEqual(rows[0]["TO_NPI"], "1000000012")
            with self.assertRaises(ValueError):
                stage(FIXTURE, output, "synthetic", "2024")

    def test_bad_or_duplicate_rows_leave_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "bad.csv", Path(tmp) / "out.csv"
            for text in ("FROM_NPI,TO_NPI,PATIENT_COUNT\n1000000004,1000000012,\n",
                         "FROM_NPI,TO_NPI,PATIENT_COUNT\n1000000004,1000000012,3\n1000000004,1000000012,3\n",
                         "FROM_NPI,TO_NPI,PATIENT_COUNT\n1000000004,1000000012,3\n1000000004,1000000020,5,extra\n"):
                source.write_text(text)
                with self.assertRaises(ValueError):
                    stage(source, out, "test", "2024")
                self.assertFalse(out.exists())

class GeographyTests(unittest.TestCase):
    def test_radius_and_coordinates(self):
        from practiceiq.geography import distance_miles, within_radius
        self.assertEqual(distance_miles(37.54, -77.44, 37.54, -77.44), 0)
        # Roughly 69 miles per degree of latitude near Richmond.
        self.assertTrue(68 < distance_miles(37.54, -77.44, 38.54, -77.44) < 70)
        self.assertTrue(within_radius(37.54, -77.44, 38.54, -77.44, 70))
        self.assertFalse(within_radius(37.54, -77.44, 38.54, -77.44, 68))
        with self.assertRaises(ValueError):
            distance_miles(91, 0, 0, 0)
        with self.assertRaises(ValueError):
            within_radius(0, 0, 0, 0, -1)


if __name__ == "__main__":
    unittest.main()
