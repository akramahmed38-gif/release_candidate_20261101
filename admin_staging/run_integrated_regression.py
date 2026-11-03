"""Frozen 176-case IPC regression against the already running staging worker.

No user login/token export. Does not claim UI or native-stack acceptance.
"""
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
import hashlib,importlib.util,json,math,statistics,subprocess,sys,time,uuid
ROOT=Path(__file__).resolve().parent;RELEASE=ROOT.parent

def pins():
    paths=list((RELEASE/'source').rglob('*'))+[ROOT/n for n in ['engine_worker.py','engine_controller.py','admin_knowledge.py','catalog_store.py','run_admin.py','isolation.py','knowledge_workspace.html','knowledge_workspace.js']]
    return {p.relative_to(RELEASE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and '__pycache__' not in p.parts}

def percentile(values,p):
    values=sorted(values)
    if not values:return None
    index=(len(values)-1)*p;lo=math.floor(index);hi=math.ceil(index)
    return values[lo]+(values[hi]-values[lo])*(index-lo)

def main():
    # The preserved grader imports run_phase2 from the frozen runtime tree.
    # Import the same module-path bootstrap as the existing regression runner;
    # no engine, stores or models are created in this collector process.
    sys.path.insert(0,str(RELEASE/'source/candidate'))
    from candidate import CatalogEngine
    from observed_guard import windows_sample
    before=pins();out=ROOT/'state'/('regression_'+uuid.uuid4().hex[:10]);out.mkdir()
    definition=json.loads((RELEASE/'source/candidate/fixture_data/definition.json').read_text(encoding='utf-8'))
    facts={f['fact_id']:f for f in definition['facts']};ids=list(facts)
    cases=json.loads((RELEASE/'end_to_end/datasets/original176.json').read_text(encoding='utf-8-sig'));assert len(cases)==176
    spec=importlib.util.spec_from_file_location('preserved_grader',RELEASE/'end_to_end/datasets/preserved_evaluation.py');grader=importlib.util.module_from_spec(spec);spec.loader.exec_module(grader)
    endpoint=json.loads((ROOT/'.private/engine_endpoint.json').read_text());key=(ROOT/'.private/engine.key').read_text()
    actor='frozen-regression-'+uuid.uuid4().hex;opener=build_opener(ProxyHandler({}));rows=[]
    def ask(q,cid):
        payload={'question':q,'conversation_id':cid,'actor_scope':actor,'knowledge_mode':'review_preview','selected_fact_ids':ids}
        request=Request('http://127.0.0.1:'+str(endpoint['port'])+'/ask',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        started=time.perf_counter();sample_before=windows_sample()
        from urllib.error import HTTPError,URLError
        try:
            with opener.open(request,timeout=60) as response:value=json.load(response)
        except HTTPError as exc:
            value={'execution_error':{'http_status':exc.code,'worker_error':json.load(exc)},'complete':False,'supported_fact_ids':[]}
        except (URLError,TimeoutError) as exc:
            value={'execution_error':{'type':type(exc).__name__},'complete':False,'supported_fact_ids':[]}
        value['collector_system_before']=sample_before
        value['collector_system_after']=windows_sample()
        return value,(time.perf_counter()-started)*1000
    execution_error=None
    try:
        with (out/'RESPONSES.jsonl').open('x',encoding='utf-8') as f:
            for record in cases:
                case=record['frozen_expected'];cid=str(case.get('conversation',case['id']));setups=[]
                if case.get('setup'):setups.append(ask(case['setup'],cid)[0])
                for setup in case.get('setup_turns',[]):
                    text=setup.get('raw_question') if isinstance(setup,dict) else setup
                    same=setup.get('same_session',True) if isinstance(setup,dict) else True
                    setups.append(ask(text,cid if same else cid+':other')[0])
                actual,elapsed=ask(record['question'],cid)
                expected={**case,'language':case.get('reply_language',case.get('language'))}
                setup_failed=any(x.get('execution_error') for x in setups)
                issues=['execution_failure'] if actual.get('execution_error') else ['setup_execution_failure'] if setup_failed else grader.grade_business(expected,actual,facts)
                row={'id':record['id'],'question':record['question'],'expected':case,'actual':actual,'http_ms':elapsed,'business_issues':issues,'passed':not issues,'setups':setups}
                rows.append(row);f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
                (out/'PROGRESS.json').write_text(json.dumps({'completed':len(rows),'total':176,'failed_ids':[r['id'] for r in rows if not r['passed']]}),encoding='utf-8')
    except Exception as exc:
        execution_error={'type':type(exc).__name__,'completed_before_error':len(rows)}
        if isinstance(exc,ModuleNotFoundError):execution_error['missing_module']=exc.name
        from urllib.error import HTTPError
        if isinstance(exc,HTTPError):
            execution_error['http_status']=exc.code
            try:execution_error['worker_error']=json.load(exc)
            except Exception:pass
    finally:
        complete=[r for r in rows if r['passed'] and r['expected'].get('complete')]
        timing={}
        for language in ['ar','en']:
            population=[r for r in complete if r['actual'].get('reply_language')==language]
            values=[r['http_ms'] for r in population]
            timing[language]={'n':len(values),'p50_ms':percentile(values,.5),'p95_ms':percentile(values,.95),'guard_wait_total_ms':sum(r['actual'].get('worker_resource_wait_ms',0) for r in population)}
        summary={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=RELEASE,text=True).strip(),'completed':len(rows),'total':176,'passed':sum(r['passed'] for r in rows),'failed_ids':[r['id'] for r in rows if not r['passed']],'execution_error':execution_error,'supported_complete_correct':len(complete),'supported_denominator':117,'source_unchanged':pins()==before,'gold_changed':False,'facts_approved':0,'independent':False,'backend':'existing Core/BM25 staging IPC worker','native':'NOT RUN','complete_correct_http':timing,'source_pins':before}
        summary['request_execution_failure_ids']=[r['id'] for r in rows if r['actual'].get('execution_error')]
        (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k!='source_pins'}));print('RESULTS '+str(out))

if __name__=='__main__':main()
