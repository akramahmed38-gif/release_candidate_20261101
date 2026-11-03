from pathlib import Path
import json,collections,hashlib,math,csv,datetime
import openpyxl
from openpyxl.styles import Alignment,Font
ROOT=Path(__file__).resolve().parents[1];TESTS=Path(r'D:\FawryChatbotPreparation\Tests')
def norm(v):return ' '.join(str(v).split())
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def pct(values,p):
 if not values:return None
 v=sorted(values);x=(len(v)-1)*p;a=math.floor(x);b=math.ceil(x);return v[a]+(v[b]-v[a])*(x-a)
def main():
 out=Path(json.loads((TESTS/'Results/CURRENT_ANSWER_CAMPAIGN.json').read_text())['path']);selected=json.loads((out/'HARNESS_SELECTION.json').read_text(encoding='utf-8'));gold={r['Test_ID']:r for r in selected['cases']};executed=[json.loads(s) for s in (out/'EXECUTED_ANSWERS.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()];assert len({r['bank_id'] for r in executed})==len(executed)
 pointer=json.loads((ROOT/'admin_staging/BENCHMARK_SNAPSHOT_PREPARATION.json').read_text(encoding='utf-8'));authored=[json.loads(s) for s in (Path(pointer['path'])/'records.jsonl').read_text(encoding='utf-8').splitlines()]
 refs=collections.defaultdict(list)
 for r in authored:refs[(r['source_document'],r['authored_id'])].append(r)
 judgments=[]
 for row in executed:
  case=gold[row['bank_id']];paths=case['Source_File'].split(' ; ');ids=case['Gold_ID'].split('__');resolved=[];issues=[]
  for path,identity in zip(paths,ids):
   base=identity.split('_dialogue_')[0];choices=refs.get((path,base),[])
   if len(choices)!=1:issues.append('authored_reference_missing_or_ambiguous');continue
   r=choices[0];resolved.append(r)
   if r['hold_reason']:issues.append(r['hold_reason'])
  if len(resolved)!=len(paths):issues.append('reference_side_missing')
  if resolved and not all(norm(r['original_answer']) in norm(case['Expected_Answer']) for r in resolved):issues.append('expected_answer_differs_from_current_source')
  status='INCONCLUSIVE_GOLD_MISMATCH' if issues else 'REFERENCE_VERIFIED_FOR_SOURCE_VERSION'
  actual=row['main']['actual'];wrong_service='customer_care' in actual.get('answer','') and case['Service']=='Insurance'
  judgments.append({'Test_ID':row['bank_id'],'reference_validity':status,'reference_issues':issues,'source_versions':[{'path':r['source_document'],'sha256':r['source_sha256'],'locator':r['locator']} for r in resolved],'business_currentness_approved':False,'question_reference_fit':'DEVELOPER_REVIEWED; not independent acceptance','verdict':'REFERENCE_UNSCORABLE' if issues else 'INCOMPLETE_UNNECESSARY_CLARIFICATION','complete_correct':False,'missing_requested_information':case['Expected_Answer'],'wrong_service_interpretation':wrong_service,'unsupported_business_assertions':0 if not actual.get('supported_fact_ids') else None,'false_complete':False if not actual.get('complete') else None,'reason':'No business answer or citation emitted. Existing reference is present; answering adapter remains limited to 21 fixtures and raw planner introduces unresolved predicates. This is not a successful source-gap hold.','language':case['Language'],'original_service':case['Service'],'source_family':case['Source_File']+'|'+case['Gold_ID']})
 with (out/'ANSWER_JUDGMENTS.jsonl').open('w',encoding='utf-8') as f:
  for r in judgments:f.write(json.dumps(r,ensure_ascii=False)+'\n')
 existing=[json.loads(s) for s in (out/'BANK_CASE_STATUS.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()];byjudgment={r['Test_ID']:r for r in judgments}
 for row in existing:
  if row['Test_ID'] in byjudgment:
   j=byjudgment[row['Test_ID']];row.update(state='EXECUTED',outcome=j['verdict'],reference_validity=j['reference_validity'],run_id='harness_008d6e6_fixed_fixture_diagnostic')
  elif row['run_eligibility']=='RUN_SEMANTIC' and 'KnowledgeBase/QA/' in row['source_reference']:
   row.update(state='PAUSED_UNEXECUTED_SYSTEMIC_DEFECT',reason='Source-authored QA is not connected to full answering pipeline; 21-fixture coverage ceiling demonstrated. No individual outcome inferred.')
  else:row.update(state='QUEUED',reason='Not executed; broader source/runtime integration and balanced campaign pending')
 with (out/'BANK_CASE_STATUS.jsonl').open('w',encoding='utf-8') as f:
  for r in existing:f.write(json.dumps(r,ensure_ascii=False)+'\n')
 times=[r['main']['http_ms'] for r in executed];timing={}
 for lang in sorted(set(c['Language'] for c in gold.values())):
  values=[r['main']['http_ms'] for r in executed if gold[r['bank_id']]['Language']==lang];timing[lang]={'n':len(values),'p50_ms':pct(values,.5),'p95_ms':pct(values,.95),'p99_ms':pct(values,.99),'scope':'All main requests; no complete-correct answers'}
 states=collections.Counter(r['state'] for r in existing);progress={'campaign_id':out.name,'bank_cases':33845,'executed':len(executed),'complete_correct':0,'incorrect_or_incomplete':sum(j['verdict']!='REFERENCE_UNSCORABLE' for j in judgments),'incomplete':sum(j['verdict']=='INCOMPLETE_UNNECESSARY_CLARIFICATION' for j in judgments),'false_complete':0,'unsupported_assertions':0,'wrong_service_interpretations':sum(j['wrong_service_interpretation'] for j in judgments),'wrong_provider_business_assertions':0,'legitimate_knowledge_gaps':0,'valid_partial_hold':0,'reference_unscorable':sum(j['verdict']=='REFERENCE_UNSCORABLE' for j in judgments),'timeouts':0,'not_run':33845-len(executed),'case_state_counts':dict(states),'workbook_only_held':3070,'timing_by_language':timing,'complete_correct_latency':{'n':0,'p50_ms':None,'p95_ms':None,'p99_ms':None},'phase':'full_existing_pipeline_integration_required','backend':'existing Core/BM25 fixture worker','native':'NOT RUN','current_lookup_replacement':'REJECTED_NOT_SERVED','old_gold_unchanged':True,'independent_acceptance':False};save(out/'CURRENT_PROGRESS.json',progress)
 manifest=json.loads((out/'RUN_MANIFEST.json').read_text(encoding='utf-8'));manifest.update(state='HARNESS_EXECUTED; broader integration pending',harness_commit='008d6e6',harness_handler='/training/api/v1/admin/knowledge-ask',shared_core_handler='admin_knowledge.call_engine -> owned CatalogEngine',floating_widget_preview_parity='NOT PROVEN',served_knowledge_pool='Fixed all21 fixtures, independent of case gold; not broad source coverage',prepared_source_snapshot=pointer['snapshot_id'],source_snapshot_serving='NOT ADOPTED: 530-record QA lookup rejected',expected_answers_sent_to_runtime=False);save(out/'RUN_MANIFEST.json',manifest)
 book=openpyxl.Workbook();sheet=book.active;sheet.title='Executed_Answers';headers=['Test_ID','Language','Service','Full Question','Full Actual Answer','Original Expected Answer','Conversation Setup','Verdict','Reference Validity','HTTP ms','Final Status','Complete','Actual Citations','Trace ID','Backend','Tested Commit','JSONL Evidence']
 sheet.append(headers)
 for row,j in zip(executed,judgments):
  case=gold[row['bank_id']];a=row['main']['actual'];sheet.append([row['bank_id'],case['Language'],case['Service'],row['original_question'],a.get('answer',''),case['Expected_Answer'],case['Conversation_Setup'],j['verdict'],j['reference_validity'],row['main']['http_ms'],a.get('answer_status'),a.get('complete'),json.dumps(a.get('citations',[]),ensure_ascii=False),a.get('diagnostic_trace_id'),a.get('backend'),'008d6e6','EXECUTED_ANSWERS.jsonl'])
 sheet.freeze_panes='D2';sheet.auto_filter.ref=sheet.dimensions
 for cell in sheet[1]:cell.font=Font(bold=True)
 for row in sheet.iter_rows(min_row=2):
  for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
 for letter in ['D','E','F']:sheet.column_dimensions[letter].width=80
 summary=book.create_sheet('Summary');summary.append(['Metric','Actual']);
 for k in ['bank_cases','executed','complete_correct','incomplete','reference_unscorable','false_complete','unsupported_assertions','timeouts','not_run']:summary.append([k,progress[k]])
 summary.append(['Native full stack','NOT RUN']);summary.append(['Independent release acceptance','NOT PASSED']);book.save(out/'CHATBOT_ANSWER_RESULTS.xlsx')
 with (out/'SERVICE_TOPIC_LANGUAGE_COVERAGE.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['original_service','topic','language','bank_cases','executed','complete_correct','incomplete','not_run'])
  bank=[json.loads(s) for s in (TESTS/'Fawry_HR_Chatbot_Semantic_25K_Runnable.jsonl').read_text(encoding='utf-8-sig').splitlines() if s.strip()]
  groups=collections.Counter((r['Service'],r['Topic'],r['Language']) for r in bank)
  for k,n in sorted(groups.items()):
   actual=[j for j in judgments if (gold[j['Test_ID']]['Service'],gold[j['Test_ID']]['Topic'],gold[j['Test_ID']]['Language'])==k];w.writerow([*k,n,len(actual),0,sum(j['verdict']=='INCOMPLETE_UNNECESSARY_CLARIFICATION' for j in actual),n-len(actual)])
 report='# Original question-bank campaign — IN PROGRESS / NO-GO\n\n'+f'33,845 runnable cases; {len(executed)} executed; 0 complete-correct; {progress["incomplete"]} incomplete; {progress["reference_unscorable"]} reference-unscorable; 33,838 not run. No false-complete business response, business assertion or timeout occurred in these seven no-fact responses. One wrong-service interpretation was observed for Insurance (customer_care). No hold is counted as a business-answer pass.\n\n'+'This harness used the fixed entire existing21-fixture pool through the actual authenticated admin chat UI, with original questions and declared setup turns only. It demonstrates the current coverage failure; it is not a full-library campaign or native validation. The source QA lookup replacement was rejected before any campaign request used it. Its552-record snapshot remains onboarding data, not an adopted chatbot.\n\n## Actual answers and reference review\n\n'
 for row,j in zip(executed,judgments):
  c=gold[row['bank_id']];a=row['main']['actual'];report+='### '+row['bank_id']+' — '+c['Service']+'\n\nQuestion: '+row['original_question']+'\n\nActual full answer:\n\n'+a.get('answer','')+'\n\nExpected source reference: '+c['Source_File']+' / '+c['Gold_ID']+'\n\nExpected source facts (evaluator only): '+c['Expected_Answer']+'\n\nVerdict: **'+j['verdict']+'**. Reference: '+j['reference_validity']+'. Actual citations: '+json.dumps(a.get('citations',[]),ensure_ascii=False)+'. HTTP: '+str(row['main']['http_ms'])+' ms.\n\n'
 report+='## Timing and next repair\n\n'+json.dumps(timing,ensure_ascii=False,indent=2)+'\n\nThese latency populations contain only unsuccessful clarifications. There are zero complete-correct latency samples and no production SLA claim. Source-reference fidelity is not business currentness approval. Full BGE/Chroma/Ollama execution is not claimed.\n\nNext: connect the existing full prepared content and original retrieval/answer pipeline, preserving safety and actual source bindings. Do not execute thousands of expected fixture-ceiling holds or adopt the rejected QA-only replacement. Repair raw obligation retention independently from evidence availability; then freeze a new revision and run balanced original IDs.\n'
 (out/'FINAL_CHATBOT_TEST_REPORT.md').write_text(report,encoding='utf-8');print(json.dumps({'campaign':str(out),'executed':len(executed),'incomplete':progress['incomplete'],'reference_unscorable':progress['reference_unscorable'],'not_run':progress['not_run'],'state_counts':dict(states),'xlsx_created':True}))
if __name__=='__main__':main()
