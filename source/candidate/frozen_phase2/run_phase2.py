from pathlib import Path
from time import perf_counter
from urllib.request import Request,build_opener,ProxyHandler
import argparse,json,hashlib,shutil,threading,time,uuid,sys,os,traceback
from engine import ROOT,MultiEngine,IsolationError
from run_pilot import make_server,memory,guard,prepare_workspace

def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.pending')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def prepare(work):
    work.mkdir(parents=True)
    shutil.copytree(ROOT/'fixture_data/source_files',work/'source_files')
    prepare_workspace(work/'phase1')
    definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
    save(work/'ISOLATED_TEST_ONLY.json',{'fixture_only':True,'production_use_allowed':False,'approvals_pending':True})
    save(work/'test_eligibility.json',{'fixture_only':True,'production_use_allowed':False,'authorized_test_fact_ids':[f['fact_id'] for f in definition['facts']],'rendering_fingerprints':{f['fact_id']:f['english_sha256'] for f in definition['facts']}})

def preservation(app):
    base=guard(app) if app else None
    if app:
        definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
        for relative,expected in definition['sources'].items():
            digest=hashlib.sha256((app/relative).read_bytes()).hexdigest()
            if digest!=expected:raise ValueError('Current original source differs')
            base['phase2_source:'+relative]=digest
    return base

def grade(case,response,facts):
    issues=[]
    if response.get('complete')!=case['complete']:issues.append('completeness')
    if set(response.get('supported_fact_ids',[]))!=set(case['facts']):issues.append('fact_coverage')
    if response.get('reply_language')!=case['language']:issues.append('language')
    if response.get('normal_runtime_eligible') is not False or not response.get('fixture_only') or not response.get('approvals_pending'):issues.append('isolation')
    if response.get('generation_calls')!=0 or response.get('translation_calls')!=0:issues.append('forbidden_generation')
    citations=response.get('citations',[])
    if set(c['fact_id'] for c in citations)!=set(case['facts']):issues.append('citations')
    for c in citations:
        f=facts[c['fact_id']]
        if any(c[k]!=f[k] for k in ['service_id','source_document','source_sha256','locator']):issues.append('wrong_source_or_provider')
        if c['evidence_unit_id']!=f['source_unit_id']:issues.append('wrong_evidence')
        if f['english' if case['language']=='en' else 'arabic'] not in response['answer']:issues.append('altered_claim')
    return sorted(set(issues))

def main(args):
    os.environ['ANONYMIZED_TELEMETRY']='False';os.environ['OTEL_SDK_DISABLED']='true'
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    runid=args.run_id or time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    if not __import__('re').fullmatch(r'\d{8}_\d{6}_[a-f0-9]{8}',runid):raise ValueError('Invalid run ID')
    out=(args.output or ROOT/'runs')/runid;out.mkdir(parents=True,exist_ok=False)
    save(out/'PROGRESS.json',{'status':'initializing','run_id':runid})
    try:
        work=out/'private_fixture';prepare(work);before=preservation(args.app);start=perf_counter()
        if args.backend=='native':
            from retrieval import NativeBackend
            factory=lambda facts:NativeBackend(facts,work)
        else:
            from engine import CoreBackend
            factory=CoreBackend
        engine=MultiEngine(work,factory,test_mode=True)
        save(out/'INITIALIZATION.json',{'backend':engine.backend.mode,'startup_ms':(perf_counter()-start)*1000,'details':getattr(engine.backend,'initialization',{}),'memory':memory()})
        server=make_server(engine);threading.Thread(target=server.serve_forever,daemon=True).start()
        url='http://127.0.0.1:'+str(server.server_port);opener=build_opener(ProxyHandler({}));results=[]
        def request(question,cid,sid):
            start=perf_counter();cpu=time.process_time()
            data=json.dumps({'question':question,'conversation_id':cid,'session_id':sid},ensure_ascii=False).encode()
            try:
                with opener.open(Request(url+'/ask',data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:value=json.load(response)
            except Exception as exc:value={'execution_error_type':type(exc).__name__}
            return value,{'http_ms':(perf_counter()-start)*1000,'process_cpu_ms':(time.process_time()-cpu)*1000,**memory()}
        original=json.loads((ROOT/'phase1/test_cases.json').read_text(encoding='utf-8'))['cases']
        cases=[{**c,'id':'P1_'+c['id']} for c in original]+json.loads((ROOT/'test_cases.json').read_text(encoding='utf-8'))['cases']
        try:
            for c in cases:
                cid=c.get('conversation',c['id']);setup=None
                if c.get('setup'):setup=request(c['setup'],cid,cid)[0]
                value,timing=request(c['question'],cid,cid);issues=grade(c,value,engine.facts)
                results.append({'id':c['id'],'question':c['question'],'expected':c,'actual':value,'measurements':timing,'issues':issues,'passed':not issues,'setup':setup})
                save(out/'RESULTS.json',results);save(out/'PROGRESS.json',{'status':'running','completed':len(results),'target':len(cases),'failed':sum(not r['passed'] for r in results)})
            def mutation(identity,question,expected,complete=False):
                value,timing=request(question,identity,identity)
                case={'facts':expected,'complete':complete,'language':'en'}
                issues=grade(case,value,engine.facts)
                results.append({'id':identity,'question':question,'expected':case,'actual':value,'measurements':timing,'issues':issues,'passed':not issues})
            source=work/'source_files/KnowledgeBase/Articles/Wallets_ART.md';data=source.read_bytes()
            source.write_bytes(data+b'\nTEST INVALIDATION')
            mutation('SOURCE_QNB_CHANGED','Compare AXIS and QNB initial activation deposits.',['F0011','F0012']);source.write_bytes(data)
            source=work/'source_files/KnowledgeBase/Articles/AZIMUT_ART.md';data=source.read_bytes();source.unlink()
            mutation('SOURCE_AZIMUT_DELETED','AXIS opening fee; Azimut registration steps.',['F0010']);source.write_bytes(data)
            auth=work/'test_eligibility.json';original_auth=auth.read_bytes();state=json.loads(original_auth);state['authorized_test_fact_ids'].remove('F0040');save(auth,state)
            mutation('MIDDLE_STEP_REVOKED','AXIS opening fee; Azimut registration steps.',['F0010']);auth.write_bytes(original_auth)
            state=json.loads(original_auth);state['rendering_fingerprints']['F0073']='revoked';save(auth,state)
            mutation('LANGUAGE_VIEW_REVOKED','Compare AXIS and QNB initial activation deposits.',['F0011','F0012']);auth.write_bytes(original_auth)
            state=json.loads(original_auth);state['production_use_allowed']=True;save(auth,state)
            mutation('PRODUCTION_FLAG_REJECTED','Compare AXIS and QNB initial activation deposits.',[]);auth.write_bytes(original_auth)
            try:MultiEngine(work,test_mode=False);rejected=False
            except IsolationError:rejected=True
            results.append({'id':'NORMAL_MODE_REJECTED','passed':rejected})
        finally:server.shutdown();server.server_close()
        after=preservation(args.app)
        numeric=hashlib.sha256((ROOT/'phase1/candidate/chatbot/reference_validation.py').read_bytes()).hexdigest()
        from chatbot.reference_validation import scoped_numeric_checks
        probes=[not scoped_numeric_checks('Service code 73157.','Service code 73158.','transaction_codes')[0],not scoped_numeric_checks('Fawry Plus: 1%. ATM: 0.75%.','Fawry Plus: 0.75%. ATM: 1%.','withdrawal')[0],not scoped_numeric_checks('إيداع 20 جنيه، يستقر في رصيد العميل.','An activation fee of 20 EGP.','activation')[0]]
        preserved=before==after
        passed=all(r['passed'] for r in results) and preserved and all(probes) and numeric=='9eb736461247aaa7f89347bb8284113c9bd51b5d3e6f954b31b4e4d665ac2848'
        summary={'run_id':runid,'status':'completed','technical_checks_passed':passed,'backend':engine.backend.mode,'main_cases':len(cases),'integrity_checks':6,'failed_ids':[r['id'] for r in results if not r['passed']],'numeric_validator_sha256':numeric,'numeric_rejection_probes_passed':all(probes),'preservation_checks_passed':preserved,'approvals_pending':True,'generation_calls':0,'translation_calls':0,'document_embedding_calls':0,'memory':memory(),'decision':'TECHNICAL_GO_FOR_REVIEW_ONLY' if passed and args.backend=='native' else 'CORE_PASS_NATIVE_PENDING' if passed else 'NO_GO'}
        save(out/'RESULTS.json',results);save(out/'SUMMARY.json',summary);save(out/'PROGRESS.json',summary)
        print(json.dumps(summary),flush=True)
    except Exception as exc:
        save(out/'PROGRESS.json',{'status':'blocked','error_type':type(exc).__name__,'safe_stack':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)]})
        print(json.dumps({'run_id':runid,'status':'blocked','error_type':type(exc).__name__}),flush=True);raise SystemExit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['core','native'],default='core');p.add_argument('--output',type=Path);p.add_argument('--app',type=Path);p.add_argument('--run-id');main(p.parse_args())
