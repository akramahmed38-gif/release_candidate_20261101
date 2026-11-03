"""Prepare source-authored pending evidence, independently of benchmark gold.
This program never reads any question bank, expected answer or evaluation file.
"""
from pathlib import Path
import collections,hashlib,importlib.util,json,re,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];STAGING=ROOT/'admin_staging'
APP=Path(r'\\10.100.175.10\Projects\Production\FP Branches + Forms\HR Training App')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def norm(s):return re.sub(r'[^\w]','',str(s).casefold())
def main():
 sys.path.insert(0,str(STAGING/'application'))
 from chatbot.ingestion import MaterialIngestor
 sys.path.insert(0,str(STAGING))
 from catalog_store import SENSITIVE
 safety=Path(r'D:\FawryChatbotPreparation\Tests\EvaluationTools\production_candidate\chatbot\passage_quality.py')
 spec=importlib.util.spec_from_file_location('preserved_passage_quality',safety);guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
 c=sqlite3.connect('file:'+str(STAGING/'state/databases/knowledge.sqlite')+'?mode=ro',uri=True)
 sources=[json.loads(x[0]) for x in c.execute("select data from record where kind='source'")];profiles=[json.loads(x[0]) for x in c.execute("select data from record where kind='profile'")];c.close()
 aliases={p['service_id']:[norm(v) for v in [p['name'].split('/')[0],*p.get('aliases',[])] if len(norm(v))>=3] for p in profiles}
 records=[];gaps=[];source_versions={};seen=set();copies={}
 for source in sorted(sources,key=lambda x:x['source_path']):
  relative=source['source_path']
  if not relative.startswith('KnowledgeBase/QA/') or not relative.endswith('.md'):continue
  path=(APP/relative).resolve()
  if not path.is_relative_to(APP.resolve()):raise RuntimeError('Source path containment')
  try:raw=path.read_bytes()
  except OSError:gaps.append({'source':relative,'reason':'SOURCE_MISSING'});continue
  if sha(raw)!=source['source_sha256']:gaps.append({'source':relative,'reason':'SOURCE_VERSION_CHANGED'});continue
  source_versions[relative]=sha(raw);copies[relative]=raw
  text=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n');cursor=0
  for section in MaterialIngestor._split_knowledge_base_sections(text):
   position=text.find(section,cursor);cursor=max(cursor,position+len(section));record=MaterialIngestor._parse_knowledge_base_qa_record(section)
   if record is None:gaps.append({'source':relative,'reason':'UNPARSED_SECTION','section_sha256':sha(section.encode())});continue
   identity=relative+'|'+record.qa_id
   seen.add(identity);reason=None
   if SENSITIVE.search(record.answer):reason='RESTRICTED_CONTENT'
   elif guard.contains_interpretation_instructions(record.answer):reason='SOURCE_INTERPRETER_DIRECTIVE'
   elif guard.held_policy_instruction(record.answer):reason='EXISTING_POLICY_REVIEW_HOLD'
   category=norm(record.category.split(' - ')[0]);specific=[sid for sid,values in aliases.items() if category in values]
   scopes=specific or json.loads(source.get('scopes_json','[]'))
   if not scopes:reason=reason or 'SERVICE_ASSOCIATION_UNRESOLVED'
   line_start=text[:position].count('\n')+1 if position>=0 else None
   marker=re.search(r'(?m)^\s*answer\s*:\s*([|>]?)\s*$',section)
   answer_start=line_start+section[:marker.end()].count('\n')+1 if marker and line_start else line_start
   value={'record_id':'QA-'+sha((identity+'|'+str(position)).encode())[:24],'authored_id':record.qa_id,'source_document':relative,'source_sha256':sha(raw),'source_unit_sha256':sha(section.encode()),'locator':{'type':'lines','line_start':answer_start,'line_end':line_start+section.count('\n') if line_start else None,'authored_id':record.qa_id},'service_ids':scopes,'category':record.category,'question':record.question,'alternate_questions':record.alternate_questions,'keywords':record.keywords,'original_answer':record.answer,'original_answer_sha256':sha(record.answer.encode()),'arabic_view':'ORIGINAL_SOURCE_TEXT','english_view':'NO_REVIEWED_ENGLISH_RENDERING','review_status':'held' if reason else 'pending_admin_review','hold_reason':reason,'normal_runtime_eligible':False,'human_fidelity_approved':False,'business_currentness_approved':False,'source_identity_not_business_approval':True}
   records.append(value)
 groups=collections.defaultdict(list)
 for record in records:groups[(record['source_document'],record['authored_id'])].append(record)
 for identity,group in groups.items():
  if len(group)<2:continue
  signatures={(r['question'],r['original_answer']) for r in group}
  if len(signatures)==1:
   for record in group[1:]:record.update(hold_reason='DUPLICATE_SOURCE_ALIAS',review_status='held',duplicate_of=group[0]['record_id'])
  else:
   for record in group:record.update(hold_reason='CONFLICTING_DUPLICATE_AUTHORED_ID',review_status='held')
 digest=sha(json.dumps({'sources':source_versions,'records':records},sort_keys=True,ensure_ascii=False).encode());target=STAGING/'state/benchmark_snapshots'/digest[:24];target.mkdir(parents=True,exist_ok=True)
 path=target/'records.jsonl';body=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records)
 if path.exists() and path.read_text(encoding='utf-8')!=body:raise RuntimeError('Immutable snapshot differs')
 path.write_text(body,encoding='utf-8')
 for rel,raw in copies.items():
  dest=target/'source_files'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 manifest={'snapshot_id':digest[:24],'snapshot_digest':digest,'mode':'ADMIN_REVIEW_BENCHMARK','sources':source_versions,'records':len(records),'usable_pending_records':sum(not r['hold_reason'] for r in records),'held_records':sum(bool(r['hold_reason']) for r in records),'per_service_pending':dict(collections.Counter(s for r in records if not r['hold_reason'] for s in r['service_ids'])),'hold_reasons':dict(collections.Counter(r['hold_reason'] for r in records if r['hold_reason'])),'gaps':gaps,'record_file_sha256':sha(path.read_bytes()),'source_parser_sha256':sha(Path(sys.modules['chatbot.ingestion'].__file__).read_bytes()),'safety_module_sha256':sha(safety.read_bytes()),'originals_modified':False,'benchmark_gold_read':False,'new_translations':0,'new_embeddings':0,'approvals_created':0,'english_missing_is_not_approval':True}
 (target/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (STAGING/'BENCHMARK_SNAPSHOT_PREPARATION.json').write_text(json.dumps({'path':str(target),**manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in manifest.items() if k not in ['sources','gaps']},ensure_ascii=True))
if __name__=='__main__':main()
