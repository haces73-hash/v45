"""Municipality eligibility: no radius inference."""
import unittest
from test_original_locations import load_functions

class MunicipalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load_functions()

    def test_all_eight_choices(self):
        self.assertEqual(set(self.f["SEARCH_MUNICIPALITIES"]), {
            "Halmstad", "Falkenberg", "Varberg", "Kungsbacka",
            "Laholm", "Hylte", "Helsingborg", "Göteborg"})

    def test_code_selects_municipality_not_nearby_city(self):
        raw = {"workplace_addresses": [
            {"municipality_code": "1380", "city": "Oskarström"},
            {"municipality_code": "1381", "city": "Laholm"}]}
        result = self.f["_municipality_addresses"](raw, "Halmstad")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["city"], "Oskarström")

    def test_label_fallback_and_conflicting_code(self):
        f = self.f["_municipality_addresses"]
        self.assertTrue(f({"workplace_address": {"municipality": "Halmstad"}}, "Halmstad"))
        self.assertFalse(f({"workplace_address": {
            "municipality": "Halmstad", "municipality_code": "1381"}}, "Halmstad"))

    def test_region_or_title_cannot_prove_municipality(self):
        f = self.f["_municipality_addresses"]
        self.assertFalse(f({"headline": "Montör i Halmstad",
                           "workplace_address": {"region": "Hallands län"}}, "Halmstad"))

if __name__ == "__main__":
    unittest.main()
