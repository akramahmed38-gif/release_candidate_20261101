"""Actual loopback HTTP checks; no native/model or independent acceptance claim."""
from pathlib import Path
import hashlib, http.cookiejar, json, secrets, subprocess, sys, threading, time, uuid
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine,DemoServer


def main():
    out=ROOT/'end_to_end'/('run_'+time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]);out.mkdir()
    pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    started=time.perf_counter();engine=create_engine(out/'private_workspace');startup=(time.perf_counter()-started)*1000
    token=secrets.token_urlsafe(40);server=DemoServer(engine,token,out/'audit.jsonl')
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    base='http://127.0.0.1:'+str(server.server_port);rows=[]
    def client():return build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()))
    a,b=client(),client()
    def call(client,path,body=None,headers=None):
        t=time.perf_counter();h={'Content-Type':'application/json',**(headers or {})}
        req=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:
            with client.open(req,timeout=30) as r:status=r.status;raw=r.read();kind=r.headers.get('Content-Type','')
        except HTTPError as r:status=r.code;raw=r.read();kind=r.headers.get('Content-Type','')
        data=json.loads(raw) if 'application/json' in kind else raw.decode()
        rows.append({'path':path,'http_status':status,'http_ms':(time.perf_counter()-t)*1000,'response':data})
        return status,data
    checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    try:
        status,page=call(a,'/');check('browser_page_has_correct_scope',status==200 and 'UNAPPROVED EVIDENCE' in page and 'three AXIS' not in page)
        check('javascript_served',call(a,'/app.js')[0]==200)
        check('unknown_route_404',call(a,'/unknown')[0]==404)
        check('unauthenticated_ask_denied',call(a,'/ask',{'question':'AXIS opening fee?','conversation_id':'forged'})[0]==401)
        check('wrong_token_denied',call(a,'/session',{'token':'wrong'})[0]==401)
        for c in [a,b]:check('developer_login',call(c,'/session',{'token':token})[0]==200)
        cid=call(a,'/conversations',{})[1]['conversation_id'];other=call(b,'/conversations',{})[1]['conversation_id']
        check('distinct_server_owned_conversations',cid!=other)
        check('cross_session_conversation_rejected',call(b,'/ask',{'question':'AXIS opening fee?','conversation_id':cid})[0]==403)
        check('cross_origin_rejected',call(a,'/conversations',{}, {'Origin':'https://untrusted.invalid'})[0]==403)
        check('invalid_question_type_rejected',call(a,'/ask',{'question':{},'conversation_id':cid})[0]==400)
        status,result=call(a,'/ask',{'question':'What is the AXIS opening fee?','conversation_id':cid})
        check('actual_source_bound_answer',status==200 and result['complete'] and result['supported_fact_ids']==['F0010'] and {c['fact_id'] for c in result['citations']}=={'F0010'})
        check('test_only_approval_boundary',result['fixture_only'] and result['approvals_pending'] and result['normal_runtime_eligible'] is False)
        status,follow=call(a,'/ask',{'question':'Please give only its minimum initial deposit amount.','conversation_id':cid})
        check('same_session_followup',status==200 and follow['complete'] and follow['supported_fact_ids']==['F0011'])
        status,isolated=call(b,'/ask',{'question':'Please give only its minimum initial deposit amount.','conversation_id':other})
        check('new_session_does_not_inherit_service',status==200 and not isolated['complete'] and not isolated['supported_fact_ids'])
        status,gap=call(a,'/ask',{'question':'What are the complete Azimut KYC documents?','conversation_id':cid})
        check('missing_evidence_not_complete',status==200 and not gap['complete'])
        check('logout_revokes_session',call(a,'/logout',{})[0]==200 and call(a,'/conversations',{})[0]==401)
        logs=(out/'audit.jsonl').read_text(encoding='utf-8')
        check('logs_exclude_questions_tokens_and_cookies',token not in logs and 'AXIS' not in logs and 'rc_session' not in logs)
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)
        after={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
        report={'candidate_source_pins':pins,'historical_candidate':'8e2faa3','release_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'startup_ms':startup,'checks':checks,'all_passed':bool(checks) and all(c['passed'] for c in checks),'source_unchanged':pins==after,'actual_http_responses':rows,'native':'NOT RUN','model_calls':0,'employee_access':False,'independent_evaluation':False}
        (out/'RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'results':str(out/'RESULTS.json'),'checks':len(checks),'passed':sum(c['passed'] for c in checks),'source_unchanged':pins==after}))


if __name__=='__main__':main()
