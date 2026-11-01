"""Bounded source-view expansion. No generation and no policy approval."""
from pathlib import Path
from time import perf_counter
import hashlib,json,re,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'frozen_phase2/phase1'))
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
        self.rows={fid:tokenize_for_search(f['service_label']+' '+f['arabic']+' '+f['english']+' '+f['aspect'].replace('_',' ')) for fid,f in facts.items()}
        corpus=list(self.rows.values())
        self.stats=SimpleNamespace(corpus=corpus,avg_doc_len=sum(map(len,corpus))/len(corpus),doc_freq=Counter(t for doc in corpus for t in set(doc)))
    def search_slot(self,question,service,topic,ids):
        found,meta=self.search(question,[topic]);return [f for f in found if f in ids],meta

class MultiEngine:



    def ask(self,q,conversation='fixture',session='synthetic'):
        started=perf_counter();t=perf_counter();intent=self.interpret(q,conversation,session);timing={'interpretation_ms':(perf_counter()-t)*1000}
        t=perf_counter();valid_sources={};source_reads=0
        state=json.loads((self.workspace/'test_eligibility.json').read_text())
        global_ok=state.get('fixture_only') is True and state.get('production_use_allowed') is False
        for path,expected in self.definition['sources'].items():
            try:valid_sources[path]=sha_bytes((self.workspace/'source_files'/path).read_bytes())==expected;source_reads+=1
            except OSError:valid_sources[path]=False
        timing['source_verification_ms']=(perf_counter()-t)*1000
        authorized=set(state.get('authorized_test_fact_ids',[]));global_ok=global_ok and authorized<=set(self.definition['authorized_test_ids'])
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
        for service in dict.fromkeys(f['service_id'] for f in self.facts.values()):
            ids=[f for f in selected if self.facts[f]['service_id']==service]
            if not ids:continue
            ids.sort(key=lambda fid:self.facts[fid].get('sequence_order') or int(fid[1:]))
            views=[]
            for fid in ids:
                fact=self.facts[fid];view=fact['english' if language=='en' else 'arabic']
                if sha_bytes(view.encode())!=fact[('english' if language=='en' else 'arabic')+'_sha256']:raise IsolationError('View changed')
                if language=='en' and re.search(r'[\u0621-\u064a]',view):raise IsolationError('Arabic leakage')
                if not scoped_numeric_checks(fact['arabic'],fact['english'],fact['validation_topic'])[0]:raise IsolationError('Numeric mismatch')
                views.append(view)
                citations.append({'fact_id':fid,'service_id':service,'source_document':fact['source_document'],'source_sha256':fact['source_sha256'],'evidence_unit_id':fact['source_unit_id'],'unit_text_sha256':fact['unit_text_sha256'],'locator':fact['locator'],'test_only':True})
            if any(self.facts[fid].get('procedure_contract')=='myfawry_navigation' for fid in ids) and len(ids)==6:
                source=' '.join(self.facts[f]['arabic'] for f in ids);english=' '.join(self.facts[f]['english'] for f in ids)
                # Only an exact immutable source-view has this grammatical
                # reference normalized for the existing closed vocabulary.
                # No action, condition or generated answer is removed.
                from workflow_view import audit_source_view
                audit=audit_source_view(source,english,self.facts[ids[-1]]['english_sha256'])
                if not audit['passed']:raise IsolationError('Existing workflow contract rejected ordered view')
            groups.append(self.definition['service_profiles'][service]['name']+':\n'+'\n'.join(views))
        def gap_label(slot):
            provider=self.definition['service_profiles'].get(slot['service_id'],{}).get('name',slot['service_id'])
            key=slot['topic'].split(' / ')[0]
            aliases=self.catalog.catalog['facets'].get(key,[])
            wanted=[a for a in aliases if bool(re.search(r'[\u0621-\u064a]',a))==(language=='ar')]
            label=wanted[0] if wanted else key.replace('_',' ')
            if ' / missing channel ' in slot['topic']:label+=' ('+slot['topic'].split(' / missing channel ')[1].replace('_',' ')+')'
            return provider+' / '+label
        gaps=[gap_label(s) for s in slots if not s['complete']]
        complete=bool(selected) and not gaps
        banner='UNAPPROVED TEST FIXTURE — approvals pending.' if language=='en' else 'اختبار معزول غير معتمد؛ الموافقات معلقة.'
        scope='Only the selected source references are covered; this is not a complete eligibility checklist or end-to-end service procedure.' if language=='en' else 'الإجابة محددة بالمراجع المتاحة، وليست قائمة كاملة بشروط الفتح أو إجراءات الخدمة.'
        gap=('Unavailable or held: ' if language=='en' else 'أجزاء غير متاحة أو معلقة: ')+', '.join(gaps)
        timing.update(validation_and_assembly_ms=(perf_counter()-t)*1000,engine_total_ms=(perf_counter()-started)*1000)
        return {'fixture_only':True,'approvals_pending':True,'normal_runtime_eligible':False,'type':'answer' if selected else 'unavailable','complete':complete,'supported_fact_ids':selected,'slots':slots,'citations':citations,'answer':'\n\n'.join([banner]+groups+([gap] if gaps else [])+[scope]),'reply_language':language,'interpretation':intent,'timings_ms':timing,'source_cache':{'cache_hits':0,'files_hashed':source_reads,'policy':'verify fixture originals on every request'},'generation_calls':0,'translation_calls':0}
