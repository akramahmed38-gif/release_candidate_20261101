from pathlib import Path
import json,tempfile,unittest
from unittest.mock import patch
import catalog_store
import synthetic_store as store
import synthetic_restore as restore

ACTOR='synthetic-restore-test'

def document(marker,english=True):
    views={'ar':{'marker':marker}}
    if english:views['en']={'marker':marker}
    return json.dumps({'title':'SYNTHETIC restore proof','fields':{'marker':marker},'views':views}).encode()

def published(marker='SYN-RESTORE',english=True):
    ns=store.new_revision(document(marker,english),ACTOR)['namespace']
    for action in ['submit','simulate_fidelity','simulate_currentness','publish_simulation']:store.transition(ns,action,ACTOR)
    return ns

class RestoreTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        for obj,name,value in [(catalog_store,'DB',self.root/'knowledge.sqlite'),(store,'UPLOADS',self.root/'uploads'),
                               (restore,'ROOT',self.root),(restore,'RESTORES',self.root/'restore_drills')]:
            item=patch.object(obj,name,value);item.start();self.addCleanup(item.stop)

    def positive(self,ns,language='en'):
        result=store.preview(ns,'marker',language,ACTOR);self.assertTrue(result['complete']);return result

    def receipt(self):
        ns=published();self.positive(ns);result=restore.drill(ns,'marker','en',ACTOR)
        return ns,result,restore.RESTORES/result['drill_id']

    def test_roundtrip_and_copy_revocation_preserve_original_and_sibling(self):
        sibling=published('SYN-SIBLING');control=self.positive(sibling)
        ns,r,work=self.receipt()
        self.assertTrue(r['passed']);self.assertTrue(r['snapshot_restore_positive_match'])
        self.assertFalse(r['whole_application_restore_proven']);self.assertFalse(r['identity_or_native_index_restore_proven'])
        self.assertTrue(r['restored_revocation_holds']);self.assertTrue(r['original_namespace_still_complete'])
        self.assertEqual(self.positive(sibling)['citations'],control['citations'])
        self.assertTrue(self.positive(ns)['complete'])
        with store.db() as c:
            event=c.execute("select data from event where kind='synthetic_restore_drill' and target=?",(ns,)).fetchone()
            self.assertFalse(json.loads(event[0])['real_policy_approval'])

    def test_draft_or_unproven_revision_cannot_start_drill(self):
        ns=published()
        with self.assertRaises(store.WorkflowError):restore.drill(ns,'marker','en',ACTOR)

    def test_changed_source_after_positive_does_not_restore(self):
        ns=published();self.positive(ns)
        with store.db() as c:row=store.current(c,ns)
        store.source_path(row).write_bytes(b'SYNTHETIC TAMPERED')
        with self.assertRaises(store.WorkflowError):restore.drill(ns,'marker','en',ACTOR)

    def test_missing_language_does_not_become_eligible_on_restore(self):
        ns=published(english=False);self.positive(ns,'ar')
        with self.assertRaises(store.WorkflowError):restore.drill(ns,'marker','en',ACTOR)
        self.assertEqual(store.preview(ns,'marker','en',ACTOR)['gap'],'missing_language_view')

    def test_restore_never_overwrites_existing_destination(self):
        _,_,work=self.receipt();sentinel=work/'restored/keep.txt';sentinel.write_text('keep')
        with self.assertRaises(store.WorkflowError):restore.restore_bundle(work/'bundle',work/'restored')
        self.assertEqual(sentinel.read_text(),'keep')

    def test_manifest_hash_mismatch_denies_new_target(self):
        _,_,work=self.receipt();database=work/'bundle/knowledge.sqlite';database.write_bytes(database.read_bytes()+b'changed')
        target=work/'another'
        with self.assertRaises(store.WorkflowError):restore.restore_bundle(work/'bundle',target)
        self.assertFalse(target.exists())

    def test_manifest_traversal_denied_before_target_creation(self):
        _,_,work=self.receipt();p=work/'bundle/MANIFEST.json';m=json.loads(p.read_text());m['files']['../outside.txt']='0'*64;p.write_text(json.dumps(m))
        target=work/'another'
        with self.assertRaises(store.WorkflowError):restore.restore_bundle(work/'bundle',target)
        self.assertFalse(target.exists())

    def test_external_restore_destination_denied(self):
        _,_,work=self.receipt()
        with self.assertRaises(store.WorkflowError):restore.restore_bundle(work/'bundle',self.root/'outside')
        self.assertFalse((self.root/'outside').exists())

    def test_real_namespace_denied(self):
        with self.assertRaises(store.WorkflowError):restore.drill('F0010','marker','en',ACTOR)

    def test_replacement_restores_exact_new_generation_and_keeps_history(self):
        ns=published('SYN-V1');self.positive(ns)
        row=store.new_revision(document('SYN-V2'),ACTOR,ns);self.assertEqual(row['revision'],2)
        with self.assertRaises(store.WorkflowError):restore.drill(ns,'marker','en',ACTOR)
        for action in ['submit','simulate_fidelity','simulate_currentness','publish_simulation']:store.transition(ns,action,ACTOR)
        before=self.positive(ns);result=restore.drill(ns,'marker','en',ACTOR)
        self.assertEqual(result['revision'],2);self.assertEqual(result['restored']['citations'],before['citations'])
        work=restore.RESTORES/result['drill_id']
        self.assertTrue((work/'bundle/uploads'/ns/'1.json').is_file())
        self.assertTrue((work/'bundle/uploads'/ns/'2.json').is_file())

    def test_real_records_never_enter_snapshot_or_change(self):
        with store.db() as c:catalog_store.put(c,'fact','real-pending-reference','frozen',{'pending':True,'eligible':False})
        ns,_,work=self.receipt()
        with store.db() as c:
            original=c.execute("select data from record where kind='fact'").fetchone()[0]
        self.assertEqual(json.loads(original),{'pending':True,'eligible':False})
        import sqlite3
        with sqlite3.connect(work/'bundle/knowledge.sqlite') as c:
            self.assertEqual(c.execute("select count(*) from record where kind not in ('synthetic_revision','synthetic_pointer')").fetchone()[0],0)

if __name__=='__main__':unittest.main()
