"""Developer tests: explicit clarification, original scope, and owner isolation."""
from pathlib import Path
import json,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine

class ClarificationResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'end_to_end'/('clarification_'+uuid.uuid4().hex[:10]);cls.out.mkdir();cls.engine=create_engine(cls.out/'private_workspace');cls.rows=[]
    @classmethod
    def tearDownClass(cls):
        (cls.out/'RESULTS.json').write_text(json.dumps({'rows':cls.rows,'developer_authored':True,'native':'NOT RUN'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(cls.out)
    def ask(self,q,cid,sid='owner'):
        a=self.engine.ask(q,cid,sid);self.rows.append({'question':q,'actual':a});return a
    def test_original_request_resumes_after_explicit_reply(self):
        cid=uuid.uuid4().hex;first=self.ask('How much do I need to activate the wallet?',cid)
        self.assertFalse(first['complete']);self.assertEqual(first['supported_fact_ids'],[])
        a=self.ask('I mean AXIS Pay.',cid)
        self.assertTrue(a['complete']);self.assertEqual(set(a['supported_fact_ids']),{'F0011','F0012'})
        self.assertEqual(a['current_user_question'],'I mean AXIS Pay.')
        self.assertEqual(a['resolved_question'],'How much do I need to activate the wallet?')
        self.assertEqual(a['clarification_resolution']['service_id'],'axis_pay')
    def test_channel_remains_bound_to_original_question(self):
        cid=uuid.uuid4().hex;self.ask('What is the deposit fee through ATMs?',cid);a=self.ask('AXIS Pay',cid)
        self.assertTrue(a['complete']);self.assertEqual(a['supported_fact_ids'],['F0002'])
    def test_another_provider_is_not_assigned_axis_facts(self):
        cid=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',cid);a=self.ask('QNB Wallet',cid)
        self.assertTrue(a['complete']);self.assertEqual(a['supported_fact_ids'],['F0073'])
    def test_new_question_cancels_pending_request(self):
        cid=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',cid)
        a=self.ask('What is the QNB Wallet ATM withdrawal fee?',cid)
        self.assertTrue(a['complete']);self.assertEqual(a['supported_fact_ids'],['F0076']);self.assertNotIn('clarification_resolution',a)
    def test_session_isolation(self):
        cid=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',cid,'first')
        a=self.ask('I mean AXIS Pay.',cid,'second');self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[])
    def test_negative_reply_is_not_positive_service_binding(self):
        cid=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',cid)
        a=self.ask('Not AXIS Pay.',cid);self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[]);self.assertNotIn('clarification_resolution',a)
    def test_source_invalidation_is_not_bypassed_by_resumption(self):
        positive=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',positive)
        control=self.ask('AXIS Pay',positive);self.assertTrue(control['complete'])
        self.assertEqual(set(control['supported_fact_ids']),{'F0011','F0012'})
        cid=uuid.uuid4().hex;self.ask('How much do I need to activate the wallet?',cid)
        p=self.out/'private_workspace/source_files/daily_brief/axis_wallet_sales_guide.pdf';before=p.read_bytes()
        try:
            p.write_bytes(before+b'\nDISPOSABLE INVALIDATION TEST')
            a=self.ask('AXIS Pay',cid);self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[])
        finally:p.write_bytes(before)

if __name__=='__main__':unittest.main(verbosity=2)
