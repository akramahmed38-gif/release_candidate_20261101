"""Deploy reviewed next revision only with the owned web process stopped."""
from pathlib import Path
import ast,hashlib,json,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
if (ROOT/'RUNNING.json').exists():raise SystemExit('Stop owned staging process before replacing runtime files')
NEXT=ROOT/'next_revision'
for p in NEXT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'))
backup=ROOT/'state/revision_backups'/time.strftime('%Y%m%d_%H%M%S');backup.mkdir(parents=True)
targets=[ROOT/'run_admin.py',ROOT/'application/main.py',ROOT/'application/src/routes/chatbot.py']
for p in targets:
    relative=p.relative_to(ROOT);destination=backup/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
for name in ['catalog_store.py','engine_worker.py','engine_controller.py','admin_knowledge.py','knowledge_workspace.html','knowledge_workspace.js']:shutil.copy2(NEXT/name,ROOT/name)
p=ROOT/'run_admin.py';s=p.read_text(encoding='utf-8')
s=s.replace('from isolation import configuration,install_guards,validate_settings,contained','from engine_controller import start as start_engine,stop as stop_engine\nENGINE_PROCESS,ENGINE_LOG=start_engine()\nfrom isolation import configuration,install_guards,validate_settings,contained')
s=s.replace("'chatbot':'adapter_pending'","'chatbot':'isolated_core_review_and_approval_gate'")
s=s.replace("banner='<div", "banner='<div")
s=s.replace('NO EMPLOYEE OR PRODUCTION ACCESS |','NO EMPLOYEE OR PRODUCTION ACCESS | <a href="/training/admin/knowledge-workspace">Admin knowledge workspace</a> |')
s=s.replace("receipt['stopped_epoch']=time.time();", "stop_engine(ENGINE_PROCESS,ENGINE_LOG)\n        receipt['stopped_epoch']=time.time();")
p.write_text(s,encoding='utf-8')
p=ROOT/'application/main.py';s=p.read_text(encoding='utf-8');needle='app.include_router(chatbot.chatbot_router)';assert needle in s
s=s.replace(needle,needle+'\nfrom admin_knowledge import router as admin_knowledge_router\napp.include_router(admin_knowledge_router)')
p.write_text(s,encoding='utf-8')
p=ROOT/'application/src/routes/chatbot.py';s=p.read_text(encoding='utf-8')
s=s.replace('class ChatbotAskRequest(BaseModel):','class ChatbotAskRequest(BaseModel):\n    knowledge_mode: str = "approved"\n    selected_fact_ids: list[str] = Field(default_factory=list, max_length=21)')
needle='    try:\n        ensure_sidecar_started = time.perf_counter()'
assert needle in s
s=s.replace(needle,'''    # Owned staging adapter: no production sidecar call or request-time spawn.
    from admin_knowledge import call_engine
    user_context = await _resolve_chatbot_user_context(request)
    result = await run_in_threadpool(call_engine, {
        'question': question, 'knowledge_mode': payload.knowledge_mode,
        'selected_fact_ids': payload.selected_fact_ids,
        'conversation_id': payload.conversation_id or payload.session_id or request_id,
    }, user_context)
    result.update(request_id=request_id, conversation_id=payload.conversation_id,
                  session_id=payload.session_id, message_id=payload.message_id)
    return result

    try:
        ensure_sidecar_started = time.perf_counter()''',1)
# Existing UI feedback is staging-local and cannot contact the legacy sidecar.
needle='async def submit_chatbot_feedback(request: Request, payload: ChatbotFeedbackRequest) -> dict[str, Any]:\n'
assert needle in s
s=s.replace(needle,needle+'''    from catalog_store import db
    from admin_knowledge import hashlib
    actor = await _resolve_chatbot_user_context(request)
    event = {'request_id': payload.request_id, 'rating': payload.rating,
             'actor_hash': hashlib.sha256(str(actor.get('username')).encode()).hexdigest(),
             'question_sha256': hashlib.sha256(payload.question.encode()).hexdigest(),
             'answer_sha256': hashlib.sha256(payload.answer.encode()).hexdigest(),
             'source_references': [{'fact_id': x.get('fact_id')} for x in payload.sources],
             'environment': 'isolated_admin_staging'}
    with db() as connection:
        connection.execute('insert into event(at,kind,target,data) values(?,?,?,?)',
                           (time.time(),'answer_feedback',payload.conversation_id or '',json.dumps(event)))
    return {'saved': True, 'staging_only': True}
''')
p.write_text(s,encoding='utf-8')
for p in targets:ast.parse(p.read_text(encoding='utf-8'))
receipt={'revision':'admin_catalog_engine_integration','backup':str(backup),'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in targets+[ROOT/n for n in ['catalog_store.py','engine_worker.py','engine_controller.py','admin_knowledge.py','knowledge_workspace.html','knowledge_workspace.js']]},'production_modified':False,'approvals_granted':0}
(ROOT/'WORKSPACE_REVISION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps({'prepared':True,'backup':str(backup)}))
