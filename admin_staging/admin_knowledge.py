"""Authenticated extension to the existing Training admin application."""
from pathlib import Path
import hashlib,json,time,uuid
from urllib.request import Request as URLRequest,build_opener,ProxyHandler
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import HTMLResponse,FileResponse,Response
from pydantic import BaseModel,Field
from routes.users.auth_utils import get_current_user
from catalog_store import rows,db,get
from catalog_queries import filter_records
from source_preview import render as render_source,SourcePreviewError
ROOT=Path(__file__).resolve().parent

def admin(user=Depends(get_current_user)):
    if user.get('role')!='admin':raise HTTPException(403,'Administrator required')
    return user

router=APIRouter(dependencies=[Depends(admin)])

def call_engine(payload,actor):
    if payload.get('knowledge_mode','approved')!='approved' and actor.get('role')!='admin':raise HTTPException(403,'Administrator review access required')
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
def records(kind:str,q:str='',service:str='',review_status:str='',language:str='',source_version:str='',eligible:bool|None=None):
    if kind not in {'profile','source','unit','fact','pdf_page'}:raise HTTPException(404,'Unknown record type')
    result=rows(kind)
    try:result=filter_records(result,service=service,review_status=review_status,language=language,source_version=source_version,eligible=eligible)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    if q:
        if len(q)>200:raise HTTPException(422,'Search too long')
        result=[r for r in result if q.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
    return {'records':result,'count':len(result),'normal_runtime_eligible':0,'approval_inferred':False}

@router.get('/api/v1/admin/knowledge-citation/{fact_id}',response_class=HTMLResponse)
def citation(fact_id:str,version:str):
    import re
    if not re.fullmatch(r'(?:F\d{4}|QA-[a-f0-9]{24})',fact_id) or not re.fullmatch('[a-f0-9]{64}',version):raise HTTPException(422,'Exact original fact ID and source SHA-256 required')
    if fact_id.startswith('QA-'):
        pointer=json.loads((ROOT/'BENCHMARK_SNAPSHOT_PREPARATION.json').read_text(encoding='utf-8'))
        snapshot=Path(pointer['path']).resolve()
        if not snapshot.is_relative_to((ROOT/'state/benchmark_snapshots').resolve()):raise HTTPException(409,'Invalid review snapshot')
        manifest=json.loads((snapshot/'MANIFEST.json').read_text(encoding='utf-8'));raw=(snapshot/'records.jsonl').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest['record_file_sha256']:raise HTTPException(409,'Review registry changed')
        choices=[r for r in map(json.loads,raw.decode('utf-8').splitlines()) if r['record_id']==fact_id and r['source_sha256']==version and not r['hold_reason']]
        if len(choices)!=1:raise HTTPException(404,'Eligible review reference unavailable')
        fact={**choices[0],'fact_id':fact_id}
    else:
        try:fact=get('fact',fact_id,version)
        except ValueError:raise HTTPException(404,'Registered fact version unavailable') from None
    try:return render_source(fact)
    except SourcePreviewError as exc:raise HTTPException(exc.status,str(exc)) from None

@router.post('/api/v1/admin/knowledge-ask')
def ask(payload:Ask,user=Depends(admin)):
    result=call_engine(payload.model_dump(),user)
    result['conversation_id']=payload.conversation_id
    from answer_feedback import capture
    result['diagnostic_trace_id']=capture(payload.model_dump(),result,user)
    return result

class Feedback(BaseModel):
    trace_id:str=Field(max_length=38)
    note:str=Field(min_length=1,max_length=2000)

@router.post('/api/v1/admin/answer-feedback')
def submit_feedback(payload:Feedback,user=Depends(admin)):
    from answer_feedback import report
    try:return report(payload.trace_id,payload.note,user)
    except LookupError:raise HTTPException(404,'Trace unavailable') from None

@router.get('/api/v1/admin/answer-feedback')
def feedback_list(user=Depends(admin)):
    from answer_feedback import listing
    return {'reports':listing(user),'scope':'current_authenticated_administrator'}

@router.get('/api/v1/admin/answer-trace/{trace_id}')
def answer_trace(trace_id:str,user=Depends(admin)):
    from answer_feedback import read
    try:return read(trace_id,user)
    except LookupError:raise HTTPException(404,'Trace unavailable') from None

@router.get('/api/v1/admin/answer-trace/{trace_id}/export')
def export_trace(trace_id:str,user=Depends(admin)):
    from answer_feedback import export
    try:value=export(trace_id,user)
    except LookupError:raise HTTPException(404,'Trace unavailable') from None
    return Response(json.dumps(value,ensure_ascii=False),media_type='application/json',
                    headers={'Content-Disposition':'attachment; filename="'+trace_id+'.json"','Cache-Control':'no-store'})

@router.get('/api/v1/admin/knowledge-status')
def status():
    return {'counts':{k:len(rows(k)) for k in ['profile','source','unit','fact','pdf_page']},'native':'NOT RUN','semantic_acceptance':'NO-GO','approvals_granted':0,'employee_access':False}


def widget_mode(actor):
    from answer_feedback import owner
    try:value=get('widget_review_mode',owner(actor),'active')
    except ValueError:return 'approved'
    if value.get('expires_at',0)<time.time():return 'approved'
    return 'approved'  # Whole-QA lookup serving rejected; preserve safe original default.

class WidgetReviewMode(BaseModel):
    mode:str

@router.post('/api/v1/admin/chatbot-review-mode')
def set_widget_review_mode(payload:WidgetReviewMode,user=Depends(admin)):
    if payload.mode!='approved':raise HTTPException(409,'Full review pipeline integration is pending; source-QA lookup is not an accepted replacement')
    from answer_feedback import owner
    value={'mode':payload.mode,'expires_at':time.time()+1800,'normal_runtime_eligible':False,'scope':'explicit administrator opt-in; all fixed records; no per-question source filters'}
    with db() as c:
        c.execute("insert into record(kind,id,version,data) values('widget_review_mode',?,'active',?) on conflict(kind,id,version) do update set data=excluded.data",(owner(user),json.dumps(value)))
    return value
