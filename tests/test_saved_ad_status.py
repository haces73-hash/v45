import unittest
from types import SimpleNamespace
from test_original_locations import load_functions

class SavedAdStatusTests(unittest.TestCase):
    def setUp(self):
        self.f=load_functions()
        self.calls=[]

    def response(self,status=200,data=None,error=False):
        def get(url,**kw):
            self.calls.append(url)
            if error:raise RuntimeError("timeout")
            return SimpleNamespace(status_code=status,ok=status==200,json=lambda:data)
        self.f["requests"]=SimpleNamespace(get=get,RequestException=RuntimeError)

    def test_active_and_removed_flag(self):
        for removed,want in ((False,"active"),(True,"removed")):
            self.response(data={"id":"31451515","removed":removed})
            self.assertEqual(self.f["_saved_ad_status"]("31451515")["status"],want)

    def test_missing_source_is_removed(self):
        for code in (404,410):
            self.response(status=code)
            self.assertEqual(self.f["_saved_ad_status"]("31451515")["status"],"removed")

    def test_temporary_failure_is_not_deletion(self):
        for code in (403,429,500):
            self.response(status=code)
            self.assertEqual(self.f["_saved_ad_status"]("31451515")["status"],"unknown")
        self.response(error=True)
        self.assertEqual(self.f["_saved_ad_status"]("31451515")["status"],"unknown")

    def test_wrong_identity_and_arbitrary_url_not_trusted(self):
        self.response(data={"id":"99999999","removed":True})
        self.assertEqual(self.f["_saved_ad_status"]("31451515")["status"],"unknown")
        self.calls.clear()
        self.assertEqual(self.f["_saved_ad_status"]("https://example.org/job")["status"],"unknown")
        self.assertEqual(self.calls,[])

    def test_links_uses_jobtech_only(self):
        ident="a"*32
        self.response(data={"id":ident,"headline":"Jobb"})
        self.assertEqual(self.f["_saved_ad_status"]("links:"+ident)["status"],"active")
        self.assertEqual(self.calls,["https://links.api.jobtechdev.se/ad/"+ident])

if __name__=="__main__":
    unittest.main()
