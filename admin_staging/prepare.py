"""Apply isolated deployment configuration to imported existing app only."""
from pathlib import Path
import ast,hashlib,json
from isolation import ROOT,configuration,contained
APP=ROOT/'application'

def replace_function(path,name,code):
    s=path.read_text(encoding='utf-8-sig');tree=ast.parse(s)
    nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name]
    if len(nodes)!=1:raise ValueError('Expected one function '+name)
    n=nodes[0];lines=s.splitlines(keepends=True);indent=' '*n.col_offset
    lines[n.lineno-1:n.end_lineno]=[indent+line+'\n' for line in code.splitlines()]
    path.write_text(''.join(lines),encoding='utf-8')

def main():
    manifest=json.loads((ROOT/'IMPORTED_APPLICATION_MANIFEST.json').read_text(encoding='utf-8'))
    if not manifest.get('complete'):raise RuntimeError('Incomplete application copy')
    done=ROOT/'PREPARED.json'
    if done.exists():return
    paths=configuration();private=ROOT/'.private';private.mkdir(exist_ok=True)
    import secrets
    secret=private/'jwt.key'
    if not secret.exists():secret.write_text(secrets.token_urlsafe(64),encoding='ascii')
    config={'APP_NAME':'Fawry HR Training — ISOLATED ADMIN STAGING','APP_VERSION':'admin-20261102','PATH_LOGS':str(paths['logs']),'PATH_DATA_ROOT':str(paths['uploads']),'PATH_ASSETS_ROOT':str(paths['assets']),'PATH_MODELS_ROOT':str(paths['models']),'PATH_OUTPUT_ROOT':str(paths['output']),'SQLITE_DB_PATH':str(paths['databases']/'training.db'),'FILE_MAX_SIZE':26214400,'FILE_DEFAULT_CHUNK_SIZE':1048576}
    (APP/'config').mkdir(exist_ok=True)
    (APP/'config/config.yaml').write_text(''.join(k+': '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in config.items()),encoding='utf-8')
    (ROOT/'STAGING_PATHS.json').write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    replace_function(APP/'src/routes/users/admin_credentials.py','credential_path',"""def credential_path():
    target=Path(os.environ['STAGING_ADMIN_CREDENTIAL_PATH']).resolve()
    if target.parent!=Path(os.environ['STAGING_PRIVATE_ROOT']).resolve():
        raise RuntimeError('Staging credentials must be private and isolated')
    return target""")
    replace_function(APP/'main.py','_cors_allowed_origins',"""def _cors_allowed_origins():
    return ['http://127.0.0.1:'+os.environ['STAGING_PORT']]""")
    mainpath=APP/'main.py';s=mainpath.read_text(encoding='utf-8')
    s=s.replace('        await users_router.ensure_manager_employee(app.state.db_client)','        # Staging: no seeded identities.')
    s=s.replace('        await resigned_users_service.ensure_default_protected_accounts()','        # Staging: no production protected-account seeding.')
    s=s.replace('    app.state.auto_resign_scheduler_task = asyncio.create_task(auto_resign_scheduler(app))','    app.state.auto_resign_scheduler_task = None  # Staging background jobs disabled')
    # Authentication bodies/traffic are never recorded by the generic audit middleware.
    tree=ast.parse(s)
    for n in sorted([n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and 'audit' in n.name],key=lambda n:n.lineno,reverse=True):
        lines=s.splitlines(keepends=True);at=n.body[0].lineno-1
        lines[at:at]=['    if _normalize_request_path(request) in PUBLIC_API_PATHS:\n','        return await call_next(request)\n'];s=''.join(lines)
    mainpath.write_text(s,encoding='utf-8')
    users=APP/'src/routes/users/users_router.py';s=users.read_text(encoding='utf-8');tree=ast.parse(s)
    n=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='ensure_manager_employee');lines=s.splitlines(keepends=True);lines[n.body[0].lineno-1:n.body[0].lineno-1]=['    if os.environ.get("FAWRY_ISOLATED_ADMIN")=="1":\n','        return\n'];s=''.join(lines)
    s=s.replace('print(f"LOGIN :: Login attempt for email: {email} with OTP/password field.")','print("LOGIN :: Identity and credential omitted.")');users.write_text(s,encoding='utf-8')
    replace_function(APP/'src/routes/chatbot.py','_ensure_sidecar_running',"""async def _ensure_sidecar_running():
    return {'running':False,'error':'Staging admin application is available; its isolated chatbot adapter is not connected yet. No production sidecar was contacted or started.'}""")
    replace_function(APP/'src/routes/chatbot.py','_setup_message',"""def _setup_message():
    return 'Staging chatbot integration is pending; no production action is required.'""")
    # Route every logger default to the configured private staging log directory.
    p=APP/'src/utils/logging_utils.py';s=p.read_text(encoding='utf-8');s=s.replace('    # Ensure log directory exists','    log_dir = os.environ.get("STAGING_LOG_DIR", log_dir)\n    # Ensure log directory exists');p.write_text(s,encoding='utf-8')
    # Verify the copied frontend supports an explicit same-origin runtime API base.
    bundles=list((APP/'hr-training-frontend/build').rglob('*.js'))
    if not bundles or not any('__TRAINING_API_BASE_URL' in p.read_text(encoding='utf-8',errors='ignore') for p in bundles):raise RuntimeError('Frontend API origin override not proven')
    before={r['path']:r['staged_sha256'] for r in manifest['files']}
    after={p.relative_to(APP).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in APP.rglob('*') if p.is_file()}
    done.write_text(json.dumps({'staging_only':True,'changes':[{'path':p,'before':before.get(p),'after':h} for p,h in after.items() if before.get(p)!=h],'state_copied_from_production':False,'jobs_disabled':True,'notifications_disabled':True},indent=2)+'\n',encoding='utf-8')
    print('Existing app prepared; production stores, identity and sidecar excluded')
if __name__=='__main__':main()
