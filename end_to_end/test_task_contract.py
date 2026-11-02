"""Generalized boundary counterexamples, not the sealed challenge questions."""
from pathlib import Path
import json,sys,unittest,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine
from task_contract import task_mode,scalar_view

class TaskContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.out=ROOT/'end_to_end'/('task_contract_'+uuid.uuid4().hex[:10]);cls.out.mkdir();cls.engine=create_engine(cls.out/'private_workspace');cls.rows=[]
 @classmethod
 def tearDownClass(cls):
  (cls.out/'ACTUAL.json').write_text(json.dumps(cls.rows,ensure_ascii=False,indent=2),encoding='utf-8')
 def ask(self,q):
  a=self.engine.ask(q,uuid.uuid4().hex,'task-test');self.rows.append({'question':q,'actual':a});return a
 def test_classification_emits_no_business_views(self):
  a=self.ask('Classify only: QNB Wallet identity; AXIS opening fee; ADIB remittance transaction code.')
  self.assertEqual(a['type'],'interpretation');self.assertFalse(a['supported_fact_ids']);self.assertFalse(a['citations']);self.assertTrue(a['complete'])
  self.assertEqual({(r['service_id'],r['intent_id']) for r in a['request_contract']['requests']},{('qnb_wallet','identity'),('axis_pay','opening_fee'),('adib_remittance','transaction_code')})
 def test_named_unknown_intent_does_not_borrow_previous_topic(self):
  a=self.ask('Routing only: QNB Wallet documents; Yellow Card unknowablething.')
  self.assertFalse(a['complete']);self.assertFalse(a['supported_fact_ids'])
  self.assertFalse(any(r['service_id']=='yellow_card' and r['intent_id']=='documents' for r in a['request_contract']['requests']))
 def test_meta_words_inside_quote_do_not_change_mode(self):
  self.assertEqual(task_mode('A memo says “classify only”; what is AXIS opening fee?')['mode'],'business_answer')
 def test_negative_classification_and_mixed_tasks_not_silently_dropped(self):
  self.assertEqual(task_mode('Do not classify only: explain AXIS opening fee.')['mode'],'business_answer')
  self.assertEqual(task_mode('Classify only: QNB documents; also answer AXIS opening fee.')['mode'],'business_answer')
 def test_ordinary_business_answer_still_answers(self):
  a=self.ask('What is the QNB ATM withdrawal fee?');self.assertTrue(a['complete']);self.assertEqual(a['supported_fact_ids'],['F0076']);self.assertFalse(a['clarification_needed'])
 def test_numeric_scope_projects_only_literal_amount(self):
  for provider,fid in [('AXIS','F0011'),('QNB Wallet','F0073')]:
   a=self.ask('Give only the numeric minimum initial deposit amount for '+provider+'.')
   self.assertTrue(a['complete']);self.assertEqual(a['supported_fact_ids'],[fid]);self.assertIn(fid,a['rendered_view_projections'])
   parent=self.engine.facts[fid]['english'];view=a['rendered_view_projections'][fid];self.assertEqual(view['text'],parent[view['start']:view['end']]);self.assertNotIn('immediate',a['answer'])
 def test_scalar_projection_refuses_extra_policy_scope_or_mismatch(self):
  f=dict(self.engine.facts['F0011']);f['scope']={**f['scope'],'exception':'unknown'};self.assertIsNone(scalar_view(f,'en'))
  f=dict(self.engine.facts['F0011']);f['scope']={**f['scope'],'minimum_initial_deposit_egp':999};self.assertIsNone(scalar_view(f,'en'))
 def test_complete_has_consistent_presentation(self):
  a=self.ask('AXIS deposits through Fawry Plus and ATM: compare the fees.')
  self.assertTrue(a['complete']);self.assertFalse(a['clarification_needed']);self.assertEqual(a['resolution_status'],'complete_scoped_answer');self.assertNotIn('Unresolved request dimensions',a['answer'])
 def test_mode_cannot_bypass_midrequest_revocation(self):
  def revoke():
   path=self.engine.workspace/'test_eligibility.json';self.old=path.read_bytes();path.write_text('{}')
  self.engine.before_emit_hook=revoke
  try:
   a=self.ask('Classify only: AXIS opening fee.');self.assertFalse(a['complete']);self.assertFalse(a['supported_fact_ids'])
  finally:
   (self.engine.workspace/'test_eligibility.json').write_bytes(self.old);self.engine.before_emit_hook=None

class ClauseRoleTests(unittest.TestCase):
 def test_ordinals_bind_adjacent_financial_head_not_other_topic(self):
  from linguistic_spans import financial_ordinal_spans,spans
  for q in ['first deposit','deposit first','الإيداع الأول','أول إيداع']:
   self.assertTrue(financial_ordinal_spans(q,spans(q,'deposit')+spans(q,'إيداع')),q)
  self.assertFalse(financial_ordinal_spans('deposit fee; first procedure',[(0,7)]))
 def test_process_title_not_explicit_financial_question(self):
  from linguistic_spans import process_context_scope,spans
  def h(q):return {'activation':spans(q,'activation'),'identity':spans(q,'ID')}
  self.assertIsNotNone(process_context_scope('activation: valid ID required?',h('activation: valid ID required?')))
  self.assertIsNone(process_context_scope('activation fee and valid ID?',h('activation fee and valid ID?')))
 def test_image_object_does_not_remove_separate_identity_check(self):
  from linguistic_spans import image_object_identity_spans,spans
  for q,want in [('photo of the ID',True),('photo; ID valid?',False)]:
   self.assertEqual(bool(image_object_identity_spans(q,{'image':spans(q,'photo'),'identity':spans(q,'ID')})),want)

if __name__=='__main__':unittest.main(verbosity=2)
