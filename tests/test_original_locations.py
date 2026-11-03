"""Location normalization regressions; no network or Flask dependency."""
import ast
import datetime
import math
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import place_database

def load_functions():
    scope = dict(re=re, math=math, datetime=datetime, swedish_places=place_database)
    for node in ast.parse((ROOT / "app.py").read_text()).body:
        if isinstance(node, ast.FunctionDef):
            node.decorator_list = []
        elif not (isinstance(node, ast.Assign) and all(
                isinstance(t, ast.Name) and t.id.isupper() for t in node.targets)):
            continue
        try:
            exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), scope)
        except NameError:
            pass
    return scope

class OriginalLocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = load_functions()

    def test_multiple_originals_and_untrusted_host(self):
        raw = {"source_links": [
            {"url": "https://arbetsformedlingen.se/platsbanken/annonser/31633292"},
            {"url": "https://arbetsformedlingen.se/platsbanken/annonser/31633310"},
            {"url": "https://evil.example/annonser/31699999"}]}
        self.assertEqual(self.f["_linked_jobsearch_ids"](raw), ["31633292", "31633310"])

    def test_brief_is_read(self):
        ad = {"headline": "Betongarbetare", "brief": "Arbetsort: Halmstad",
              "source_links": [{"url": "https://arbetsformedlingen.se/platsbanken/annonser/31633292"}]}
        job = self.f["parse_external"](ad)
        self.assertEqual(job["description"], ad["brief"])
        self.assertEqual(job["city"], "Halmstad")

    def test_original_city_and_municipality(self):
        for field in ("workplace_address", "workplace_addresses"):
            address = {"municipality": "Järfälla"}
            raw = {field: [address] if field.endswith("es") else address}
            options = self.f["_location_options"](raw)
            self.assertEqual(options[0]["city"], "Järfälla")

    def test_away_assignment_stays_excluded(self):
        job = {"title": "Betongare sökes till traktamenteuppdrag!",
               "description": "Projekt på annan ort"}
        self.assertEqual(self.f["reject_reason"](job), "Arbete på annan ort / traktamenteuppdrag")
        self.assertIsNone(self.f["score_job"](job))

if __name__ == "__main__":
    unittest.main()
