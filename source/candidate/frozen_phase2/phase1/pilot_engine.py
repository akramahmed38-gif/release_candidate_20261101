"""Explicitly unapproved, three-fact fixture. Never imported by normal runtime."""
from pathlib import Path
from time import perf_counter
from collections import Counter
from types import SimpleNamespace
import ast,hashlib,json,math,re,sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'candidate'))
from chatbot.canonical_context import Planner,norm
from chatbot.query_language import normalize_franco,reply_language
from chatbot.normalization import tokenize_for_search
from chatbot.conversation_memory import ConversationStore
from chatbot.reference_validation import scoped_numeric_checks,business_numbers
from chatbot.semantic_claims import check_semantic_claims

ALLOWED={'F0010','F0011','F0012'}
ASPECTS={'opening_fee':'F0010','initial_deposit':'F0011','balance_treatment':'F0012'}
# Linguistic concepts only. Monetary values and answers are read from records.
CONCEPTS={
 'opening_fee':r'open(?:ing)?|subscription|sign.?up|registration fee|فتح|اشتراك|الاشتراك',
 'initial_deposit':r'activat\w*|minimum|initial|deposit|how much.{0,25}need|تفعيل|اقل|مبدئي|ايداع|الايداع|بكام',
 'balance_treatment':r'balanc\w*|remain\w*|stays?|disappear\w*|deduct\w*|رصيد|الرصيد|بتفضل|يفضل|تبقي|بتتخصم|تتخصم|تختفي|بتروح|بيروح',
}
OUTSIDE={
 'withdrawal':r'withdraw\w*|cash.?out|سحب|السحب',
 'kyc_documents':r'\bkyc\b|documents?|paperwork|eligibility|requirements?|\bID\b|مستند|اوراق|الاوراق|شروط|الشروط|بطاقه|هويه',
 'discounts':r'discount\w*|offers?|\bخصم\b|خصومات|عرض',
 'transfers':r'transfer\w*|remittance|تحويل|حواله',
 'transaction_codes':r'service code|transaction code|كود',
 'ongoing_balance_limit':r'(?:minimum|lowest).{0,15}(?:ongoing|remaining|maintained) balance|رصيد.{0,15}(?:دائم|طول الوقت)',
}

def sha_bytes(value):return hashlib.sha256(value).hexdigest()

def existing_bm25():
    """Load the unchanged pure scorer without importing optional Chroma locally."""
    path=ROOT/'candidate/chatbot/retrieval.py';tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='HybridRetriever')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_bm25_score')
    module=ast.Module(body=[method],type_ignores=[]);namespace={'Counter':Counter,'math':math}
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),namespace)
    return namespace['_bm25_score']

class LexicalBackend:
    mode='LOCAL_BM25_CORE_ONLY_NOT_NATIVE_RETRIEVAL_PROOF'
    def __init__(self,facts):
        self.facts=facts;self.score=existing_bm25()
        self.rows={fid:tokenize_for_search('AXIS Pay wallet '+f['arabic']+' '+f['english']+' '+f['aspect'].replace('_',' ')) for fid,f in facts.items()}
        corpus=list(self.rows.values());df=Counter(t for doc in corpus for t in set(doc))
        self.stats=SimpleNamespace(corpus=corpus,avg_doc_len=sum(map(len,corpus))/len(corpus),doc_freq=df)
    def search(self,question,aspects):
        start=perf_counter();tokens=tokenize_for_search(question+' AXIS '+ ' '.join(a.replace('_',' ') for a in aspects))
        scores={fid:self.score(self.stats,tokens,row) for fid,row in self.rows.items()}
        return list(self.facts),{'bm25_ms':(perf_counter()-start)*1000,'bm25_scores':scores,'backend':self.mode,'query_embedding_calls':0,'generation_calls':0}

class IsolationError(ValueError):pass

class FixtureEngine:
    def __init__(self,workspace,backend_factory=LexicalBackend,test_mode=False):
        if not test_mode:raise IsolationError('Unapproved fixture cannot run in normal mode')
        self.workspace=Path(workspace).resolve()
        marker=json.loads((self.workspace/'ISOLATED_TEST_ONLY.json').read_text(encoding='utf-8'))
        if marker!={'fixture_only':True,'production_use_allowed':False,'approvals_pending':True}:raise IsolationError('Missing isolation marker')
        definition=json.loads((ROOT/'fixture_data/fixture_definition.json').read_text(encoding='utf-8'))
        self.definition=definition;self.facts={f['fact_id']:f for f in definition['facts']}
        if set(self.facts)!=ALLOWED:raise IsolationError('Fixture scope differs from authorization')
        if any(f['normal_runtime_eligible'] or f['business_approved'] or f['human_fidelity_approved'] for f in self.facts.values()):raise IsolationError('Fixture must retain pending approvals')
        for f in self.facts.values():
            if sha_bytes(f['arabic'].encode())!=f['arabic_sha256'] or sha_bytes(f['english'].encode())!=f['english_sha256']:raise IsolationError('Rendering fingerprint differs')
            ok,reason=scoped_numeric_checks(f['arabic'],f['english'],'activation')
            if not ok:raise IsolationError('Unchanged numeric validator rejected fixture rendering')
            if not check_semantic_claims(f['arabic'],f['english'],'activation')['passed']:raise IsolationError('Fixture rendering condition rejected')
        self.store=ConversationStore();self.planner=Planner(definition['service_profiles'])
        self.backend=backend_factory(self.facts)

    def interpret(self,question,conversation,session):
        text=norm(normalize_franco(question));previous=self.store.get_business_context(conversation,session) or {}
        plan=self.planner.plan(question)
        # All aliases still pass through existing planner; add the supplied
        # Egyptian spelling as language equivalence, never as business data.
        explicit_axis=bool(re.search(r'\baxis\b|اكسس|اكسيس|اكسس باي',text))
        services=list(plan.services)
        if explicit_axis and 'axis_pay' not in services:services.append('axis_pay')
        foreign=[s for s in services if s!='axis_pay']
        unknown=bool(re.search(r'paypal|vodafone|orange|etisalat|bankxyz|فودافون|اورنج|اتصالات',text))
        if unknown:foreign.append('unsupported_named_service')
        selected={a for a,rx in CONCEPTS.items() if re.search(rx,text,re.I)}
        outside={a for a,rx in OUTSIDE.items() if re.search(rx,text,re.I)}
        if 'ongoing_balance_limit' in outside and not re.search(r'initial|deposit|activat|مبدئي|ايداع|تفعيل',text):selected.clear()
        tariff=bool(re.search(r'deposits?|cash.?in|ايداع',text) and re.search(r'fees?|charges?|rates?|رسوم|عموله',text))
        initial_scope=bool(re.search(r'initial|minimum|activat|open|balanc|مبدئي|اقل|تفعيل|فتح|رصيد',text))
        if tariff and not initial_scope:outside.add('cash_in_transaction_tariff');selected.clear()
        followup=bool(previous) and not selected and re.search(r'what about|and |does it|those|طيب|وهل|بالنسبه|بتفضل|الرصيد',text,re.I)
        if followup:selected=set(previous.get('aspects',[]))
        # A request about an unsupported transaction's fee is not an opening fee.
        if outside and not re.search(CONCEPTS['opening_fee']+'|'+CONCEPTS['initial_deposit']+'|'+CONCEPTS['balance_treatment'],text,re.I):selected.clear()
        if 'balance_treatment' in selected:selected.add('initial_deposit')
        if 'initial_deposit' in selected:selected.add('balance_treatment')
        if selected and re.search(r'\bfee\b|charges?|cost|بتتخصم|تتخصم|رسوم|مصاريف',text,re.I) and not outside:selected.add('opening_fee')
        if re.search(r'activat\w*.{0,15}(?:cost|fee|بكام)|تفعيل.{0,15}بكام',text,re.I):selected.update(ASPECTS)
        if 'opening_fee' in selected and re.search(r'deposit|initial|activate|تفعيل|ايداع|عشرين',text,re.I):selected.update(ASPECTS)
        if 'opening_fee' in selected and re.search(r'\d|twenty|عشرين',text):selected.update(ASPECTS)
        # Declared fixture context can resolve generic "the wallet", never an
        # explicit foreign provider. Explicit foreign-service requests get no AXIS facts.
        axis=explicit_axis or (not services and not foreign)
        if foreign and not explicit_axis:axis=False;selected.clear()
        if axis and selected:self.store.set_business_context(conversation,session,{'services':['axis_pay'],'aspects':sorted(selected)})
        language='en' if re.search(r'in english|بالانجليزي',text) else reply_language(question)
        return {'axis':axis,'aspects':sorted(selected),'unsupported':sorted(outside|{'service:'+s for s in foreign}),'language':language,'context_used':bool(followup),'fixture_default_service':not services and not explicit_axis and not foreign}

    def ask(self,question,conversation='isolated',session='synthetic'):
        start=perf_counter();timings={};result={'fixture_only':True,'approvals_pending':True,'normal_runtime_eligible':False,'label':'UNAPPROVED TEST FIXTURE - NOT PRODUCTION','generation_calls':0,'translation_calls':0}
        stamp=perf_counter();intent=self.interpret(question,conversation,session);timings['interpretation_ms']=(perf_counter()-stamp)*1000
        result['interpretation']=intent
        language=intent['language']
        wanted=[ASPECTS[a] for a in ASPECTS if a in intent['aspects']]
        stamp=perf_counter();source=self.workspace/'source_files'/self.definition['source_document']
        try:
            state=json.loads((self.workspace/'test_eligibility.json').read_text(encoding='utf-8'))
            valid=(state.get('fixture_only') is True and state.get('production_use_allowed') is False and
                   state.get('source_sha256')==self.definition['source_sha256'] and sha_bytes(source.read_bytes())==self.definition['source_sha256'])
            authorized=set(state.get('authorized_test_fact_ids',[]))
            if not authorized<=ALLOWED:valid=False
        except (OSError,ValueError):valid=False;authorized=set()
        timings['source_and_test_authorization_ms']=(perf_counter()-stamp)*1000
        blocked=[];available=[];retrieval={}
        if not valid:blocked=['source_or_test_authorization_invalid']
        elif not intent['axis'] or not wanted:blocked=intent['unsupported'] or ['question_outside_test_scope_or_ambiguous']
        else:
            stamp=perf_counter();retrieved,retrieval=self.backend.search(question,intent['aspects']);timings['retrieval_ms']=(perf_counter()-stamp)*1000
            available=[fid for fid in wanted if fid in authorized and fid in retrieved]
            blocked=[fid+':revoked_or_not_retrieved' for fid in wanted if fid not in available]+intent['unsupported']
        texts=[];citations=[];stamp=perf_counter()
        for fid in available:
            f=self.facts[fid];text=f['english'] if language=='en' else f['arabic']
            # No wording is generated: each output is an immutable source-bound
            # rendering, plus separate presentation text and original citation.
            assert sha_bytes(text.encode())==f['english_sha256' if language=='en' else 'arabic_sha256']
            ok,_=scoped_numeric_checks(f['arabic'],f['english'],'activation')
            if not ok:raise IsolationError('Numeric rendering verification failed')
            if language=='ar' and business_numbers(text)!=business_numbers(f['arabic']):raise IsolationError('Arabic numeric identity failed')
            if language=='en' and re.search(r'[\u0621-\u064a]',text):raise IsolationError('Arabic leakage in English view')
            texts.append(text);citations.append({'fact_id':fid,'source_document':self.definition['source_document'],'page':1,'source_sha256':self.definition['source_sha256'],'evidence_unit_id':f['source_unit_id'],'unit_text_sha256':f['unit_text_sha256'],'test_only':True})
        timings['validation_and_assembly_ms']=(perf_counter()-stamp)*1000
        complete=bool(available) and not blocked and len(available)==len(wanted)
        result.update(type='answer' if available else 'unavailable',complete=complete,supported_fact_ids=available,unsupported_components=blocked,citations=citations,reply_language=language,retrieval=retrieval)
        banner='UNAPPROVED TEST FIXTURE - approvals pending.' if language=='en' else 'اختبار معزول غير معتمد؛ الموافقات ما زالت معلقة.'
        scope='Financial test scope only; this is not a complete KYC or eligibility checklist.' if language=='en' else 'نطاق الاختبار هو المعلومات المالية دي فقط. باقي شروط الفتح والمستندات خارج النطاق.'
        gap=('Unverified in this test: '+', '.join(blocked)) if language=='en' else ('أجزاء غير متاحة في الاختبار: '+', '.join(blocked))
        result['answer']='\n\n'.join([banner]+texts+([gap] if blocked else [])+[scope])
        result['timings_ms']={**timings,'engine_total_ms':(perf_counter()-start)*1000}
        return result
