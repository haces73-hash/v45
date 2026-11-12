"""Multi-area search through the real Flask endpoint with mocked public ad services."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('multi_search_app', ROOT / 'app.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def ad(ident, city, title='Montör', **extra):
    raw = dict(id=ident, headline=title, employer={'name': 'Test '+ident+' AB'},
               description={'text': 'Vi söker dig till produktion och montering. Ingen erfarenhet krävs. Du får introduktion på arbetsplatsen och arbetar tillsammans med kollegor.'},
               driving_license_required=False, working_hours_type={'label':'Heltid'},
               workplace_address={'municipality':city,'municipality_code':module.SEARCH_MUNICIPALITIES[city]},
               webpage_url='https://arbetsformedlingen.se/platsbanken/annonser/'+ident)
    raw.update(extra)
    return raw

class MultiMunicipalityTests(unittest.TestCase):
    def setUp(self):
        self.client=module.app.test_client()
        self.seen=[]
        shared=ad('81000003','Halmstad',workplace_addresses=[
            {'municipality':'Halmstad','municipality_code':'1380'},
            {'municipality':'Laholm','municipality_code':'1381'}])
        self.ads={'1380':[ad('81000001','Halmstad','Snickerimedarbetare'),shared,ad('81000004','Göteborg')],
                  '1381':[ad('81000002','Laholm','Produktionsmedarbetare'),shared],
                  '1382':[]}
    def fetch(self,url,params=None,**kwargs):
        self.seen.append((url,params))
        if 'joblinks' in url:
            hits=[]
        else:
            hits=self.ads.get(params['municipality'],[])
        class Result:
            def raise_for_status(self):pass
            def json(self):return {'hits':hits}
        return Result()
    def search(self,query):
        with patch.object(module.requests,'get',side_effect=self.fetch),patch.object(module.requests,'post',side_effect=AssertionError('No mail')):
            r=self.client.get('/api/jobs?region=municipality&'+query)
        self.assertEqual(r.status_code,200)
        return r.get_json()
    def test_union_dedup_and_global_priority(self):
        result=self.search('city=Laholm&city=Halmstad&city=Laholm')
        self.assertEqual(result['municipalities'],['Halmstad','Laholm'])
        jobs=result['jobs']+result['needs_review']
        ids=[j['id'] for j in jobs]
        self.assertEqual(set(ids),{'81000001','81000002','81000003'})
        self.assertEqual(len(ids),3)
        shared=next(j for j in jobs if j['id']=='81000003')
        self.assertEqual(shared['search_municipalities'],['Halmstad','Laholm'])
        self.assertEqual({p['municipality'] for u,p in self.seen if '/search' in u},{'1380','1381'})
        self.assertTrue(result['search_complete'])
        self.assertEqual(result['jobs'],sorted(result['jobs'],key=lambda j:(j['priority'],-j['match_score'],j['id'])))
    def test_single_area_keeps_old_api_contract(self):
        r=self.search('city=Halmstad')
        self.assertEqual(r['city'],'Halmstad')
        self.assertNotIn('81000002',[j['id'] for j in r['jobs']+r['needs_review']])
    def test_empty_area_does_not_hide_other_area_results(self):
        r=self.search('city=Falkenberg&city=Laholm')
        self.assertIn('81000002',[j['id'] for j in r['jobs']+r['needs_review']])
    def test_invalid_selection_rejected_without_network(self):
        with patch.object(module.requests,'get',side_effect=AssertionError('No request expected')):
            self.assertEqual(self.client.get('/api/jobs?city=Unknown').status_code,400)
    def test_failed_source_is_not_reported_as_complete(self):
        original=self.fetch
        def failing(url,params=None,**kwargs):
            if '/search' in url and params['municipality']=='1381':
                raise module.requests.ConnectionError('offline')
            return original(url,params,**kwargs)
        with patch.object(module.requests,'get',side_effect=failing):
            r=self.client.get('/api/jobs?city=Halmstad&city=Laholm').get_json()
        self.assertFalse(r['search_complete'])
        self.assertTrue(r['errors'])
        self.assertIn('81000001',[j['id'] for j in r['jobs']+r['needs_review']])
    def test_all_eight_areas_are_searched(self):
        r=self.search('&'.join('city='+city for city in module.SEARCH_MUNICIPALITIES))
        self.assertEqual(r['municipalities'],list(module.SEARCH_MUNICIPALITIES))
        self.assertEqual({p['municipality'] for u,p in self.seen if '/search' in u},set(module.SEARCH_MUNICIPALITIES.values()))
    def test_part_time_is_excluded_in_both_selected_areas(self):
        for city,code,ident in [('Halmstad','1380','81000006'),('Laholm','1381','81000007')]:
            self.ads[code].append(ad(ident,city,working_hours_type={'label':'Deltid'}))
        r=self.search('city=Halmstad&city=Laholm')
        self.assertFalse({'81000006','81000007'} & {j['id'] for j in r['jobs']+r['needs_review']})
    def test_existing_mandatory_license_filter_applies_across_areas(self):
        self.ads['1381'].append(ad('81000005','Laholm',driving_license_required=True))
        r=self.search('city=Halmstad&city=Laholm')
        self.assertNotIn('81000005',[j['id'] for j in r['jobs']+r['needs_review']])

if __name__=='__main__':unittest.main()
