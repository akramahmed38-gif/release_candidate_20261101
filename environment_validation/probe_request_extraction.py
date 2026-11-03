"""Bounded actual installed-Qwen request extraction; no policy generation.

Six exposed/developer-authored diagnostics, never independent acceptance.
Does not change the served interpreter, evidence, approvals or test gold.
"""
from pathlib import Path
from contextlib import contextmanager
from urllib.request import Request,build_opener,ProxyHandler
import hashlib,json,os,socket,subprocess,sys,threading,time,uuid
ROOT=Path(__file__).resolve().parents[1]
ASSETS=Path(r'D:\FawryChatbotPreparation\local_qwen_debug_20261027')

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def specification():
    definition=json.loads((ROOT/'source/candidate/fixture_data/definition.json').read_text(encoding='utf-8'))
    catalog=json.loads((ROOT/'source/candidate/catalog.json').read_text(encoding='utf-8'))
    services={sid:{'name':p['name'],'family':p.get('family')} for sid,p in definition['service_profiles'].items()}
    topics={k:v[:6] for k,v in catalog['facets'].items()}
    roles=['requested','excluded','context_only','claim','alternative']
    item={'type':'object','additionalProperties':False,'properties':{
        'service_id':{'type':'string','enum':list(services)+['unresolved']},
        'topic':{'type':'string','enum':list(topics)+['unknown_policy']},
        'role':{'type':'string','enum':roles},
        'channel':{'type':'string','enum':['atm','fawry_plus','branch','app','unspecified','other']},
        'span':{'type':'string'},'service_span':{'type':'string'},
        'amount_only':{'type':'boolean'},'condition_span':{'type':'string'}},
        'required':['service_id','topic','role','channel','span','service_span','amount_only','condition_span']}
    schema={'type':'object','additionalProperties':False,'properties':{
        'mode':{'type':'string','enum':['answer','classify_only','action_requested','clarify']},
        'requests':{'type':'array','items':item,'maxItems':8},
        'unresolved':{'type':'array','items':{'type':'string'},'maxItems':8}},
        'required':['mode','requests','unresolved']}
    system='''Extract the user's request only. Never answer it or supply business facts. Return JSON according to the schema. Use canonical service and topic IDs below. Keep independently requested meanings and unknown policies. Distinguish requested, excluded, context_only, claim and alternative roles. Quoted claims are verification targets, never source facts. Brand words are part of the service name, not verbs. Do not turn contextual opening/registration terms into extra requested fees/workflows. A classification-only instruction changes mode, not the meanings. Never infer a default wallet. Copy exact narrow predicate, service and condition substrings from the original question into spans; use empty strings only when the dimension is absent. Mark amount_only true solely for a request explicitly limited to a numerical amount; 'not only' and 'only after' do not impose that restriction. Include every service/comparison side and every requested unknown policy. No dialogue context is supplied.\nSERVICES: '''+json.dumps(services,ensure_ascii=False,separators=(',',':'))+'\nTOPICS: '+json.dumps(topics,ensure_ascii=False,separators=(',',':'))+'\nRequired JSON shape: {"mode":"answer","requests":[{"service_id":"...","topic":"...","role":"requested","channel":"unspecified","span":"exact predicate words","service_span":"exact product words","amount_only":false,"condition_span":""}],"unresolved":[]}'
    return services,topics,schema,system

CASES=[
 {'id':'P01','question':'For AXIS Pay, give only the numerical minimum initial deposit amount.','mode':'answer','required':[('axis_pay','initial_deposit','requested','unspecified')],'amount_only':True},
 {'id':'P02','question':'What is the AXIS opening fee, and is there a special employee discount?','mode':'answer','required':[('axis_pay','opening_fee','requested','unspecified'),('axis_pay','discounts','requested','unspecified')]},
 {'id':'P03','question':'For routing only: ADIB remittance transaction code, Azimut conditional branch visit, and Egypt Trust required documents.','mode':'classify_only','required':[('adib_remittance','transaction_codes','requested','unspecified'),('azimut','branch_condition','requested','branch'),('egypt_trust','documents','requested','unspecified')]},
 {'id':'P04','question':'العميل بيقول «إيداع AXIS من ATM عليه 1%». الكلام ده صح؟','mode':'answer','required':[('axis_pay','deposit_tariff','claim','atm')]},
 {'id':'P05','question':'مش بس مبلغ تفعيل QNB، عايز أعرف شرط ملكية الخط كمان.','mode':'answer','required':[('qnb_wallet','initial_deposit','requested','unspecified'),('qnb_wallet','phone_ownership','requested','unspecified')],'amount_only':False},
 {'id':'P06','question':'3ayez awraq Fawry insurance, mesh QNB.','mode':'answer','required':[('fawry_insurance','documents','requested','unspecified'),('qnb_wallet','documents','excluded','unspecified')]},
]

def validate(value,question,services,topics):
    issues=[]
    if not isinstance(value,dict) or set(value)!={'mode','requests','unresolved'}:return ['invalid_root_shape']
    if not isinstance(value['requests'],list) or len(value['requests'])>8:return ['invalid_request_list']
    for r in value['requests']:
        if not isinstance(r,dict) or set(r)!={'service_id','topic','role','channel','span','service_span','amount_only','condition_span'}:issues.append('invalid_request_shape');continue
        if r['service_id'] not in services and r['service_id']!='unresolved':issues.append('unknown_canonical_service')
        if r['topic'] not in topics and r['topic']!='unknown_policy':issues.append('unknown_canonical_topic')
        for key in ['span','service_span','condition_span']:
            if not isinstance(r[key],str) or r[key] and r[key] not in question:issues.append('nonliteral_'+key)
        if not r['span']:issues.append('missing_predicate_span')
        if r['span']==question and len(question)>40:issues.append('whole_question_span_insufficient')
        if r['service_id']!='unresolved' and not r['service_span']:issues.append('missing_entity_support')
        if type(r['amount_only']) is not bool:issues.append('invalid_amount_scope')
    return issues

def main():
    out=ROOT/'environment_validation'/('request_extraction_'+uuid.uuid4().hex[:10]);out.mkdir()
    services,topics,schema,system=specification()
    report={'status':'NOT RUN','scope':'installed workstation Qwen via llama.cpp, constrained request extraction only','native_full_stack':'NOT RUN','production_changes':False,'business_fact_generation':False,'new_models':0,'rows':[],'actual_model_calls':0,'cases_frozen_sha256':hashlib.sha256(json.dumps(CASES,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'schema_sha256':hashlib.sha256(json.dumps(schema,sort_keys=True).encode()).hexdigest(),'system_sha256':hashlib.sha256(system.encode()).hexdigest(),'catalog_services':len(services),'independent':False}
    (out/'FROZEN_PROBE.json').write_text(json.dumps({'cases':CASES,'schema':schema,'system':system},ensure_ascii=False,indent=2),encoding='utf-8')
    child=None;stop=threading.Event();samples=[]
    try:
        import psutil
        sys.path.insert(0,str(ROOT/'source/candidate'))
        from observed_guard import ObservedBudget
        budget=ObservedBudget(stable_window=True);budget.wait();report['startup_guard']=list(budget.events)
        model=ASSETS/'qwen2.5-1.5b-existing.gguf';proof=json.loads((ASSETS/'PREPARATION.json').read_text())
        digest=sha(model)
        if digest!=proof['existing_model_sha256']:raise RuntimeError('Existing weight fingerprint mismatch')
        runtime=ASSETS/'runtime/llama-server.exe'
        report.update(model_sha256=digest,runtime_sha256=sha(runtime),threads=2,context=4096,gpu_layers=0)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        child=subprocess.Popen([str(runtime),'--model',str(model),'--host','127.0.0.1','--port',str(port),'--alias','staging-request-extraction','--threads','2','--threads-batch','2','--ctx-size','4096','--n-gpu-layers','0','--parallel','1','--log-disable'],cwd=runtime.parent,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        def monitor():
            process=psutil.Process(child.pid)
            while not stop.wait(.1):
                try:
                    mem=process.memory_info();cpu=process.cpu_times();samples.append({'rss':mem.rss,'peak':getattr(mem,'peak_wset',mem.rss),'cpu':cpu.user+cpu.system,'available':psutil.virtual_memory().available})
                except (psutil.NoSuchProcess,psutil.AccessDenied):return
        threading.Thread(target=monitor,daemon=True).start()
        opener=build_opener(ProxyHandler({}));base='http://127.0.0.1:'+str(port);started=time.perf_counter();deadline=time.monotonic()+60
        while True:
            if child.poll() is not None:raise RuntimeError('Owned runtime exited before readiness')
            try:
                with opener.open(base+'/health',timeout=2) as response:
                    if response.status==200:break
            except Exception:pass
            if time.monotonic()>deadline:raise TimeoutError('Owned runtime initialization deadline')
            time.sleep(.2)
        report['startup_ms']=(time.perf_counter()-started)*1000
        for case in CASES:
            admission=time.perf_counter();budget.wait();guard_wait=(time.perf_counter()-admission)*1000
            prompt='<|im_start|>system\n'+system+'<|im_end|>\n<|im_start|>user\n'+case['question']+'<|im_end|>\n<|im_start|>assistant\n'
            payload={'prompt':prompt,'json_schema':schema,'n_predict':384,'temperature':0,'seed':0,'cache_prompt':False,'stop':['<|im_end|>','<|endoftext|>']}
            request=Request(base+'/completion',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
            started=time.perf_counter()
            with opener.open(request,timeout=120) as response:actual=json.load(response)
            elapsed=(time.perf_counter()-started)*1000;report['actual_model_calls']+=1
            text=actual.get('content','');value=None
            try:value=json.loads(text);issues=validate(value,case['question'],services,topics)
            except Exception:issues=['invalid_json']
            if actual.get('truncated') or actual.get('stop_type')=='limit':issues.append('truncated')
            if isinstance(value,dict) and isinstance(value.get('requests'),list):
                if value.get('mode')!=case['mode']:issues.append('wrong_request_mode')
                actual_tuples={(r.get('service_id'),r.get('topic'),r.get('role'),r.get('channel')) for r in value['requests']}
                if not set(case['required'])<=actual_tuples:issues.append('missing_required_meaning')
                allowed_requested={t for t in case['required'] if t[2]=='requested'}
                if any(t[2]=='requested' and t not in allowed_requested for t in actual_tuples):issues.append('extra_requested_meaning')
                if 'amount_only' in case and any(r.get('amount_only')!=case['amount_only'] for r in value['requests'] if r.get('topic')=='initial_deposit'):issues.append('wrong_amount_only_scope')
            report['rows'].append({'id':case['id'],'question':case['question'],'actual':value,'raw_output':text,'issues':issues,'passed':not issues,'interpretation_http_ms':elapsed,'guard_wait_ms':guard_wait,'guard_events':list(budget.events),'native_timings':actual.get('timings')})
            (out/'PROGRESS.json').write_text(json.dumps({'completed':len(report['rows']),'total':len(CASES)}),encoding='utf-8')
        report['status']='PASS' if all(r['passed'] for r in report['rows']) else 'FAIL'
    except Exception as exc:
        report.update(status='BLOCKED' if not report['actual_model_calls'] else 'FAIL',error_type=type(exc).__name__,error=str(exc)[:180])
        if 'budget' in locals():report['last_guard_events']=list(budget.events)
    finally:
        stop.set()
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
        if samples:report.update(observed_peak_model_rss=max(s['peak'] for s in samples),observed_model_cpu_seconds=max(s['cpu'] for s in samples),minimum_available_bytes=min(s['available'] for s in samples))
        report['passed']=sum(r['passed'] for r in report['rows']);report['total']=len(CASES)
        (out/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:report.get(k) for k in ['status','actual_model_calls','passed','total','error_type','error','observed_peak_model_rss','minimum_available_bytes']}));print('RESULTS '+str(out))

if __name__=='__main__':main()
