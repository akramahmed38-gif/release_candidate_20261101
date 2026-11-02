"""Authenticated extension to the existing Training admin application."""
from pathlib import Path
import hashlib,json,time,uuid
from urllib.request import Request as URLRequest,build_opener,ProxyHandler
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse
from pydantic import BaseModel,Field
from routes.users.auth_utils import get_current_user
from catalog_store import rows,db
ROOT=Path(__file__).resolve().parent

def admin(user=Depends(get_current_user)):
    if user.get('role')!='admin':raise HTTPException(403,'Administrator required')
    return user

router=APIRouter(dependencies=[Depends(admin)])

def call_engine(payload,actor):
    endpoint=json.loads((ROOT/'.private/engine_endpoint.json').read_text(encoding='utf-8'))
    key=(ROOT/'.private/engine.key').read_text(encoding='ascii')
    identity=actor.get('sub') or actor.get('email') or actor.get('username')
    if not identity or identity=='anonymous':raise HTTPException(403,'Authenticated actor required')
    data={**payload,'actor_scope':hashlib.sha256(str(identity).encode()).hexdigest()}
    request=URLRequest('http://127.0.0.1:'+str(endpoint['port'])+'/ask',data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
    try:
        with build_opener(ProxyHandler({})).open(request,timeout=60) as response:return json.load(response)
    except Exception as exc:
        from urllib.error import HTTPError
        if isinstance(exc,HTTPError):
            value=json.load(exc);raise HTTPException(exc.code,value.get('detail','Isolated worker failed')) from None
        raise HTTPException(503,'Isolated answer backend unavailable; not a resource-busy claim') from None

class Ask(BaseModel):
    question:str=Field(min_length=1,max_length=4000)
    conversation_id:str=Field(default_factory=lambda:uuid.uuid4().hex,max_length=200)
    knowledge_mode:str='approved'
    selected_fact_ids:list[str]=Field(default_factory=list,max_length=21)

@router.get('/admin/knowledge-workspace',response_class=HTMLResponse)
def page():return (ROOT/'knowledge_workspace.html').read_text(encoding='utf-8')

@router.get('/admin/knowledge-workspace.js')
def script():return FileResponse(ROOT/'knowledge_workspace.js',media_type='application/javascript')

@router.get('/api/v1/admin/knowledge/{kind}')
def records(kind:str,q:str='',service:str=''):
    if kind not in {'profile','source','unit','fact','pdf_page'}:raise HTTPException(404,'Unknown record type')
    result=rows(kind)
    if service:
        result=[r for r in result if r.get('service_id')==service or service in r.get('service_ids',[])]
    if q:
        if len(q)>200:raise HTTPException(422,'Search too long')
        result=[r for r in result if q.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
    return {'records':result,'count':len(result),'normal_runtime_eligible':0,'approval_inferred':False}

@router.post('/api/v1/admin/knowledge-ask')
def ask(payload:Ask,user=Depends(admin)):
    result=call_engine(payload.model_dump(),user)
    result['conversation_id']=payload.conversation_id
    return result

@router.get('/api/v1/admin/knowledge-status')
def status():
    return {'counts':{k:len(rows(k)) for k in ['profile','source','unit','fact','pdf_page']},'native':'NOT RUN','semantic_acceptance':'NO-GO','approvals_granted':0,'employee_access':False}
