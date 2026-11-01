"""Developer regressions for typed amount facets, not service defaults or policy."""
from pathlib import Path
import hashlib,json,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine

class FundingFacetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=ROOT/'end_to_end'/('facets_'+uuid.uuid4().hex[:10]);cls.out.mkdir()
        cls.engine=create_engine(cls.out/'private_workspace');cls.rows=[]
        cls.pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    @classmethod
    def tearDownClass(cls):
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        assert after==cls.pins
        (cls.out/'ACTUAL_ANSWERS.json').write_text(json.dumps({'pins':cls.pins,'rows':cls.rows,'native':'NOT RUN','developer_authored':True},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(cls.out)
    def ask(self,q,cid):
        a=self.engine.ask(q,cid,'facet-test');self.rows.append({'question':q,'actual':a});return a
    def facts(self,q,ids,cid=None,setup=None):
        cid=cid or uuid.uuid4().hex
        if setup:self.ask(setup,cid)
        a=self.ask(q,cid)
        self.assertTrue(a['complete'],{'q':q,'status':a['answer_status']})
        self.assertEqual(set(a['supported_fact_ids']),set(ids),q)
        self.assertEqual({c['fact_id'] for c in a['citations']},set(ids),q)
        return a
    def test_possessive_determiner_class(self):
        for word in ['my','your','its','our','their','his','her']:
            with self.subTest(word=word):
                a=self.facts('Please give only '+word+' minimum initial deposit amount.',['F0011'],setup='What is the AXIS opening fee?')
                self.assertTrue(any('amount_only' in r.get('requested_facets',[]) for r in a['request_contract']['requests']))
    def test_unqualified_funding_retains_balance(self):
        for q in ['What is AXIS initial funding?','AXIS و QNB اقل ايداع للتفعيل كام؟']:
            self.facts(q,['F0011','F0012'] if 'QNB' not in q else ['F0011','F0012','F0073'])
    def test_provider_only_is_not_amount_only(self):
        self.facts('AXIS only: what is the initial deposit?',['F0011','F0012'])
    def test_explicit_amount_without_service_does_not_invent_antecedent(self):
        a=self.ask('Please give only its minimum initial deposit amount.',uuid.uuid4().hex)
        self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[])
    def test_provider_switch_controls_followup(self):
        cid=uuid.uuid4().hex;self.ask('What is AXIS initial funding?',cid);self.ask('What is QNB initial funding?',cid)
        self.facts('Please give only its minimum initial deposit amount.',['F0073'],cid)
    def test_context_free_historical_cases_clarify_without_default(self):
        cases=json.loads((ROOT/'end_to_end/datasets/original176.json').read_text(encoding='utf-8-sig'))
        ids={'P1_E02','P1_E03','P1_A02','P1_P03','P1_P04'}
        for row in cases:
            if row['id'] not in ids:continue
            case=row['frozen_expected'];self.assertFalse(case.get('setup') or case.get('setup_turns') or case.get('conversation'))
            a=self.ask(row['question'],uuid.uuid4().hex)
            self.assertFalse(a['complete']);self.assertEqual(a['supported_fact_ids'],[])
    def test_arabic_explicit_amount_scope(self):
        self.facts('عايز المبلغ فقط لتفعيل AXIS.',['F0011'])

if __name__=='__main__':unittest.main(verbosity=2)
