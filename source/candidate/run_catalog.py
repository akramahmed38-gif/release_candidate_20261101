from pathlib import Path
from time import perf_counter
from urllib.request import Request,build_opener,ProxyHandler
import json,hashlib,shutil,sys,os,time,uuid,threading,argparse,traceback
from candidate import ROOT,CatalogEngine,frozen
from run_phase2 import grade,preservation as phase2_preservation
from run_pilot import make_server,memory
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(12):
        try:temp.replace(path);return
        except PermissionError:
            if attempt==11:raise
            time.sleep(min(.05*2**attempt,1))
def preservation(app):
    state=phase2_preservation(app)
    if app:
        definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
        for relative,expected in definition['sources'].items():
            digest=hashlib.sha256((app/relative).read_bytes()).hexdigest()
            if digest!=expected:raise ValueError('Original source version changed')
            state['phase3_source:'+relative]=digest
    return state
def prepare(work):
    work.mkdir(parents=True)
    shutil.copytree(ROOT/'fixture_data/source_files',work/'source_files')
    definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
    save(work/'ISOLATED_TEST_ONLY.json',{'fixture_only':True,'production_use_allowed':False,'approvals_pending':True})
    save(work/'test_eligibility.json',{'fixture_only':True,'production_use_allowed':False,'authorized_test_fact_ids':[f['fact_id'] for f in definition['facts']],'rendering_fingerprints':{f['fact_id']:f['english_sha256'] for f in definition['facts']}})
    save(work/'generation.json',{'generation':definition['source_content_generation'],'fixture_definition_sha256':hashlib.sha256((ROOT/'fixture_data/definition.json').read_bytes()).hexdigest()})
def check_frozen():
    reference=json.loads((ROOT/'FROZEN_BASELINE_REFERENCE.json').read_text())
    for relative,digest in reference['candidate_and_results_sha256'].items():
        if hashlib.sha256((ROOT/'frozen_phase2'/relative).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen baseline changed')
    if hashlib.sha256((ROOT/'ACCEPTANCE_36.json').read_bytes()).hexdigest()!=(ROOT/'ACCEPTANCE_36.sha256').read_text():raise ValueError('Acceptance changed')
def main(args):
    os.environ['ANONYMIZED_TELEMETRY']='False';os.environ['OTEL_SDK_DISABLED']='true'
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    name=args.resume or args.run_id or time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    out=(args.output or ROOT/'runs')/name
    if not args.resume:out.mkdir(parents=True,exist_ok=False)
    elif not (out/'RESULTS.json').exists():raise ValueError('Missing resume ledger')
    lease=(out/'RUN.lock').open('a+b')
    if lease.tell()==0:lease.write(b'\0');lease.flush()
    lease.seek(0)
    if os.name=='nt':
        import msvcrt
        msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
    prior=json.loads((out/'RESULTS.json').read_text(encoding='utf-8')) if args.resume else []
    if len(prior)%2:raise ValueError('Incomplete pair requires explicit investigation')
    if any(not r['passed'] for r in prior):raise ValueError('Do not resume through failed answers')
    resumed_suffix='_resume_'+uuid.uuid4().hex[:8] if args.resume else ''
    save(out/'PROGRESS.json',{'status':'initializing','evaluation':'developer-authored'})
    engines={};servers={}
    try:
        check_frozen();before=preservation(args.app)
        save(out/('PRESERVATION_BEFORE'+resumed_suffix+'.json'),before)
        for arm in ['control','reuse']:
            # Deep original source names exceed legacy Windows MAX_PATH
            # beneath the report directory. Private data stays in a short,
            # separate local workspace; reports and case pins stay unchanged.
            work=(Path(os.environ['LOCALAPPDATA'])/'HRTrainingCatalog'/(name+resumed_suffix)/arm) if args.backend=='native' else out/(arm+resumed_suffix)
            prepare(work)
            if args.backend=='native':
                from reuse_backend import NativeBackend
                factory=lambda facts,w=work,a=arm:NativeBackend(facts,w,reuse=a=='reuse')
            else:factory=frozen.CoreBackend
            start=perf_counter();engine=CatalogEngine(work,factory,test_mode=True);engines[arm]=engine
            if args.final and arm=='reuse':
                proof=json.loads((ROOT/'DIAGNOSIS_VERIFIED.json').read_text())
                if not proof.get('short_window_guard_trigger_confirmed'):raise ValueError('Guard cause not verified; no final experiment')
                engine.backend.budget.stable_window=True
            server=make_server(engine);threading.Thread(target=server.serve_forever,daemon=True).start();servers[arm]=server
            save(out/(arm+'_INITIALIZATION'+resumed_suffix+'.json'),{'backend':engine.backend.mode,'startup_ms':(perf_counter()-start)*1000,'details':getattr(engine.backend,'initialization',{}),'memory':memory()})
        if args.backend=='native' and not args.resume:
            t=perf_counter();engines['control'].backend.embed.embed_texts(['AXIS Pay'])
            save(out/'WARMUP.json',{'query_embeddings':1,'elapsed_ms':(perf_counter()-t)*1000,'excluded_from_answers_and_latency':True})
        opener=build_opener(ProxyHandler({}))
        def request(arm,q,cid):
            start=perf_counter();cpu=time.process_time()
            data=json.dumps({'question':q,'conversation_id':cid,'session_id':cid},ensure_ascii=False).encode()
            try:
                with opener.open(Request('http://127.0.0.1:'+str(servers[arm].server_port)+'/ask',data=data,headers={'Content-Type':'application/json'}),timeout=45) as response:value=json.load(response)
            except Exception as exc:value={'execution_error_type':type(exc).__name__}
            return value,{'http_ms':(perf_counter()-start)*1000,'process_cpu_ms':(time.process_time()-cpu)*1000,**memory()}
        p1=json.loads((ROOT/'frozen_phase2/phase1/test_cases.json').read_text(encoding='utf-8'))['cases']
        p2=json.loads((ROOT/'frozen_phase2/test_cases.json').read_text(encoding='utf-8'))['cases']
        cases=[{**r,'id':'P1_'+r['id']} for r in p1]+p2+json.loads((ROOT/'ACCEPTANCE_36.json').read_text(encoding='utf-8'))['cases']
        if args.frozen_only:cases=cases[:50]
        if args.diagnostic:cases=json.loads((ROOT/'DIAGNOSTIC_CASES.json').read_text(encoding='utf-8'))
        results=prior
        for i,c in enumerate(cases):
            if i<len(prior)//2:
                pair=prior[i*2:i*2+2]
                if {r['arm'] for r in pair}!={'control','reuse'} or any(r['id']!=c['id'] or r['expected']!=c for r in pair):raise ValueError('Resume case identity mismatch')
                for arm in ['control','reuse']:
                    cid=c.get('conversation',c['id'])
                    if c.get('setup'):engines[arm].catalog.plan(c['setup'],cid,cid)
                    engines[arm].catalog.plan(c['question'],cid,cid)
                continue
            for arm in (['control','reuse'] if i%2==0 else ['reuse','control']):
                cid=c.get('conversation',c['id'])
                setup=None
                if c.get('setup'):setup=request(arm,c['setup'],cid)[0]
                value,timing=request(arm,c['question'],cid);issues=grade(c,value,engines[arm].facts)
                results.append({'id':c['id'],'arm':arm,'expected':c,'actual':value,'measurements':timing,'issues':issues,'passed':not issues,'setup':setup})
            save(out/'RESULTS.json',results);save(out/'PROGRESS.json',{'status':'running','main_pairs_completed':i+1,'main_pairs_total':len(cases),'failed':sum(not r['passed'] for r in results)})
        integrity=[]
        for arm,engine in ([] if args.diagnostic else engines.items()):
            work=engine.workspace;auth=work/'test_eligibility.json';raw=auth.read_bytes()
            def probe(identity,q,expected):
                value,timing=request(arm,q,identity);case={'facts':expected,'complete':False,'language':'en'}
                issues=grade(case,value,engine.facts)
                integrity.append({'id':identity,'arm':arm,'expected':case,'actual':value,'measurements':timing,'passed':not issues,'issues':issues})
            source=work/'source_files/KnowledgeBase/Articles/Wallets_ART.md';raw_source=source.read_bytes();source.write_bytes(raw_source+b'\nTEST CHANGE')
            probe('SOURCE_QNB_CHANGED','Compare AXIS and QNB initial activation deposits.',['F0011','F0012']);source.write_bytes(raw_source)
            source=work/'source_files/KnowledgeBase/Articles/AZIMUT_ART.md';raw_source=source.read_bytes();source.unlink()
            probe('SOURCE_AZIMUT_DELETED','AXIS opening fee; Azimut registration steps.',['F0010']);source.write_bytes(raw_source)
            state=json.loads(raw);state['authorized_test_fact_ids'].remove('F0040');save(auth,state)
            probe('MIDDLE_STEP_REVOKED','AXIS opening fee; Azimut registration steps.',['F0010']);auth.write_bytes(raw)
            state=json.loads(raw);state['rendering_fingerprints']['F0073']='revoked';save(auth,state)
            probe('LANGUAGE_VIEW_REVOKED','Compare AXIS and QNB initial activation deposits.',['F0011','F0012']);auth.write_bytes(raw)
            state=json.loads(raw);state['production_use_allowed']=True;save(auth,state)
            probe('PRODUCTION_FLAG_REJECTED','Compare AXIS and QNB initial activation deposits.',[]);auth.write_bytes(raw)
            try:CatalogEngine(work,test_mode=False);okay=False
            except frozen.IsolationError:okay=True
            integrity.append({'id':'NORMAL_MODE_REJECTED','arm':arm,'passed':okay})
            # Focused race probes: no business claims may survive a changed
            # eligibility or generation boundary immediately before emission.
            engine.before_emit_hook=lambda p=auth,b=raw:p.write_bytes(b+b' ')
            value,timing=request(arm,'What initial funding activates QNB?','MID_AUTH')
            integrity.append({'id':'MID_REQUEST_AUTH_CHANGE','arm':arm,'actual':value,'passed':value.get('invalidation_reason')=='eligibility_or_generation_changed_before_emission' and not value.get('citations')})
            engine.before_emit_hook=None;auth.write_bytes(raw)
            generation=work/'generation.json';graw=generation.read_bytes()
            engine.before_emit_hook=lambda p=generation,b=graw:p.write_bytes(b+b' ')
            value,timing=request(arm,'What initial funding activates QNB?','MID_GENERATION')
            integrity.append({'id':'MID_REQUEST_GENERATION_CHANGE','arm':arm,'actual':value,'passed':value.get('invalidation_reason')=='eligibility_or_generation_changed_before_emission' and not value.get('citations')})
            engine.before_emit_hook=None;generation.write_bytes(graw)
        save(out/'INTEGRITY.json',integrity)
        check_frozen();after=preservation(args.app)
        save(out/('PRESERVATION_AFTER'+resumed_suffix+'.json'),after)
        validators={}
        for validator_name in ['reference_validation.py','workflow_contract.py']:
            path=ROOT/'frozen_phase2/phase1/candidate/chatbot'/validator_name
            validators[validator_name]=hashlib.sha256(path.read_bytes()).hexdigest()
        passed=all(r['passed'] for r in results+integrity) and before==after
        summary={'status':'completed','run_id':name,'backend':args.backend,'main_requests':len(results),'question_pairs':len(cases),'integrity_checks':len(integrity),'failed_main':[(r['arm'],r['id'],r['issues']) for r in results if not r['passed']],'failed_integrity':[(r['arm'],r['id']) for r in integrity if not r['passed']],'correctness_checks_passed':passed,'preservation_passed':before==after,'frozen_hashes_before_after_verified':True,'validators':validators,'evaluation':'developer-authored, not independent/blind','approvals_pending':True,'generation_calls':0,'document_embedding_calls':0,'memory':memory(),'performance_gate':'pending paired review','decision':'PENDING_REVIEW' if passed else 'NO_GO'}
        save(out/'SUMMARY.json',summary);save(out/'PROGRESS.json',summary);print(json.dumps(summary),flush=True)
    except Exception as exc:
        save(out/'PROGRESS.json',{'status':'blocked','error_type':type(exc).__name__,'stack':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]});print(json.dumps({'status':'blocked','error_type':type(exc).__name__}),flush=True);raise SystemExit(2)
    finally:
        for server in servers.values():server.shutdown();server.server_close()
        lease.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['core','native'],default='core');p.add_argument('--output',type=Path);p.add_argument('--run-id');p.add_argument('--resume');p.add_argument('--app',type=Path);p.add_argument('--frozen-only',action='store_true');p.add_argument('--diagnostic',action='store_true');p.add_argument('--final',action='store_true');main(p.parse_args())
