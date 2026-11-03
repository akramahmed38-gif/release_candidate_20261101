"""Load the existing full corpus into the existing retriever; no fake answers.
This component probe is not a chatbot answer, native or eligibility acceptance.
"""
from pathlib import Path
import hashlib,json,logging,sys,time,uuid,threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'admin_staging'))
sys.path.insert(0,str(ROOT/'admin_staging/application'))
from prepared_corpus_store import PreparedCorpusStore
from chatbot.config import load_config
from chatbot.generation import OllamaClient
from chatbot.retrieval import HybridRetriever
import psutil
out=ROOT/'environment_validation'/('full_corpus_integration_'+uuid.uuid4().hex[:10]);out.mkdir()
result={'scope':'Existing HybridRetriever.refresh against immutable full prepared content','native_full_stack':'NOT RUN','actual_answer_requests':0,'model_calls':0,'new_embeddings':0,'source_extraction_calls':0,'approvals_created':0,'rows':0,'status':'NOT RUN'}
stop=threading.Event();samples=[]
def monitor():
 process=psutil.Process()
 while not stop.wait(.1):
  try:samples.append({'rss':process.memory_info().rss,'available':psutil.virtual_memory().available,'cpu_seconds':sum(process.cpu_times()[:2])})
  except Exception:return
try:
 sys.path.insert(0,str(ROOT/'source/candidate'))
 from observed_guard import ObservedBudget
 guard=ObservedBudget(stable_window=True);guard.wait();result['guard_events']=list(guard.events)
 threading.Thread(target=monitor,daemon=True).start();started=time.perf_counter()
 store=PreparedCorpusStore(Path(r'D:\FawryChatbotPreparation\prepared_content'))
 config=load_config(ROOT/'admin_staging/application')
 logger=logging.getLogger('full_corpus_component');logger.addHandler(logging.NullHandler())
 retriever=HybridRetriever(config,store,OllamaClient(config,logger),logger)
 retriever.refresh()
 result.update(status='PASS_COMPONENT_LOAD_ONLY',rows=store.count(),retriever_rows=len(retriever.corpus),curated_question_entries=len(retriever.qa_question_index),vocabulary_tokens=len(retriever.doc_freq),load_and_refresh_ms=(time.perf_counter()-started)*1000,prepared_signature=store.manifest['signature'],prepared_chunks_sha256=hashlib.sha256((store.root/'chunks.jsonl').read_bytes()).hexdigest(),source_files=store.manifest['source_files'],raw_content_not_approved=True)
 from collections import Counter
 result['source_types']={str(k):v for k,v in Counter(r['metadata'].get('source_type') for r in store.rows).items()}
 result['missing_source_sha256']=sum(not r['metadata'].get('source_sha256') for r in store.rows)
 try:store.query('any');raise AssertionError('Semantic query falsely succeeded')
 except RuntimeError:result['missing_semantic_query_explicitly_denied']=True
except Exception as exc:result.update(status='FAIL_COMPONENT',error_type=type(exc).__name__,error=str(exc)[:200])
finally:
 stop.set()
 if samples:result.update(peak_rss=max(s['rss'] for s in samples),minimum_available_ram=min(s['available'] for s in samples),process_cpu_seconds=max(s['cpu_seconds'] for s in samples))
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(result),flush=True);print('RESULTS '+str(out),flush=True)
