"""Executed IPC integration checks; not native or independent acceptance."""
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
import hashlib,json,sys,time,uuid
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from engine_controller import start,stop

def main():
    child,log=start();results=[]
    out=ROOT/'state/integration_results'/uuid.uuid4().hex;out.mkdir(parents=True)
    endpoint=json.loads((ROOT/'.private/engine_endpoint.json').read_text());key=(ROOT/'.private/engine.key').read_text()
    ids=[f['fact_id'] for f in json.loads((ROOT.parent/'source/candidate/fixture_data/definition.json').read_text(encoding='utf-8'))['facts']]
    def call(payload,authorized=True):
        started=time.perf_counter()
        request=Request('http://127.0.0.1:'+str(endpoint['port'])+'/ask',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key if authorized else 'invalid'})
        try:
            with build_opener(ProxyHandler({})).open(request,timeout=60) as response:status=response.status;body=json.load(response)
        except HTTPError as exc:status=exc.code;body=json.load(exc)
        return status,body,(time.perf_counter()-started)*1000
    try:
        scenarios=[
          ('approved_gate',{'question':'What is the AXIS opening fee?'},200,[]),
          ('ipc_auth_required',{'question':'AXIS opening fee'},401,None),
          ('preview_requires_selection',{'question':'AXIS opening fee','knowledge_mode':'review_preview'},422,None),
          ('unknown_mode_rejected',{'question':'AXIS opening fee','knowledge_mode':'production'},422,None),
          ('english_source_bound',{'question':'What is the AXIS opening fee?','knowledge_mode':'review_preview','selected_fact_ids':ids,'actor_scope':'integration-a'},200,['F0010']),
          ('arabic_qnb_source_bound',{'question':'رسوم سحب QNB من ATM كام؟','knowledge_mode':'review_preview','selected_fact_ids':ids,'actor_scope':'integration-a'},200,['F0076']),
          ('selected_record_only',{'question':'AXIS opening fee and minimum initial deposit','knowledge_mode':'review_preview','selected_fact_ids':['F0010'],'actor_scope':'integration-a'},200,['F0010']),
        ]
        for name,payload,expected_status,expected_ids in scenarios:
            code,actual,elapsed=call(payload,name!='ipc_auth_required')
            passed=code==expected_status and (expected_ids is None or set(actual.get('supported_fact_ids',[]))==set(expected_ids))
            if name=='selected_record_only':passed=passed and not actual.get('complete')
            results.append({'name':name,'passed':passed,'http_status':code,'http_ms':elapsed,'expected_fact_ids':expected_ids,'actual':actual})
    finally:
        stop(child,log)
        summary={'passed':sum(r['passed'] for r in results),'total':len(results),'native':'NOT RUN','developer_authored':True,'rows':results}
        (out/'RESULTS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':summary['passed'],'total':summary['total'],'report':str(out/'RESULTS.json')}))
    if not all(r['passed'] for r in results):raise SystemExit(1)

if __name__=='__main__':main()
