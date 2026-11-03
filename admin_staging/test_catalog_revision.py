"""General metadata/locator tests; no policy approval or original edits."""
from pathlib import Path
import hashlib,json,sys,unittest,uuid
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'next_revision'))
from catalog_queries import declared_services,filter_records
from source_preview import render,SourcePreviewError

class Queries(unittest.TestCase):
 def test_generic_scope_metadata(self):
  for key,value in [('service_id','service_x'),('service_ids',['service_x']),('service_ids_json','["service_x"]'),('scopes_json','["service_x"]')]:
   with self.subTest(key=key):self.assertEqual(declared_services({key:value}),{'service_x'})
 def test_source_and_page_filter(self):
  rows=[{'source_id':'a','scopes_json':'["alpha"]'},{'source_id':'b','service_ids_json':'["beta"]'}]
  self.assertEqual(filter_records(rows,service='beta'),[rows[1]])
 def test_no_boolean_or_simulation_approval(self):
  self.assertEqual(filter_records([{'normal_runtime_eligible':True,'simulated_approval':True}],eligible=True),[])
 def test_language_views(self):
  rows=[{'english_test_view':'literal pending view'},{'arabic':'نص أصلي'},{'english_test_view':'held','quarantine_reason':'restricted'}]
  self.assertEqual(filter_records(rows,language='en_test'),[rows[0]])
  self.assertEqual(filter_records(rows,language='ar'),[rows[1]])
 def test_version_and_hold(self):
  digest='a'*64;row={'source_sha256':digest,'review_status':'restricted_hold'}
  self.assertEqual(filter_records([row],source_version=digest,review_status='restricted_hold'),[row])
  with self.assertRaises(ValueError):filter_records([row],source_version='partial')
 def test_malformed_metadata_is_not_a_service(self):self.assertEqual(declared_services({'scopes_json':'invalid'}),set())

class Sources(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.root=ROOT/'state'/('citation_tests_'+uuid.uuid4().hex[:10]);cls.root.mkdir(parents=True)
  cls.text=b'SYNTHETIC LOCATOR TEST\nsource-bound marker\nunrelated context\n'
  (cls.root/'test.md').write_bytes(cls.text)
  cls.fact={'fact_id':'F9999','source_document':'test.md','source_sha256':hashlib.sha256(cls.text).hexdigest(),'locator':{'line_start':2,'line_end':2},'review_status':'pending'}
 def test_exact_original_lines(self):
  result=render(self.fact,[self.root]);self.assertIn('source-bound marker',result);self.assertNotIn('unrelated context',result)
 def test_path_traversal(self):
  with self.assertRaises(SourcePreviewError):render({**self.fact,'source_document':'../outside.md'},[self.root])
 def test_version_mismatch(self):
  with self.assertRaises(SourcePreviewError):render({**self.fact,'source_sha256':'b'*64},[self.root])
 def test_unbounded_locator(self):
  with self.assertRaises(SourcePreviewError):render({**self.fact,'locator':{}},[self.root])
 def test_restricted_record(self):
  with self.assertRaises(SourcePreviewError):render({**self.fact,'quarantine_reason':'restricted'},[self.root])
 def test_positive_then_modified_source_with_unrelated_preserved(self):
  positive=render(self.fact,[self.root]);self.assertIn('source-bound marker',positive)
  changed=self.root/'changed.md';changed.write_bytes(self.text)
  fact={**self.fact,'source_document':'changed.md'}
  self.assertIn('source-bound marker',render(fact,[self.root]))
  changed.write_bytes(b'changed revision')
  with self.assertRaises(SourcePreviewError):render(fact,[self.root])
  self.assertIn('source-bound marker',render(self.fact,[self.root]))

if __name__=='__main__':unittest.main(verbosity=2)
