"""Frozen 176-case business regression through the authenticated demo HTTP API."""
from pathlib import Path
import hashlib,http.cookiejar,importlib.util,json,secrets,subprocess,sys,threading,time,uuid
from urllib.request import Request,build_opener,HTTPCookieProcessor,ProxyHandler
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine,DemoServer

def main():
    out=ROOT/'end_to_end'/('historical_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);out.mkdir()
    pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    cases=json.loads((ROOT/'end_to_end/datasets/original176.json').read_text(encoding='utf-8-sig'));assert len(cases)==176
    spec=importlib.util.spec_from_file_location('preserved_grader',ROOT/'end_to_end/datasets/preserved_evaluation.py');grading=importlib.util.module_from_spec(spec);spec.loader.exec_module(grading)
    t=time.perf_counter();engine=create_engine(out/'private_workspace');startup=(time.perf_counter()-t)*1000
    token=secrets.token_urlsafe(40);server=DemoServer(engine,token,out/'audit.jsonl');threading.Thread(target=server.serve_forever,daemon=True).start()
    base='http://127.0.0.1:'+str(server.server_port);clients={};rows=[]
    def post(client,path,data):
        t=time.perf_counter()
        with client.open(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=30) as response:value=json.load(response)
        return value,(time.perf_counter()-t)*1000
    def ask(q,key):
        if key not in clients:
            client=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()));post(client,'/session',{'token':token});cid=post(client,'/conversations',{})[0]['conversation_id'];clients[key]=(client,cid)
        client,cid=clients[key];return post(client,'/ask',{'question':q,'conversation_id':cid})
    try:
        with (out/'RESPONSES.jsonl').open('x',encoding='utf-8') as f:
            for record in cases:
                case=record['frozen_expected'];key=str(case.get('conversation',case['id']));setups=[]
                if case.get('setup'):setups.append(ask(case['setup'],key)[0])
                for setup in case.get('setup_turns',[]):
                    text=setup.get('raw_question') if isinstance(setup,dict) else setup
                    same=setup.get('same_session',True) if isinstance(setup,dict) else True
                    setups.append(ask(text,key if same else key+':other')[0])
                actual,http_ms=ask(record['question'],key)
                expected={**case,'language':case.get('reply_language',case.get('language'))}
                issues=grading.grade_business(expected,actual,engine.facts)
                row={'id':record['id'],'question':record['question'],'expected':case,'actual':actual,'http_ms':http_ms,'business_issues':issues,'passed':not issues,'setups':setups}
                f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();rows.append(row)
                (out/'PROGRESS.json').write_text(json.dumps({'completed':len(rows),'total':176}),encoding='utf-8')
    finally:
        server.shutdown();server.server_close()
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        summary={'release_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_pins':pins,'source_unchanged':pins==after,'completed':len(rows),'total':176,'passed':sum(r['passed'] for r in rows),'failed_ids':[r['id'] for r in rows if not r['passed']],'supported_complete_correct':sum(r['passed'] and bool(r['expected'].get('complete')) for r in rows),'supported_denominator':117,'startup_ms':startup,'environment':'workstation authenticated loopback Core HTTP','native':'NOT RUN','model_calls':0,'gold_changed':False,'independent':False}
        (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in summary.items() if k!='source_pins'}))

if __name__=='__main__':main()
