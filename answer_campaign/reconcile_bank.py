from pathlib import Path
import json,hashlib,collections,sqlite3,datetime,uuid,csv
import openpyxl
ROOT=Path(__file__).resolve().parents[1]
TESTS=Path(r'D:\FawryChatbotPreparation\Tests')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 out=TESTS/'Results'/('answer_campaign_20261103_'+uuid.uuid4().hex[:8]);out.mkdir()
 bankpath=TESTS/'Fawry_HR_Chatbot_Semantic_25K_Runnable.jsonl';bank=[json.loads(s) for s in bankpath.read_text(encoding='utf-8-sig').splitlines() if s.strip()];byid={r['Test_ID']:r for r in bank}
 workbook=TESTS/'Fawry_HR_Chatbot_Semantic_25K_Test_Bank.xlsx';wb=openpyxl.load_workbook(workbook,read_only=True,data_only=True);it=wb['Test_Cases'].iter_rows(values_only=True);headers=next(it);original={};held=[];mismatch=[];eligibility=collections.Counter()
 for rownum,values in enumerate(it,2):
  row={k:'' if v is None else str(v) for k,v in zip(headers,values)};cid=row['Test_ID'];original[cid]=rownum;eligibility[row['Run_Eligibility']]+=1
  if cid in byid:
   if any(row.get(k,'')!=str(v) for k,v in byid[cid].items()):mismatch.append(cid)
  else:held.append({'Test_ID':cid,'workbook_row':rownum,'Run_Eligibility':row['Run_Eligibility'],'Service':row['Service'],'Language':row['Language']})
 sheets={s.title:{'rows':s.max_row,'columns':s.max_column} for s in wb};wb.close()
 c=sqlite3.connect(ROOT/'admin_staging/state/databases/knowledge.sqlite');sources=[json.loads(x[0]) for x in c.execute("select data from record where kind='source'")];c.close();registry={r['source_path'].replace('\\','/'):r for r in sources}
 refs={}
 for r in bank:
  for path in r['Source_File'].split(' ; '):
   path=path.strip().replace('\\','/');entry=registry.get(path)
   if path and path not in refs:refs[path]={'registry_present':entry is not None,'registered_sha256':entry.get('source_sha256') if entry else None,'current_snapshot_match':entry.get('current_snapshot_match') if entry else False,'canonical_scopes':json.loads(entry.get('scopes_json','[]')) if entry else [],'runtime_coverage':'CURRENT_21_FIXTURE_ADAPTER_DOES_NOT_LOAD_AUTHORED_QA'}
 audit=json.loads((TESTS/'Results/package_audit_20261027/INPUT_AUDIT.json').read_text(encoding='utf-8'))
 reconc={'campaign_id':out.name,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'bank_sha256':sha(bankpath),'expected_bank_sha256':'483b0a059be90f0d6b6b064cfa19116ff6481d2f5dc14f7356dd66823cb2191a','workbook_sha256':sha(workbook),'runnable_count':len(bank),'unique_ids':len(byid),'unique_exact_questions':len(set(r['Question'] for r in bank)),'workbook_case_count':len(original),'workbook_only_held':len(held),'workbook_eligibility':dict(eligibility),'workbook_manifest_mismatch_ids':mismatch,'workbook_sheets':sheets,'language_counts':dict(collections.Counter(r['Language'] for r in bank)),'eligibility_counts':dict(collections.Counter(r['Run_Eligibility'] for r in bank)),'setup_cases':sum(bool(r['Conversation_Setup']) for r in bank),'historical_workbook_hash_match':sha(workbook)==audit['input_hashes'][workbook.name],'source_references':refs,'bank_not_regenerated':True,'smoke_is_subset_not_additional_bank':True,'original_gold_modified':False}
 assert reconc['bank_sha256']==reconc['expected_bank_sha256'] and len(bank)==33845 and len(byid)==len(bank) and not mismatch
 save(out/'BANK_RECONCILIATION.json',reconc)
 with (out/'BANK_CASE_STATUS.jsonl').open('w',encoding='utf-8') as f:
  for line,r in enumerate(bank,1):
   v={'Test_ID':r['Test_ID'],'manifest_line':line,'workbook_sheet':'Test_Cases','workbook_row':original[r['Test_ID']],'bank_sha256':reconc['bank_sha256'],'language':r['Language'],'original_service':r['Service'],'topic':r['Topic'],'source_reference':r['Source_File'],'gold_reference':r['Gold_ID'],'run_eligibility':r['Run_Eligibility'],'conversation_setup':r['Conversation_Setup'],'question_sha256':hashlib.sha256(r['Question'].encode()).hexdigest(),'meaning_family':r['Source_File']+'|'+r['Gold_ID'],'duplicate_of':None,'state':'BLOCKED_RUNTIME_COVERAGE','reference_validity':'REFERENCE_ONLY_UNREVIEWED','reason':'Broader fixed source-bound admin benchmark snapshot and actual handler integration not yet frozen; no answer request executed'}
   f.write(json.dumps(v,ensure_ascii=False)+'\n')
 with (out/'WORKBOOK_HELD_CASES.jsonl').open('w',encoding='utf-8') as f:
  for r in held:f.write(json.dumps(r,ensure_ascii=False)+'\n')
 progress={'campaign_id':out.name,'bank_cases':len(bank),'executed':0,'complete_correct':0,'incorrect':0,'valid_partial_hold':0,'reference_unscorable_executed':0,'runtime_coverage_blocked':len(bank),'not_run':len(bank),'workbook_only_held':len(held),'native':'NOT RUN','phase':'source_snapshot_integration','counts_not_inferred_from_prior_tests':True};save(out/'CURRENT_PROGRESS.json',progress)
 save(out/'RUN_MANIFEST.json',{'campaign_id':out.name,'bank':str(bankpath),'bank_sha256':reconc['bank_sha256'],'application':str(ROOT),'current_handler':'/training/api/v1/chatbot/ask','state':'PREPARING_NOT_EXECUTING','approved_mode_unchanged':True,'expected_answers_runtime_input':False,'concurrency':1,'resume_policy':'Never repeat completed IDs within a frozen run; new revision uses a new run ID'})
 (out/'EXECUTED_ANSWERS.jsonl').touch();save(TESTS/'Results/CURRENT_ANSWER_CAMPAIGN.json',{'path':str(out),'campaign_id':out.name})
 with (out/'SERVICE_TOPIC_LANGUAGE_COVERAGE.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['original_service','topic','language','bank_cases','executed','complete_correct','runtime_coverage_blocked'])
  for key,n in sorted(collections.Counter((r['Service'],r['Topic'],r['Language']) for r in bank).items()):w.writerow([*key,n,0,0,n])
 with (out/'REFERENCE_AND_KNOWLEDGE_GAPS.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['source_reference','registry_present','current_snapshot_match','runtime_coverage','reference_validity'])
  for key,r in sorted(refs.items()):w.writerow([key,r['registry_present'],r['current_snapshot_match'],r['runtime_coverage'],'PENDING_CASE_REFERENCE_FIT_CHECK'])
 (out/'FINAL_CHATBOT_TEST_REPORT.md').write_text('# Original question-bank campaign — in progress\n\n33,845 runnable cases reconciled; 36,915 workbook rows include 3,070 separate held cases. Original manifest hash matches the supplied value. **0 actual campaign requests executed.** No accuracy, native or deployment acceptance is claimed.\n\nCurrent blocker: the answering adapter loads 21 fixtures while authored Q&A files are only catalogued, not onboarded. Preparing the broader fixed pending-evidence snapshot is authorized; no benchmark gold or per-case source hints may enter the runtime. Original cases and historical results remain unchanged.\n',encoding='utf-8')
 print(json.dumps({'campaign':str(out),'runnable':len(bank),'workbook':len(original),'held':len(held),'manifest_hash_match':True,'mismatches':len(mismatch),'executed':0}))
if __name__=='__main__':main()
