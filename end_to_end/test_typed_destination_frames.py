"""Typed language arguments must not invent provider-specific balance rules."""
from pathlib import Path
import hashlib,json,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine

class TypedDestinationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'end_to_end'/('typed_destination_'+uuid.uuid4().hex[:10]);cls.out.mkdir();cls.engine=create_engine(cls.out/'private_workspace');cls.rows=[]
        cls.pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    @classmethod
    def tearDownClass(cls):
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts};assert after==cls.pins
        (cls.out/'RESULTS.json').write_text(json.dumps({'source_pins':cls.pins,'rows':cls.rows,'native':'NOT RUN','developer_authored':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(cls.out)
    def ask(self,q,cid=None):
        a=self.engine.ask(q,cid or uuid.uuid4().hex,'typed-destination');self.rows.append({'question':q,'actual':a});return a
    def complete(self,q,ids):
        a=self.ask(q);self.assertTrue(a['complete'],a['answer_status']);self.assertEqual(set(a['supported_fact_ids']),set(ids));self.assertEqual({c['fact_id'] for c in a['citations']},set(ids))
    def test_prepositional_goal_and_opening_contrast(self):
        self.complete('Does the AXIS initial deposit go into my balance, or is it an opening charge?',['F0010','F0011','F0012'])
    def test_direct_goal(self):
        self.complete('Will the AXIS initial funding enter my balance?',['F0011','F0012'])
    def test_qnb_minimum_does_not_prove_balance_treatment(self):
        a=self.ask('Will QNB initial funding enter my balance?');self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],['F0073']);self.assertEqual(a['answer_status'],'supported_partial')
    def test_requested_fee_survives_separate_balance_clause(self):
        self.complete('Will AXIS initial funding enter my balance; and what are deposit fees at Fawry Plus?',['F0011','F0012','F0001'])
    def test_tariff_is_not_balance_treatment(self):
        self.complete('What is the AXIS deposit fee at Fawry Plus?',['F0001'])
    def test_refund_is_not_initial_deposit(self):
        a=self.ask('Does the QNB refund go into my balance?');self.assertFalse(a['complete']);self.assertNotIn('F0012',a['supported_fact_ids'])
    def test_contrast_after_service_clarification(self):
        cid=uuid.uuid4().hex;a=self.ask('Does the deposit go into my balance, or is it an opening charge?',cid)
        self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[])
        b=self.ask('I mean AXIS Pay.',cid);self.assertTrue(b['complete']);self.assertEqual(set(b['supported_fact_ids']),{'F0010','F0011','F0012'})

if __name__=='__main__':unittest.main(verbosity=2)
