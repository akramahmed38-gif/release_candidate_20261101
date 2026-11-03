"""Original source QA onboarding for the existing admin answering worker.
No benchmark IDs, expected answers or source hints are accepted at request time.
"""
from pathlib import Path
from collections import Counter
import hashlib,json,math,re,time
ROOT=Path(__file__).resolve().parent

def digest(raw):return hashlib.sha256(raw).hexdigest()
def key(text):return ' '.join(str(text).casefold().strip(' ?!؟.').split())

def bm25(query,document,frequencies,count,average):
    if not query or not document:return 0.0
    counts=Counter(document);length=len(document);score=0.0
    # Same k1/b and formula as the existing application's lexical retriever.
    for token in query:
        frequency=counts.get(token,0)
        if not frequency:continue
        inverse=math.log(1+(count-frequencies.get(token,0)+.5)/(frequencies.get(token,0)+.5))
        score+=inverse*frequency*2.5/(frequency+1.5*(.25+.75*length/(average or 1)))
    return score

class ReviewRegistry:
    def __init__(self):
        pointer=json.loads((ROOT/'BENCHMARK_SNAPSHOT_PREPARATION.json').read_text(encoding='utf-8'))
        self.root=Path(pointer['path']).resolve()
        if not self.root.is_relative_to((ROOT/'state/benchmark_snapshots').resolve()):raise RuntimeError('Review snapshot containment')
        self.manifest_path=self.root/'MANIFEST.json';self.manifest_bytes=self.manifest_path.read_bytes();self.manifest=json.loads(self.manifest_bytes)
        raw=(self.root/'records.jsonl').read_bytes()
        if digest(raw)!=self.manifest['record_file_sha256']:raise RuntimeError('Review registry changed')
        self.records=[r for r in map(json.loads,raw.decode('utf-8').splitlines()) if not r['hold_reason']]
        from chatbot.normalization import tokenize_for_search
        self.tokenize=tokenize_for_search
        self.documents=[self.tokenize(' '.join([r['question'],r['category'],*r['alternate_questions']])) for r in self.records]
        self.frequency=Counter(t for doc in self.documents for t in set(doc));self.average=sum(map(len,self.documents))/(len(self.documents) or 1)
        self.exact={}
        for i,r in enumerate(self.records):
            for q in [r['question'],*r['alternate_questions']]:self.exact.setdefault(key(q),set()).add(i)
        self.authorized_digest=digest(self.manifest_bytes)

    def source_ok(self,record):
        relative=record['source_document'];copy=(self.root/'source_files'/relative).resolve()
        if not copy.is_relative_to((self.root/'source_files').resolve()):return False
        # Current original and pinned copy must agree; deletion/replacement holds.
        original=Path(r'\\10.100.175.10\Projects\Production\FP Branches + Forms\HR Training App')/relative
        try:return digest(copy.read_bytes())==record['source_sha256']==digest(original.read_bytes()) and digest(record['original_answer'].encode())==record['original_answer_sha256']
        except OSError:return False

    def ask(self,engine,question,conversation,actor):
        started=time.perf_counter();scope='review-bank:'+actor;cid=scope+':'+conversation
        plan=engine.catalog.plan(question,cid,scope);planning_ms=(time.perf_counter()-started)*1000
        contract=plan['request_contract'];services=plan.get('services',[])
        # Only explicit/resolved service assignments from the existing planner.
        exact=self.exact.get(key(question),set())
        if not services:
            entities=engine.catalog.entities(question);services=list(dict.fromkeys(e.get('service_id') for e in entities if e.get('service_id')))
        if not services and exact:
            # An authored alias may be underspecified across products: never
            # choose the provider from evidence availability.
            exact=set()
        retrieval_started=time.perf_counter();query=self.tokenize(question);ranked=[]
        for index,(record,document) in enumerate(zip(self.records,self.documents)):
            if not set(record['service_ids'])&set(services):continue
            score=bm25(query,document,self.frequency,len(self.records),self.average)
            if score>0:ranked.append((score,index))
        ranked.sort(reverse=True);selected=[]
        # Exact source-authored wording is a strong but deliberately narrow
        # reference contract. Other retrieval is returned as partial review,
        # never silently certified as a complete semantic answer.
        if len(exact)==1:
            i=next(iter(exact))
            if set(self.records[i]['service_ids'])&set(services):selected=[i]
        if not selected:
            for service in services:
                candidate=next((i for _,i in ranked if service in self.records[i]['service_ids']),None)
                if candidate is not None and candidate not in selected:selected.append(candidate)
        retrieval_ms=(time.perf_counter()-retrieval_started)*1000
        verify_started=time.perf_counter();admitted=[];gaps=[]
        if digest(self.manifest_path.read_bytes())!=self.authorized_digest:raise RuntimeError('Frozen review generation changed')
        for i in selected:
            if self.source_ok(self.records[i]):admitted.append(self.records[i])
            else:gaps.append({'reason':'source_version_changed_or_unavailable','record_id':self.records[i]['record_id']})
        language=plan.get('language','ar');english=language=='en'
        if english:gaps.append({'reason':'reviewed_english_view_missing','scope':'selected_original_arabic_source_records'})
        grounded_exact=len(exact)==1 and len(admitted)==1 and not gaps and not contract.get('unresolved_spans')
        if not grounded_exact and admitted:gaps.append({'reason':'semantic_question_to_reference_completeness_not_verified'})
        if not admitted:gaps.append({'reason':'no_source_bound_reference_for_resolved_request','services':services})
        classification=contract.get('task_mode',{}).get('mode')=='interpretation_only'
        if classification:admitted=[];grounded_exact=False;gaps=[{'reason':'classification_request_not_a_business_answer'}]
        # Original locators and source-bound literal views, never generated policy.
        citations=[{'fact_id':r['record_id'],'source_document':r['source_document'],'source_sha256':r['source_sha256'],'source_unit_id':r['authored_id'],'locator':r['locator']} for r in admitted]
        answer='UNAPPROVED ADMIN REVIEW BENCHMARK — original source references, not approved policy.\n\n'
        answer+='\n\n'.join(r['original_answer'] for r in admitted)
        if gaps:answer+='\n\nUnresolved / unavailable: '+', '.join(g['reason'] for g in gaps)
        verify_ms=(time.perf_counter()-verify_started)*1000
        # Recheck selected dependencies and generation immediately before output.
        final_started=time.perf_counter()
        if any(not self.source_ok(r) for r in admitted) or digest(self.manifest_path.read_bytes())!=self.authorized_digest:
            admitted=[];citations=[];grounded_exact=False;answer='The evidence snapshot changed; no business answer emitted.';gaps=[{'reason':'pre_emit_source_invalidation'}]
        final_ms=(time.perf_counter()-final_started)*1000
        if services:engine.store.set_business_context(cid,scope,{'services':services,'mentioned_services':services,'raw_question':question})
        return {'answer':answer,'answer_status':'complete' if grounded_exact else 'supported_partial' if admitted else 'clarify','complete':grounded_exact,'clarification_needed':not admitted,'gaps':gaps,'request_contract':contract,'review_retrieval_trace':[{'record_id':self.records[i]['record_id'],'score':score} for score,i in ranked[:8]],'citations':citations,'sources':[{'source_name':c['source_document'],'location_label':json.dumps(c['locator'],ensure_ascii=False),'source':c} for c in citations],'supported_fact_ids':[r['record_id'] for r in admitted],'backend':'existing_catalog_planner_Core_BM25_source_QA_review','native_acceptance':'NOT RUN','snapshot_id':self.manifest['snapshot_id'],'knowledge_mode':'admin_review_benchmark','normal_runtime_eligible':False,'fixture_only':True,'reply_language':'ar' if admitted else language,'requested_reply_language':language,'timings':{'interpretation_ms':planning_ms,'retrieval_ms':retrieval_ms,'source_verification_and_assembly_ms':verify_ms,'pre_emit_verification_ms':final_ms},'actual_model_calls':0,'embedding_calls':0,'retrieval_calls':len(services),'source_checks':len(selected)*2,'semantic_completeness_certified':grounded_exact,'scope_limitation':'Nonexact original-QA alignment is partial diagnostic output, not a semantic acceptance pass'}
