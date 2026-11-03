"""B 1.0: entitlement-specific licences and duplicate recruitment ads."""
import unittest
from test_original_locations import load_functions

class B10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load_functions()

    def test_mandatory_b_optional_c(self):
        for text in ("Du har B-körkort, C-kort är meriterande.",
                     "B-körkort krävs, C-kort är meriterande.",
                     "B-körkort är meriterande, C-kort krävs."):
            for required in (True, False):
                ad = {"driving_license_required": required, "description": {"text": text}}
                self.assertEqual(self.f["_license_decision"](ad, "", text)[0], "required")

    def test_optional_b_under_heading(self):
        text = "Meriterande:\nHeta arbeten\nSäkra lyft\nHLR\nB-körkort"
        ad = {"driving_license_required": True, "description": {"text": text}}
        self.assertEqual(self.f["_license_decision"](ad, "", text)[0], "optional")

    def job(self, identifier, url, text=None):
        return {"id": identifier, "title": "Demontör | Lernia | Halmstad",
                "company": "LERNIA BEMANNING AB", "city": "Halmstad",
                "description": text or "Praktiskt arbete med demontering och montering. " * 8,
                "detail_check_status": "Fullständig annons från JobSearch",
                "application": {"url": url}}

    def test_shared_lernia_recruitment_id(self):
        a = self.job("31130435", "https://connect.lernia.se/jobs/7840551-demontor/applications/new")
        b = self.job("31130429", "https://www.lernia.se/jobb/halmstad-demontor-7840551/")
        self.assertEqual(len(self.f["_deduplicate_recruitment_jobs"]([a,b])), 1)

    def test_same_title_different_job_is_not_merged(self):
        a = self.job("1", "https://example.org/job/1")
        b = self.job("2", "https://example.org/job/2", "Ett annat uppdrag med andra arbetsuppgifter. " * 8)
        self.assertEqual(len(self.f["_deduplicate_recruitment_jobs"]([a,b])), 2)

    def test_short_summaries_are_not_text_duplicates(self):
        a = self.job("1", "https://example.org/job/1", "Kort sammanfattning")
        b = self.job("2", "https://example.org/job/2", "Kort sammanfattning")
        self.assertEqual(len(self.f["_deduplicate_recruitment_jobs"]([a,b])), 2)

if __name__ == "__main__":
    unittest.main()
