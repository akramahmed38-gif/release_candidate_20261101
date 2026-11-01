"""Prepared native diagnostic only; not independent acceptance or an SLA test."""
from pathlib import Path
import argparse,hashlib,http.cookiejar,json,os,platform,secrets,sys,threading,time
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-host',required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--diagnostic-only',action='store_true');args=p.parse_args()
    if not args.diagnostic_only:raise SystemExit('Explicit diagnostic scope required; employee/native acceptance is not authorized by this script')
    if os.name!='nt' or platform.node().casefold()!=args.expected_host.casefold() or platform.node().casefold()=='fwplus-390':raise SystemExit('BLOCKED: authorized Windows Server host required; UNC access is not execution')
    allowed=Path(os.environ['LOCALAPPDATA'])/'HRRC'
    args.workspace.resolve().relative_to(allowed.resolve())
    if args.workspace.exists():raise SystemExit('Fresh private workspace required')
    manifest=json.loads((ROOT/'native_packages/SOURCE_PINS.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise SystemExit('Package source mismatch: '+name)
    os.environ['ANONYMIZED_TELEMETRY']='False';os.environ['OTEL_SDK_DISABLED']='true'
    from demo_app import DemoServer
    from candidate import CatalogEngine
    from run_catalog import prepare
    from reuse_backend import NativeBackend
    def factory(facts):
        backend=NativeBackend(facts,args.workspace,reuse=True);backend.budget.stable_window=True
        if backend.config.generation_threads!=2:raise RuntimeError('Thread configuration mismatch')
        old=backend.embed._request
        def restricted(path,*a,**kw):
            if path not in {'/api/embed','/api/tags'}:raise RuntimeError('Only existing BGE embeddings/tags permitted')
            if path=='/api/embed':
                payload=dict(kw.get('payload',{}));options=dict(payload.get('options',{}))
                if payload.get('model')!=backend.config.embedding_model:raise RuntimeError('Model mismatch')
                options.update(num_gpu=0,num_thread=2);payload['options']=options;kw['payload']=payload
            return old(path,*a,**kw)
        backend.embed._request=restricted
        return backend
    started=time.perf_counter();prepare(args.workspace);engine=CatalogEngine(args.workspace,factory,test_mode=True);startup_ms=(time.perf_counter()-started)*1000
    token=secrets.token_urlsafe(40);server=DemoServer(engine,token,args.workspace/'audit.jsonl');threading.Thread(target=server.serve_forever,daemon=True).start()
    client=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()));base='http://127.0.0.1:'+str(server.server_port)
    def post(path,data):
        t=time.perf_counter()
        with client.open(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=60) as response:r=json.load(response)
        return r,(time.perf_counter()-t)*1000
    cases=[('What is the AXIS opening fee?',['F0010']),('ما رسوم إيداع AXIS من فوري بلس؟',['F0001']),('QNB Wallet ATM withdrawal fee?',['F0076']),('Explain Azimut registration steps in MyFawry.',['F0037','F0038','F0039','F0040','F0041','F0042']),('3ayez a3raf code ADIB remittance',['F0036']),('What is the wallet opening fee?',[])]
    rows=[]
    try:
        post('/session',{'token':token})
        for round_name in ['first_pass','warm_repeat']:
            for question,facts in cases:
                cid=post('/conversations',{})[0]['conversation_id'];answer,ms=post('/ask',{'question':question,'conversation_id':cid})
                rows.append({'condition':round_name,'question':question,'expected_fact_ids':facts,'actual':answer,'http_ms':ms,'fact_set_matches':set(answer.get('supported_fact_ids',[]))==set(facts),'complete_matches':answer.get('complete')==bool(facts)})
    finally:
        server.shutdown();server.server_close()
        report={'host':platform.node(),'source_commit':manifest['release_commit'],'package_pins':manifest['files'],'startup_ms':startup_ms,'rows':rows,'native_requests':len(rows),'model_generation_calls':0,'qwen_path':'NOT RUN; source-view assembly does not require generation; legacy Qwen service remains unvalidated','employee_access':False,'approvals_granted':0,'independent':False,'performance_certification':'NOT RUN; twelve diagnostic observations are insufficient','shared_ollama_resource_attribution':'UNAVAILABLE'}
        (args.workspace/'NATIVE_SMOKE_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'results':str(args.workspace/'NATIVE_SMOKE_RESULTS.json'),'requests':len(rows),'employee_access':False}))

if __name__=='__main__':main()
