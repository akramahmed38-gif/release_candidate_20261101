"""Bounded source-view expansion. No generation and no policy approval."""
from pathlib import Path
from time import perf_counter
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'phase1'))
from pilot_engine import FixtureEngine as Phase1Engine,LexicalBackend,IsolationError,sha_bytes
from chatbot.canonical_context import Planner,norm
from chatbot.query_language import reply_language,normalize_franco
from chatbot.conversation_memory import ConversationStore
from chatbot.reference_validation import scoped_numeric_checks,business_numbers
from chatbot.workflow_contract import audit_workflow

SERVICES={'axis_pay':'AXIS Pay','qnb_wallet':'QNB Wallet','azimut':'Azimut'}
RX={'axis_pay':r'\baxis\b|اكسيس|اكسس','qnb_wallet':r'\bqnb\b|كيو ان بي','azimut':r'azimut|ازيموت'}
TOPICS={
 'opening_fee':r'open(?:ing)?|subscription|sign.?up|فتح|اشتراك',
 'initial_deposit':r'activat\w*|initial|minimum|funding|deposit|put in|تفعيل|اقل|ايداع|بكام',
 'balance_treatment':r'balanc\w*|remain|stay|deduct|disappear|رصيد|بتفضل|بتتخصم',
 'workflow':r'workflow|navigation|navigate|steps|register|registration|خطوات|تسجيل|استثمار',
 'branch_condition':r'branch|visit|فرع|زياره|يزور',
 'documents':r'\bkyc\b|documents?|paperwork|eligibility|requirements?|مستند|اوراق|شروط',
 'withdrawal':r'withdraw|cash.?out|سحب',
 'deposit_tariff':r'(?:deposit|cash.?in)\s+(?:fees?|charges?|tariffs?)|رسوم الايداع',
 'discounts':r'discount|\bخصم\b|خصومات',
}

class CoreBackend(LexicalBackend):
    mode='CORE_ONLY_SCOPED_EXISTING_BM25'
    def __init__(self,facts):
        super().__init__(facts)
        from chatbot.normalization import tokenize_for_search
        from collections import Counter
        from types import SimpleNamespace
        self.rows={fid:tokenize_for_search(SERVICES[f['service_id']]+' '+f['arabic']+' '+f['english']+' '+f['aspect'].replace('_',' ')) for fid,f in facts.items()}
        corpus=list(self.rows.values())
        self.stats=SimpleNamespace(corpus=corpus,avg_doc_len=sum(map(len,corpus))/len(corpus),doc_freq=Counter(t for doc in corpus for t in set(doc)))
    def search_slot(self,question,service,topic,ids):
        found,meta=self.search(question,[topic]);return [f for f in found if f in ids],meta

class MultiEngine:
    def __init__(self,workspace,backend_factory=CoreBackend,test_mode=False):
        if not test_mode:raise IsolationError('Test-only candidate')
        self.workspace=Path(workspace)
        marker=json.loads((self.workspace/'ISOLATED_TEST_ONLY.json').read_text())
        if marker!={'fixture_only':True,'production_use_allowed':False,'approvals_pending':True}:raise IsolationError('Isolation marker differs')
        self.definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
        self.facts={f['fact_id']:f for f in self.definition['facts']}
        if set(self.facts)!={'F0010','F0011','F0012','F0073',*[f'F{i:04d}' for i in range(37,43)]}:raise IsolationError('Unauthorized fixture scope')
        for f in self.facts.values():
            if any(f.get(k) for k in ['normal_runtime_eligible','business_approved','human_fidelity_approved']):raise IsolationError('Pending approval boundary')
            for key in ['arabic','english']:
                if sha_bytes(f[key].encode())!=f[key+'_sha256']:raise IsolationError('Rendering identity differs')
            if not scoped_numeric_checks(f['arabic'],f['english'],'workflow' if f['service_id']=='azimut' else 'activation')[0]:raise IsolationError('Existing numerical validator failed')
        self.phase1=Phase1Engine(self.workspace/'phase1',test_mode=True)
        self.planner=Planner(self.definition['service_profiles']);self.store=ConversationStore()
        self.backend=backend_factory(self.facts)

    def interpret(self,q,cid,sid):
        text=norm(normalize_franco(q));previous=self.store.get_business_context(cid,sid) or {}
        planned=list(self.planner.plan(q).services)
        explicit=[s for s,rx in RX.items() if re.search(rx,text,re.I)]
        foreign=[s for s in planned if s not in SERVICES]
        if re.search(r'vodafone|paypal|orange|فودافون|اورنج',text):foreign.append('unsupported_named_service')
        topics=[t for t,rx in TOPICS.items() if re.search(rx,text,re.I)]
        if 'deposit_tariff' in topics:topics=[t for t in topics if t!='initial_deposit']
        followup=False
        if explicit:
            services=explicit
            if not topics and previous:
                topics=previous.get('topics',[]);followup=True
                if explicit!=previous.get('services') and 'initial_deposit' in topics and 'balance_treatment' in topics:topics=[t for t in topics if t!='balance_treatment']
        elif foreign:services=[]
        elif previous:
            services=previous.get('services',[]);followup=True
            if re.search(r'which one|both|اي واحد|مين فيهم|الاتنين',text):services=previous.get('comparison_services',services)
            if not topics:topics=previous.get('topics',[])
        else:services=['axis_pay'] if not re.search(r'which one|and that|what about|اي واحد',text) else []
        if services==['axis_pay'] and not foreign:
            axis=self.phase1.interpret(q,cid,sid)
            topics=axis['aspects']+list(axis['unsupported'])
        if not topics:topics=['unspecified']
        pieces=re.split(r';|\band\b|\sو\s',text)
        bindings={}
        for part in pieces:
            ss=[s for s,rx in RX.items() if re.search(rx,part,re.I)]
            tt=[t for t,rx in TOPICS.items() if re.search(rx,part,re.I)]
            if len(ss)==1 and tt:bindings.setdefault(ss[0],set()).update(tt)
        independent=len(services)>1 and set(bindings)==set(services)
        slots=[]
        for service in services:
            chosen=sorted(bindings[service]) if independent else topics
            for topic in chosen:
                if topic=='initial_deposit' and re.search(r'fee|cost|بكام|رسوم|بتتخصم',text) and 'deposit_tariff' not in topics and service=='axis_pay':
                    if (service,'opening_fee') not in slots:slots.append((service,'opening_fee'))
                if (service,topic) not in slots:slots.append((service,topic))
        comparison=list(dict.fromkeys(previous.get('comparison_services',[])+services))
        if services:self.store.set_business_context(cid,sid,{'services':services,'topics':topics,'comparison_services':comparison})
        return {'services':services,'topics':topics,'slots':slots,'foreign':foreign,'context_used':followup,'language':reply_language(q)}

    def required(self,service,topic):
        if service=='axis_pay':return {'opening_fee':['F0010'],'initial_deposit':['F0011','F0012'],'balance_treatment':['F0011','F0012']}.get(topic,[])
        if service=='qnb_wallet':return ['F0073'] if topic=='initial_deposit' else []
        if service=='azimut':return [f'F{i:04d}' for i in range(37,43)] if topic=='workflow' else ['F0042'] if topic=='branch_condition' else []
        return []

    def ask(self,q,conversation='fixture',session='synthetic'):
        started=perf_counter();t=perf_counter();intent=self.interpret(q,conversation,session);timing={'interpretation_ms':(perf_counter()-t)*1000}
        t=perf_counter();valid_sources={};source_reads=0
        state=json.loads((self.workspace/'test_eligibility.json').read_text())
        global_ok=state.get('fixture_only') is True and state.get('production_use_allowed') is False
        for path,expected in self.definition['sources'].items():
            try:valid_sources[path]=sha_bytes((self.workspace/'source_files'/path).read_bytes())==expected;source_reads+=1
            except OSError:valid_sources[path]=False
        timing['source_verification_ms']=(perf_counter()-t)*1000
        authorized=set(state.get('authorized_test_fact_ids',[]));global_ok=global_ok and authorized<=set(self.facts)
        slots=[];selected=[];retrieval_ms=0;selection_ms=0
        for service,topic in intent['slots']:
            t=perf_counter();required=self.required(service,topic);selection_ms+=(perf_counter()-t)*1000
            reasons=[];available=[];retrieval={}
            if not required:reasons=['held_conflicting_or_outside_selected_evidence']
            elif not global_ok:reasons=['test_authorization_invalid']
            elif any(not valid_sources[self.facts[f]['source_document']] for f in required):reasons=['source_version_invalid']
            elif any(f not in authorized or state.get('rendering_fingerprints',{}).get(f)!=self.facts[f]['english_sha256'] for f in required):reasons=['test_eligibility_or_rendering_revoked']
            else:
                t=perf_counter();found,retrieval=self.backend.search_slot(q,service,topic,required);retrieval_ms+=(perf_counter()-t)*1000
                if not set(required)<=set(found):reasons=['required_evidence_not_retrieved']
                else:available=required
            selected.extend(f for f in available if f not in selected)
            slots.append({'service_id':service,'topic':topic,'required_fact_ids':required,'supported_fact_ids':available,'complete':bool(available) and not reasons,'gap_reasons':reasons,'retrieval':retrieval})
        for service in intent['foreign']:slots.append({'service_id':service,'topic':'unsupported_service','required_fact_ids':[],'supported_fact_ids':[],'complete':False,'gap_reasons':['unsupported_service']})
        if not slots:slots=[{'service_id':'unresolved','topic':'unspecified','complete':False,'supported_fact_ids':[],'gap_reasons':['ambiguous_followup']}]
        timing.update(retrieval_ms=retrieval_ms,fact_selection_ms=selection_ms)
        t=perf_counter();language=intent['language'];citations=[];groups=[]
        for service in SERVICES:
            ids=[f for f in selected if self.facts[f]['service_id']==service]
            if not ids:continue
            ids.sort(key=lambda fid:self.facts[fid].get('sequence_order') or int(fid[1:]))
            views=[]
            for fid in ids:
                fact=self.facts[fid];view=fact['english' if language=='en' else 'arabic']
                if sha_bytes(view.encode())!=fact[('english' if language=='en' else 'arabic')+'_sha256']:raise IsolationError('View changed')
                if language=='en' and re.search(r'[\u0621-\u064a]',view):raise IsolationError('Arabic leakage')
                if not scoped_numeric_checks(fact['arabic'],fact['english'],'workflow' if service=='azimut' else 'activation')[0]:raise IsolationError('Numeric mismatch')
                views.append(view)
                citations.append({'fact_id':fid,'service_id':service,'source_document':fact['source_document'],'source_sha256':fact['source_sha256'],'evidence_unit_id':fact['source_unit_id'],'unit_text_sha256':fact['unit_text_sha256'],'locator':fact['locator'],'test_only':True})
            if service=='azimut' and len(ids)==6:
                source=' '.join(self.facts[f]['arabic'] for f in ids);english=' '.join(self.facts[f]['english'] for f in ids)
                # Only an exact immutable source-view has this grammatical
                # reference normalized for the existing closed vocabulary.
                # No action, condition or generated answer is removed.
                from workflow_view import audit_source_view
                audit=audit_source_view(source,english,self.facts['F0042']['english_sha256'])
                if not audit['passed']:raise IsolationError('Existing workflow contract rejected ordered view')
            groups.append(SERVICES[service]+':\n'+'\n'.join(views))
        gaps=[s['service_id']+' / '+s['topic'] for s in slots if not s['complete']]
        complete=bool(selected) and not gaps
        banner='UNAPPROVED TEST FIXTURE — approvals pending.' if language=='en' else 'اختبار معزول غير معتمد؛ الموافقات معلقة.'
        scope='Only the selected financial facts and app navigation are covered; this is not a complete KYC or eligibility checklist.' if language=='en' else 'النطاق هو الحقائق المالية المختارة وخطوات التطبيق فقط، وليس قائمة كاملة بشروط الفتح أو المستندات.'
        gap=('Unavailable or held: ' if language=='en' else 'أجزاء غير متاحة أو معلقة: ')+', '.join(gaps)
        timing.update(validation_and_assembly_ms=(perf_counter()-t)*1000,engine_total_ms=(perf_counter()-started)*1000)
        return {'fixture_only':True,'approvals_pending':True,'normal_runtime_eligible':False,'type':'answer' if selected else 'unavailable','complete':complete,'supported_fact_ids':selected,'slots':slots,'citations':citations,'answer':'\n\n'.join([banner]+groups+([gap] if gaps else [])+[scope]),'reply_language':language,'interpretation':intent,'timings_ms':timing,'source_cache':{'cache_hits':0,'files_hashed':source_reads,'policy':'verify fixture originals on every request'},'generation_calls':0,'translation_calls':0}
