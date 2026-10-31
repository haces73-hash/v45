import unittest
import place_database as places

class SwedishPlacesTest(unittest.TestCase):
 def test_dataset_size(self):
  self.assertEqual(len(places.MUNICIPALITIES),290)
  self.assertGreaterEqual(sum(map(len,places.LOCALITIES.values())),2000)
 def test_known_distant_places(self):
  for name in ("Borgholm","Skellefteå","Karlskrona"):
   self.assertIsNotNone(places.coordinates(name))
 def test_municipality_genitive(self):
  self.assertEqual(places.find_in_title("Park- och anläggningsarbetare till gata/park, Borgholms kommun"),"borgholm")
  self.assertEqual(places.find_in_title("Markarbetare sökes till vår kund i Skellefteå"),"skellefteå")
  self.assertEqual(places.find_in_title("Väg- och anläggningsarbetare – Karlskrona"),"karlskrona")
 def test_codes(self):
  self.assertEqual(places.municipality_from_code("1380"),"Halmstad")
 def test_unknown_is_not_halmstad(self):
  self.assertIsNone(places.coordinates("påhittad-ort-xyz"))
 def test_labeled_description(self):
  self.assertEqual(places.find_labeled_workplace("Arbetsort: Borgholm. Start omgående."),"borgholm")

if __name__=="__main__":
 unittest.main()
