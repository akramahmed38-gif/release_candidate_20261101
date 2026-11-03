from pathlib import Path
import json,tempfile,shutil,unittest
from source_review import ReviewRegistry
from source_preview import render
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.registry=ReviewRegistry()
 def test_fixed_pool_excludes_holds_and_gold_fields(self):
  self.assertGreater(len(self.registry.records),21)
  self.assertTrue(all(not r['hold_reason'] and not r['normal_runtime_eligible'] for r in self.registry.records))
  self.assertTrue(all(not ({'Test_ID','Expected_Answer','Critical_Facts'}&set(r)) for r in self.registry.records))
 def test_positive_source_identity_and_locator(self):
  r=self.registry.records[0];self.assertTrue(self.registry.source_ok(r));self.assertIsInstance(r['locator']['line_start'],int)
  body=render({**r,'fact_id':r['record_id']});self.assertIn(r['source_sha256'],body);self.assertIn('Original lines',body)
 def test_disposable_source_edit_invalidates(self):
  r=self.registry.records[0]
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);dest=root/'source_files'/r['source_document'];dest.parent.mkdir(parents=True);original=self.registry.root
   shutil.copy2(original/'source_files'/r['source_document'],dest)
   try:
    self.registry.root=root;self.assertTrue(self.registry.source_ok(r));dest.write_bytes(dest.read_bytes()+b'\nSYNTHETIC CHANGE');self.assertFalse(self.registry.source_ok(r))
   finally:self.registry.root=original
if __name__=='__main__':unittest.main()
