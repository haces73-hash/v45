import unittest
from test_original_locations import load_functions

class ExternalSummaryLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=load_functions()

    def fixtures(self):
        brief="Vi söker engagerade processoperatörer till vår anläggning i Halmstad. Du arbetar praktiskt i produktionen med kvalitetskontroller, processövervakning och noggrann dokumentation."
        summary={"headline":"Processoperatörer","brief":brief,"employer":{"name":"Test AB"}}
        original={"id":"12345678","headline":"Processoperatörer med säkerheten i fokus",
                  "employer":{"name":"Test AB"},"description":{"text":brief+"\nKrav: B-körkort."},
                  "driving_license_required":True,
                  "workplace_address":{"municipality_code":"1380","municipality":"Halmstad"}}
        return summary,original

    def test_unique_original_exposes_requirement(self):
        summary,original=self.fixtures()
        found=self.f["_matching_original_for_summary"](summary,[original],"Halmstad")
        self.assertEqual(found["id"],original["id"])
        self.assertEqual(self.f["_license_decision"](found,found["headline"],"")[0],"required")

    def test_ambiguous_or_wrong_employer_not_linked(self):
        summary,original=self.fixtures()
        f=self.f["_matching_original_for_summary"]
        self.assertIsNone(f(summary,[original,dict(original,id="87654321")],"Halmstad"))
        self.assertIsNone(f(dict(summary,employer={"name":"Annan AB"}),[original],"Halmstad"))

    def test_insufficient_evidence_or_other_area_not_linked(self):
        summary,original=self.fixtures()
        f=self.f["_matching_original_for_summary"]
        self.assertIsNone(f(dict(summary,brief="Kort text"),[original],"Halmstad"))
        self.assertIsNone(f(summary,[original],"Falkenberg"))
        self.assertIsNone(f(dict(summary,headline="Ett annat yrke"),[original],"Halmstad"))

if __name__=="__main__":
    unittest.main()
