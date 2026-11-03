"""Lifecycle story with genuine positive controls; no normal policy approvals."""
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'next_revision'))
import synthetic_store as store
import sqlite3
ACTOR='synthetic-lifecycle-test-actor'
def document(marker,english=True):
    views={'ar':{'marker':marker}}
    if english:views['en']={'marker':marker}
    return json.dumps({'title':'SYNTHETIC lifecycle test','fields':{'marker':marker},'views':views}).encode()
def publish(namespace):
    for action in ['submit','simulate_fidelity','simulate_currentness','publish_simulation']:store.transition(namespace,action,ACTOR)

class Lifecycle(unittest.TestCase):
 def test_connection_closed_after_transaction(self):
    with store.db() as connection:connection.execute('select 1').fetchone()
    with self.assertRaises(sqlite3.ProgrammingError):connection.execute('select 1')
 def test_complete_revision_story(self):
    a=store.new_revision(document('SYN-A'),ACTOR)['namespace'];b=store.new_revision(document('SYN-B'),ACTOR)['namespace']
    self.assertFalse(store.preview(a,'marker','en',ACTOR)['complete'])
    store.transition(a,'submit',ACTOR);store.transition(a,'reject',ACTOR,'Synthetic rejection for revised test marker')
    replacement=store.new_revision(document('SYN-A2'),ACTOR,a);self.assertEqual(replacement['revision'],2)
    publish(a);publish(b)
    self.assertEqual(store.preview(a,'marker','en',ACTOR)['citations'][0]['literal'],'SYN-A2')
    self.assertTrue(store.preview(b,'marker','en',ACTOR)['complete'])
    store.transition(a,'tamper_source',ACTOR)
    self.assertEqual(store.preview(a,'marker','en',ACTOR)['gap'],'source_hash_changed')
    self.assertTrue(store.preview(b,'marker','en',ACTOR)['complete'])
    store.new_revision(document('SYN-A3'),ACTOR,a)
    self.assertFalse(store.preview(a,'marker','en',ACTOR)['complete'])
    with self.assertRaises(store.WorkflowError):store.transition(a,'publish_simulation',ACTOR)
    publish(a);self.assertTrue(store.preview(a,'marker','en',ACTOR)['complete'])
    store.transition(a,'revoke',ACTOR);self.assertFalse(store.preview(a,'marker','en',ACTOR)['complete'])
    self.assertTrue(store.preview(b,'marker','en',ACTOR)['complete'])
    store.transition(b,'delete_source',ACTOR);self.assertEqual(store.preview(b,'marker','en',ACTOR)['gap'],'source_missing')
 def test_missing_language_does_not_become_approved(self):
    namespace=store.new_revision(document('SYN-AR',False),ACTOR)['namespace'];publish(namespace)
    self.assertTrue(store.preview(namespace,'marker','ar',ACTOR)['complete'])
    response=store.preview(namespace,'marker','en',ACTOR)
    self.assertFalse(response['complete']);self.assertEqual(response['gap'],'missing_language_view');self.assertFalse(response['normal_runtime_eligible'])
 def test_real_namespace_and_policy_rejected(self):
    with self.assertRaises(store.WorkflowError):store.transition('F0010','revoke',ACTOR)
    raw=json.dumps({'title':'Real policy','fields':{'marker':'APPROVED'},'views':{}}).encode()
    with self.assertRaises(store.WorkflowError):store.new_revision(raw,ACTOR)
 def test_no_early_destructive_probe(self):
    namespace=store.new_revision(document('SYN-DRAFT'),ACTOR)['namespace']
    with self.assertRaises(store.WorkflowError):store.transition(namespace,'delete_source',ACTOR)
 def test_no_generated_translation(self):
    raw=json.dumps({'title':'SYNTHETIC translation','fields':{'marker':'SYN-ORIGINAL'},'views':{'en':{'marker':'SYN-INVENTED'}}}).encode()
    with self.assertRaises(store.WorkflowError):store.new_revision(raw,ACTOR)
 def test_missing_field_is_not_a_translation_gap(self):
    namespace=store.new_revision(document('SYN-FIELD'),ACTOR)['namespace'];publish(namespace)
    self.assertEqual(store.preview(namespace,'unknown_field','en',ACTOR)['gap'],'missing_requested_field')
 def test_changed_view_cannot_reuse_source_review(self):
    namespace=store.new_revision(document('SYN-GOOD'),ACTOR)['namespace'];publish(namespace)
    self.assertTrue(store.preview(namespace,'marker','en',ACTOR)['complete'])
    with store.db() as c:
        row=store.current(c,namespace);row['document']['views']['en']['marker']='SYN-FORGED';store.write(c,'synthetic_revision',namespace,row['revision'],row)
    self.assertEqual(store.preview(namespace,'marker','en',ACTOR)['gap'],'source_view_binding_changed')

if __name__=='__main__':unittest.main(verbosity=2)
