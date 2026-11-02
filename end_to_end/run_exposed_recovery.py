"""Developer diagnostic of released failures; never a new independent score."""
from pathlib import Path
import hashlib,http.cookiejar,json,secrets,sys,threading,time,uuid
from urllib.request import Request,build_opener,HTTPCookieProcessor,ProxyHandler
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source'))
from demo_app import create_engine,DemoServer

def main():
 out=ROOT/'end_to_end'/('exposed_recovery_'+uuid.uuid4().hex[:10]);out.mkdir()
 pins=lambda:{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
 before=pins();engine=create_engine(out/'private_workspace');token=secrets.token_urlsafe(40);server=DemoServer(engine,token,out/'audit.jsonl');threading.Thread(target=server.serve_forever,daemon=True).start();base='http://127.0.0.1:'+str(server.server_port)
 cases=json.loads((ROOT/'independent_results/e232/FAILED_CASE_DIAGNOSTICS.json').read_text(encoding='utf-8'))['cases'];rows=[]
 def post(client,path,data):
  with client.open(Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=30) as r:return json.load(r)
 try:
  with (out/'ACTUAL.jsonl').open('x',encoding='utf-8') as stream:
   for case in cases:
    c=case['original_sealed_case'];e=c['expected'];client=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()));post(client,'/session',{'token':token});cid=post(client,'/conversations',{})['conversation_id']
    for setup in c.get('setup_turns',[]):
     q=setup if isinstance(setup,str) else setup.get('question',setup.get('raw_question',setup.get('content')));assert q,setup;post(client,'/ask',{'question':q,'conversation_id':cid})
    start=time.perf_counter();a=post(client,'/ask',{'question':c['main_question'],'conversation_id':cid});elapsed=(time.perf_counter()-start)*1000
    want={(r['service_id'],r['intent_id'],r.get('channel')) for r in e['tuples']}
    got={(r['service_id'],r['intent_id'],ch) for r in a['request_contract']['requests'] for ch in (r.get('channels') or [None])}
    actual=set(a['supported_fact_ids']);required=set(e.get('required_fact_ids',[]));allowed=set(e.get('allowed_fact_ids',[]));issues=[]
    if got!=want:issues.append('tuple_mismatch')
    if not required<=actual or not actual<=allowed:issues.append('fact_bounds')
    if 'interpretation' in c['category'] and a.get('response_mode')!='interpretation_only':issues.append('response_mode')
    if e['completeness'] in ['complete_within_requested_fixture_scope','interpretation_only_complete'] and not a['complete']:issues.append('incomplete')
    if a['complete'] and a.get('clarification_needed'):issues.append('contradictory_state')
    row={'case_id':c['case_id'],'question':c['main_question'],'expected':e,'actual':a,'http_ms':elapsed,'structural_issues':issues,'structural_match':not issues}
    stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush();rows.append(row)
 finally:server.shutdown();server.server_close()
 summary={'scope':'developer exposed-failure structural diagnostic, not full independent acceptance','n':len(rows),'structural_matches':sum(r['structural_match'] for r in rows),'failures':{r['case_id']:r['structural_issues'] for r in rows if not r['structural_match']},'source_pins':before,'source_unchanged':before==pins(),'original_independent_gate_unchanged':'6/36 FAIL','native':'NOT RUN'}
 (out/'SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(out);print(json.dumps({k:v for k,v in summary.items() if k!='source_pins'}))
if __name__=='__main__':main()
