import unittest
from practiceiq.existing_practices import adapt_practice, parse_npis


class ExistingPracticeTests(unittest.TestCase):
    def test_explicit_format_and_provenance(self):
        row = {"practice_id": "VA-123", "practice_name": "Synthetic Richmond Practice",
               "npis": '["1000000004", "1000000012"]', "npi_count": 2,
               "latitude": 37.54, "longitude": -77.44, "geocode_quality": "example"}
        result = adapt_practice(row, npi_format="json_array")
        self.assertEqual(result["practice_id"], "VA-123")
        self.assertEqual(result["location"]["longitude"], -77.44)
        self.assertEqual(result["npi_candidates"][0]["status"], "requires_review")
        self.assertEqual(result["npi_candidates"][0]["evidence"], "medical_practices.npis")
        self.assertEqual(parse_npis("1000000004", format="single"), ["1000000004"])
        self.assertEqual(parse_npis("1000000004, 1000000012", format="comma_separated"),
                         ["1000000004", "1000000012"])

    def test_observed_single_npi_row_preserves_existing_location_and_phone(self):
        row = {"practice_id": "sample-id", "npis": "1000000004", "npi_count": 1,
               "taxonomy_codes": "101YM0800X", "phone": "7572268126.0",
               "latitude": 36.89, "longitude": -76.29, "location": "sample-ewkb"}
        result = adapt_practice(row, npi_format="single")
        self.assertEqual(result["npi_candidates"][0]["npi"], "1000000004")
        self.assertEqual(result["taxonomy_codes_raw"], "101YM0800X")
        self.assertEqual(result["location"]["phone"], "7572268126.0")
        self.assertEqual(result["location"]["location"], "sample-ewkb")

    def test_observed_semicolon_format_and_count(self):
        row = {"practice_id": "sample-multi", "npis": "1710624440;1811621519", "npi_count": 2,
               "taxonomy_codes": "101YM0800X;101YP2500X;261QM0801X",
               "location_sources": "NPPES_PRIMARY;NPPES_SECONDARY"}
        result = adapt_practice(row, npi_format="semicolon_separated")
        self.assertEqual([x["npi"] for x in result["npi_candidates"]], ["1710624440", "1811621519"])
        self.assertEqual(result["npi_count_status"], "match")
        self.assertEqual(result["taxonomy_codes_raw"], row["taxonomy_codes"])
        self.assertEqual(result["location"]["location_sources"], row["location_sources"])
        row["npi_count"] = 3
        self.assertEqual(adapt_practice(row, npi_format="semicolon_separated")["npi_count_status"], "mismatch")
        row["npi_count"] = 1.5
        self.assertEqual(adapt_practice(row, npi_format="semicolon_separated")["npi_count_status"], "invalid_reported_count")
        row["npis"] = None
        self.assertEqual(adapt_practice(row, npi_format="semicolon_separated")["npi_count_status"], "unavailable")
        with self.assertRaises(ValueError):
            parse_npis("1710624440;", format="semicolon_separated")

    def test_missing_is_not_empty_and_invalid_data_is_rejected(self):
        self.assertIsNone(parse_npis(None, format="json_array"))
        self.assertIsNone(parse_npis("", format="json_array"))
        self.assertEqual(parse_npis("[]", format="json_array"), [])
        for value, fmt in (("1000000004,1000000012", "single"), ("1000000004", "json_array"), ('[1000000004]', "json_array"),
                           ("1000000004,1000000004", "comma_separated"), ("1000000004", "guess")):
            with self.subTest(value=value, fmt=fmt), self.assertRaises(ValueError):
                parse_npis(value, format=fmt)
        for row in ({"practice_id": ""}, {"practice_id": "x", "latitude": 1},
                    {"practice_id": "x", "latitude": 91, "longitude": 0}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                adapt_practice(row, npi_format="json_array")


if __name__ == "__main__":
    unittest.main()
