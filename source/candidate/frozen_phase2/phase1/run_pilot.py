"""Executable loopback-only fixture and bounded source-based acceptance checks."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import Request,build_opener,ProxyHandler
from contextlib import redirect_stdout,redirect_stderr
from time import perf_counter
import argparse,ctypes,hashlib,json,logging,os,shutil,sys,threading,time,uuid
from pilot_engine import ROOT,FixtureEngine,IsolationError

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.pending')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def prepare_workspace(path):
    path=Path(path);path.mkdir(parents=True,exist_ok=False)
    definition=json.loads((ROOT/'fixture_data/fixture_definition.json').read_text(encoding='utf-8'))
    src=ROOT/'fixture_data/source_files'/definition['source_document'];target=path/'source_files'/definition['source_document'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
    atomic(path/'ISOLATED_TEST_ONLY.json',{'fixture_only':True,'production_use_allowed':False,'approvals_pending':True})
    atomic(path/'test_eligibility.json',{'fixture_only':True,'production_use_allowed':False,'source_sha256':definition['source_sha256'],'authorized_test_fact_ids':['F0010','F0011','F0012']})
    return path

def memory():
    if sys.platform!='win32':return {'working_set_bytes':None,'peak_working_set_bytes':None}
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ['peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile']]
    data=Counters();data.cb=ctypes.sizeof(data)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    if ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(data),data.cb):return {'working_set_bytes':data.working,'peak_working_set_bytes':data.peak}
    return {'working_set_bytes':None,'peak_working_set_bytes':None}

def guard(app):
    if app is None:return None
    app=Path(app);paths=list((app/'chatbot').glob('*.py'))+[app/'chatbot_runtime.json',app/'src/routes/chatbot.py',app/'data/chatbot_content/active.json']
    definition=json.loads((ROOT/'fixture_data/fixture_definition.json').read_text(encoding='utf-8'));paths.append(app/definition['source_document'])
    hashes={str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    backup=app/'maintenance/backups/admin_pilot_20261025_141726'
    if not backup.is_dir():raise ValueError('Protected historical backup unavailable')
    hashes['protected_backup_metadata']=hashlib.sha256(json.dumps([(f.relative_to(backup).as_posix(),f.stat().st_size,f.stat().st_mtime_ns) for f in sorted(backup.rglob('*')) if f.is_file()]).encode()).hexdigest()
    return hashes

def make_server(engine):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/health':return self.reply({'fixture_only':True,'approvals_pending':True,'backend':engine.backend.mode})
            html='''<!doctype html><meta charset="utf-8"><title>Unapproved AXIS fixture</title><h1>UNAPPROVED TEST FIXTURE</h1><p>Only three AXIS financial facts. Human/business approvals pending. Local test use only.</p><textarea id="q" rows="4" cols="70"></textarea><button id="b">Ask test fixture</button><pre id="o"></pre><script>b.onclick=async()=>{let r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q.value,conversation_id:'local-demo',session_id:'local-demo'})});o.textContent=JSON.stringify(await r.json(),null,2)}</script>'''
            data=html.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def reply(self,value,status=200):
            data=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_POST(self):
            if self.path!='/ask':return self.reply({'error_type':'NotFound','fixture_only':True},404)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<12000:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(length))
                if set(data)-{'question','conversation_id','session_id'}:raise ValueError('Unsupported fields')
                if not isinstance(data.get('question'),str) or not 0<len(data['question'])<=1500:raise ValueError('Invalid question')
                value=engine.ask(data['question'],data.get('conversation_id','fixture'),data.get('session_id','synthetic'))
                return self.reply(value)
            except Exception as exc:return self.reply({'error_type':type(exc).__name__,'fixture_only':True,'complete':False},503)
    return ThreadingHTTPServer(('127.0.0.1',0),Handler)

def assess(case,response):
    issues=[]
    for key in ['type','complete']:
        if response.get(key)!=case[key]:issues.append('wrong_'+key)
    if set(response.get('supported_fact_ids',[]))!=set(case['facts']):issues.append('wrong_or_missing_facts')
    if response.get('reply_language')!=case['language']:issues.append('wrong_language')
    if not response.get('fixture_only') or not response.get('approvals_pending') or response.get('normal_runtime_eligible') is not False:issues.append('test_scope_bypass')
    if response.get('generation_calls')!=0 or response.get('translation_calls')!=0:issues.append('forbidden_generation')
    if case.get('context_used') is not None and response.get('interpretation',{}).get('context_used')!=case['context_used']:issues.append('context_mismatch')
    if set(c['fact_id'] for c in response.get('citations',[]))!=set(case['facts']):issues.append('citation_coverage')
    for c in response.get('citations',[]):
        if c['source_sha256']!='198dffbc8ab1ce2887356e91fab9d241ea3f08c35216d2b32a1062e64439abce' or c['page']!=1 or c['source_document']!='daily_brief/axis_wallet_sales_guide.pdf':issues.append('wrong_source')
    return issues

def main(args):
    os.environ['ANONYMIZED_TELEMETRY']='False';os.environ['OTEL_SDK_DISABLED']='true';logging.disable(logging.CRITICAL)
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    run_name=args.run_id or time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    if not __import__('re').fullmatch(r'[0-9]{8}_[0-9]{6}_[a-f0-9]{8}',run_name):raise ValueError('Invalid isolated run identifier')
    output=(Path(args.output) if args.output else ROOT/'runs')/run_name;output.mkdir(parents=True)
    work=prepare_workspace(output/'private_fixture');before=guard(args.app);started=perf_counter()
    try:
        if args.backend=='native':
            from native_backend import NativeBackend
            factory=lambda facts:NativeBackend(facts,work)
        else:
            from pilot_engine import LexicalBackend
            factory=LexicalBackend
        with open(os.devnull,'w') as sink,redirect_stderr(sink):engine=FixtureEngine(work,factory,test_mode=True)
        startup_ms=(perf_counter()-started)*1000
        atomic(output/'INITIALIZATION.json',{'fixture_only':True,'startup_ms':startup_ms,'backend':engine.backend.mode,'details':getattr(engine.backend,'initialization',{}),'working_memory':memory()})
        server=make_server(engine);threading.Thread(target=server.serve_forever,daemon=True).start()
        url='http://127.0.0.1:'+str(server.server_port)
        if args.serve:
            print(json.dumps({'url':url,'fixture_only':True,'approvals_pending':True,'backend':engine.backend.mode,'stop':'Ctrl+C'}),flush=True)
            try:
                while True:time.sleep(1)
            except KeyboardInterrupt:pass
            finally:server.shutdown();server.server_close()
            return
        opener=build_opener(ProxyHandler({}));results=[]
        def request(question,cid,sid):
            start=perf_counter();cpu=time.process_time()
            data=json.dumps({'question':question,'conversation_id':cid,'session_id':sid},ensure_ascii=False).encode()
            with opener.open(Request(url+'/ask',data=data,headers={'Content-Type':'application/json'}),timeout=45) as reply:value=json.load(reply)
            return value,{'http_ms':(perf_counter()-start)*1000,'process_cpu_ms':(time.process_time()-cpu)*1000,**memory()}
        cases=json.loads((ROOT/'test_cases.json').read_text(encoding='utf-8'))['cases']
        try:
            for case in cases:
                identity=case['id'];setup=None
                if case.get('setup'):setup=request(case['setup'],identity,identity)[0]
                value,timing=request(case['question'],identity,identity)
                issues=assess(case,value)
                results.append({'id':identity,'question':case['question'],'expected':case,'response':value,'measurements':timing,'issues':issues,'passed':not issues,'setup_response':setup})
                atomic(output/'RESULTS.json',results);atomic(output/'PROGRESS.json',{'status':'running','completed':len(results),'target':len(cases),'fixture_only':True,'failures':sum(not r['passed'] for r in results)})
            # Real source-copy and test-eligibility invalidation, never originals.
            source=work/'source_files'/engine.definition['source_document'];original=source.read_bytes()
            source.write_bytes(original+b'\nINVALID TEST COPY')
            value,timing=request('Explain AXIS opening fee, minimum deposit and balance treatment.','mut-source','mut-source');source.write_bytes(original)
            results.append({'id':'SOURCE_VERSION_INVALID','response':value,'measurements':timing,'passed':value.get('type')=='unavailable' and not value.get('citations')})
            auth=work/'test_eligibility.json';original_auth=auth.read_bytes();state=json.loads(original_auth);state['authorized_test_fact_ids'].remove('F0012');atomic(auth,state)
            value,timing=request('Explain AXIS opening fee, minimum deposit and balance treatment.','mut-revoke','mut-revoke');auth.write_bytes(original_auth)
            results.append({'id':'TEST_ELIGIBILITY_REVOKED','response':value,'measurements':timing,'passed':value.get('type')=='answer' and not value.get('complete') and 'F0012' not in value.get('supported_fact_ids',[]) and set(value.get('supported_fact_ids',[]))=={'F0010','F0011'}})
            state=json.loads(original_auth);state['production_use_allowed']=True;atomic(auth,state)
            value,timing=request('Is opening AXIS free?','mut-normal','mut-normal');auth.write_bytes(original_auth)
            results.append({'id':'PRODUCTION_FLAG_REJECTED','response':value,'measurements':timing,'passed':value.get('type')=='unavailable' and not value.get('citations')})
            try:FixtureEngine(work,test_mode=False);normal_rejected=False
            except IsolationError:normal_rejected=True
            results.append({'id':'NORMAL_RUNTIME_ENTRY_REJECTED','passed':normal_rejected})
        finally:server.shutdown();server.server_close()
        after=guard(args.app);numeric=ROOT/'candidate/chatbot/reference_validation.py'
        numeric_ok=hashlib.sha256(numeric.read_bytes()).hexdigest()=='9eb736461247aaa7f89347bb8284113c9bd51b5d3e6f954b31b4e4d665ac2848'
        from chatbot.reference_validation import scoped_numeric_checks
        probes=[not scoped_numeric_checks('Service code 73157.','Service code 73158.','transaction_codes')[0],not scoped_numeric_checks('Fawry Plus: 1%. ATM: 0.75%.','Fawry Plus: 0.75%. ATM: 1%.','withdrawal')[0],not scoped_numeric_checks('إيداع 20 جنيه، يستقر في رصيد العميل.','An activation fee of 20 EGP.','activation')[0]]
        passed=all(r['passed'] for r in results) and numeric_ok and all(probes) and before==after
        complete=[r['measurements']['http_ms'] for r in results if r.get('passed') and r.get('response',{}).get('complete')]
        def percentile(values,p):
            if not values:return None
            v=sorted(values);i=(len(v)-1)*p;lo=int(i);return v[lo]+(v[min(lo+1,len(v)-1)]-v[lo])*(i-lo)
        summary={'status':'completed','technical_checks_passed':passed,'technical_decision':'GO_FOR_REVIEW_OF_BROADER_PILOT_ONLY' if passed and args.backend=='native' else 'CORE_ONLY_NATIVE_VERIFICATION_PENDING' if passed else 'NO_GO',
            'backend':engine.backend.mode,'main_cases':len(cases),'invalidation_and_isolation_checks':4,'failed_ids':[r['id'] for r in results if not r['passed']],
            'numeric_validator_byte_identical':numeric_ok,'numeric_rejection_regressions_passed':all(probes),'production_backup_and_source_guard_unchanged':before==after if before is not None else None,
            'source_copy_restored':source.read_bytes()==original,'normal_approvals_still_pending':True,'generation_calls':0,'translation_calls':0,'document_embedding_calls':0,
            'startup_ms':startup_ms,'complete_correct_response_samples':len(complete),'complete_correct_http_p50_ms':percentile(complete,.5),'complete_correct_http_p95_ms':percentile(complete,.95),
            'latency_scope':'descriptive tiny-fixture loopback HTTP; not production SLA, formal 200-sample inference latency or concurrency proof','process_memory':memory(),
            'resource_scope':'This Python/Chroma process measured. Shared Ollama embedding process CPU/RAM not attributable here. No Qwen inference.',
            'full_benchmark_run':False,'normal_runtime_eligible_facts':0,'source_approvals_granted':0}
        atomic(output/'RESULTS.json',results);atomic(output/'SUMMARY.json',summary);atomic(output/'PROGRESS.json',summary)
        print(json.dumps({'run':run_name,'output':str(output),'summary':summary}),flush=True)
    except Exception as exc:
        import traceback
        frames=traceback.extract_tb(exc.__traceback__)
        atomic(output/'PROGRESS.json',{'status':'blocked','error_type':type(exc).__name__,'safe_stack':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in frames],'fixture_only':True,'generation_calls':0})
        print(json.dumps({'run':run_name,'status':'blocked','error_type':type(exc).__name__}),flush=True)
        raise SystemExit(2)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backend',choices=['core','native'],default='core');parser.add_argument('--serve',action='store_true');parser.add_argument('--output',type=Path);parser.add_argument('--app',type=Path);parser.add_argument('--run-id')
    main(parser.parse_args())
