import unittest
from test_original_locations import load_functions

class AdditionalRolesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load_functions()

    def job(self,title,text="Praktiskt arbete med upplärning."):
        return dict(id="test",title=title,company="Test",description=text,
                    license_status="not_required",employment_extent="full_time")

    def test_direct_roles_and_plural(self):
        for title,area in (("Möbelmontör","Snickeri och träproduktion"),
                           ("Processoperatörer","Industri och produktion"),
                           ("Assemblör","Industri och produktion"),
                           ("Byggmedhjälpare","Bygg och anläggning")):
            job=self.f["score_job"](self.job(title))
            self.assertEqual(job["cv_match_area"],area)

    def test_generic_operator_needs_actual_role_evidence(self):
        job=self.f["score_job"](self.job("Skicklig operatör till Halmstad",
            "Vi söker nu en tekniskt intresserad processoperatör till vår kund i Halmstad."))
        self.assertEqual(job["cv_match_area"],"Industri och produktion")
        self.assertIsNone(self.f["score_job"](self.job("IT-operatör",
            "Vi arbetar med andra kunder, bland annat processoperatörer.")))

if __name__ == "__main__":
    unittest.main()
