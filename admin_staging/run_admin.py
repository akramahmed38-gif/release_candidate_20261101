"""Run the existing HR app with private state and its normal admin auth."""
from pathlib import Path
import asyncio,contextlib,hashlib,hmac,importlib.util,json,os,secrets,sys,tempfile,threading,time,uuid
ROOT=Path(__file__).resolve().parent
APP=ROOT/'application'
PRIVATE=ROOT/'.private'
PORT=int(os.environ.get('FAWRY_STAGING_PORT','8765'))
# Never inherit application production credentials or service destinations.
for key in list(os.environ):
    if key.startswith(('TRAINING_','SMTP_','CHATBOT_','UNIFIED_')):os.environ.pop(key,None)
os.environ.update(FAWRY_ISOLATED_ADMIN='1',STAGING_PORT=str(PORT),STAGING_PRIVATE_ROOT=str(PRIVATE),STAGING_ADMIN_CREDENTIAL_PATH=str(PRIVATE/'admin_credentials.json'),STAGING_JWT_SECRET=(PRIVATE/'jwt.key').read_text(encoding='ascii'),STAGING_LOG_DIR=str(ROOT/'logs'),TRAINING_SMTP_DISABLED='1',SMTP_DISABLED='1',AUTO_RESIGN_USERS_ENABLED='0',TRAINING_DASHBOARD_SNAPSHOT_READS='0',TRAINING_PUBLIC_BASE_URL='http://127.0.0.1:'+str(PORT)+'/training',PORTAL_DATABASES_DIR=str(ROOT/'state/databases'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1')
os.chdir(APP);sys.dont_write_bytecode=True
sys.path.insert(0,str(APP));sys.path.insert(0,str(APP/'src'))
from isolation import configuration,install_guards,validate_settings,contained
paths=configuration();tempfile.tempdir=str(paths['temp'])
install_guards()
from utils.config_utils import get_settings
proof=validate_settings(get_settings())
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import HTMLResponse,RedirectResponse,Response
from contextlib import asynccontextmanager
import uvicorn
spec=importlib.util.spec_from_file_location('existing_hr_staging',APP/'main.py');hr=importlib.util.module_from_spec(spec);spec.loader.exec_module(hr)
from routes.users import users_router
from models.db_schemas import Employee
from models.employee_model import EmployeeModel
from sqlalchemy import select,func
RUN_ID=uuid.uuid4().hex
CREDENTIALS=PRIVATE/'admin_credentials.json'
CSRF=secrets.token_urlsafe(48)

@asynccontextmanager
async def lifespan(app):
    await hr.ensure_runtime_ready(hr.app)
    proof.update(database_created=Path(hr.app.state.settings.SQLITE_DB_PATH).is_file(),background_jobs_started=False,production_connected=False)
    (ROOT/'ISOLATION_RECEIPT.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8')
    yield
    await hr.app.state.engine.dispose()

app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def staging_boundary(request,call_next):
    host=request.headers.get('host','')
    origin=request.headers.get('origin')
    if host!='127.0.0.1:'+str(PORT):return Response('Invalid staging host',status_code=400)
    if origin and origin!='http://127.0.0.1:'+str(PORT):return Response('Cross-origin staging request denied',status_code=403)
    response=await call_next(request)
    if 'text/html' in response.headers.get('content-type',''):
        body=b''.join([part async for part in response.body_iterator]).decode('utf-8')
        env='<script src="/staging/env.js"></script>'
        body=body.replace('</head>',env+'</head>')
        banner='<div id="staging-environment" role="status" style="padding:12px;background:#fff3cd;color:#493d00;border-bottom:2px solid #997300;position:sticky;top:0;z-index:99999;font:14px Arial">ISOLATED ADMIN STAGING — UNAPPROVED KNOWLEDGE — NO EMPLOYEE OR PRODUCTION ACCESS | بيئة اختبار معزولة؛ المعرفة غير معتمدة</div>'
        body=body.replace('<body>', '<body>'+banner)
        headers={k:v for k,v in response.headers.items() if k.lower() not in {'content-length','content-type'}}
        response=HTMLResponse(body,status_code=response.status_code,headers=headers)
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'none'; form-action 'self'"
    return response

@app.get('/health')
async def health():
    return {'status':'ready','environment':'isolated_admin_staging','real_application':'existing HR Training FastAPI/React','authentication':'existing PBKDF2 admin credential verifier and JWT middleware','owner_setup_required':not CREDENTIALS.exists(),'employee_access':False,'production':False,'chatbot':'adapter_pending','native_acceptance':'NOT RUN'}

@app.get('/staging/env.js')
async def environment_js():
    return Response("window.__TRAINING_API_BASE_URL='/training';window.__FAWRY_ISOLATED_STAGING=true;",media_type='application/javascript')

@app.get('/')
async def entry():return RedirectResponse('/training/login?lang=en' if CREDENTIALS.exists() else '/staging/setup')

@app.get('/staging/setup')
async def setup_page():
    if CREDENTIALS.exists():return RedirectResponse('/training/login?lang=en')
    html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Fawry staging account setup</title></head><body><main style="max-width:540px;margin:40px auto;font-family:Arial"><h1>Create your staging administrator</h1><p>This provisions a new account in the isolated existing Training application. Enter the password privately in this browser. No production credential store was copied.</p><p>Use the administrator username you selected. This creates only an isolated staging account; production remains unchanged.</p><form method="post" action="/staging/setup"><input type="hidden" name="csrf" value="__CSRF__"><label>Administrator username <input type="text" name="email" value="training.admin" autocomplete="username" required></label><br><br><label>Display name <input name="display_name" required maxlength="80"></label><br><br><label>New staging password <input type="password" name="password" autocomplete="new-password" minlength="14" required></label><br><br><label>Confirm password <input type="password" name="confirm" autocomplete="new-password" minlength="14" required></label><br><br><button type="submit">Create staging account, then sign in</button></form><p>Knowledge remains unapproved. This account cannot approve real business policy.</p></main></body></html>'''
    response=HTMLResponse(html.replace('__CSRF__',CSRF));response.set_cookie('staging_setup_csrf',CSRF,httponly=True,samesite='strict',path='/staging/setup');return response

@app.post('/staging/setup')
async def provision(request:Request):
    if CREDENTIALS.exists():raise HTTPException(409,'Staging owner is already provisioned')
    form=await request.form()
    if not hmac.compare_digest(str(form.get('csrf','')),CSRF) or not hmac.compare_digest(request.cookies.get('staging_setup_csrf',''),CSRF):raise HTTPException(403,'Setup verification failed')
    email=str(form.get('email','')).strip().lower();display=str(form.get('display_name','')).strip();password=str(form.get('password',''));confirm=str(form.get('confirm',''))
    if not __import__('re').fullmatch(r'[a-z0-9._@+\-]{3,120}',email) or not display or len(password)<14 or password!=confirm or password!=password.strip():raise HTTPException(400,'Use a valid administrator username, a display name, and matching passwords of at least 14 characters without surrounding whitespace')
    async with hr.app.state.db_client() as session:
        count=await session.scalar(select(func.count()).select_from(Employee))
        if count:raise HTTPException(409,'Nonempty staging identity store; setup cannot reset accounts')
    await users_router._ensure_default_admin_branch(hr.app.state.db_client)
    employee=Employee(hr_id='STAGE-OWNER-'+uuid.uuid4().hex[:12],name=display,title='Staging owner',department='admin',email=email,password=users_router.OTP_ONLY_PASSWORD,branch_code=users_router.DEFAULT_ADMIN_BRANCH_CODE,employment_status='active',auto_resign_exempt=True,login_history_state='native')
    salt=secrets.token_bytes(32);digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,600000)
    credential={'username':email,'salt':salt.hex(),'digest':digest.hex(),'iterations':600000}
    temporary=PRIVATE/'admin_credentials.pending'
    temporary.write_text(json.dumps(credential),encoding='utf-8')
    model=await EmployeeModel.create_instance(hr.app.state.db_client)
    try:await model.create_user(employee)
    except Exception:
        temporary.unlink(missing_ok=True);raise HTTPException(500,'Staging account provisioning failed') from None
    temporary.replace(CREDENTIALS)
    users_router.ADMIN_USER=email;users_router.ADMIN_ALIASES={email}
    response=RedirectResponse('/training/login?lang=en',status_code=303);response.delete_cookie('staging_setup_csrf',path='/staging/setup');return response

app.mount('/training',hr.app)

if __name__=='__main__':
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=PORT,workers=1,access_log=False,log_level='warning'))
    receipt={'pid':os.getpid(),'run_id':RUN_ID,'url':'http://127.0.0.1:'+str(PORT),'script':str(Path(__file__).resolve()),'environment':'isolated_admin_staging','started_epoch':time.time()}
    (ROOT/'RUNNING.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    stop=PRIVATE/'stop-request'
    def watch():
        while not server.should_exit:
            try:
                if stop.exists() and stop.read_text(encoding='utf-8').strip()==RUN_ID:server.should_exit=True
            except OSError:pass
            time.sleep(.25)
    threading.Thread(target=watch,daemon=True).start()
    try:server.run()
    finally:
        receipt['stopped_epoch']=time.time();(ROOT/'LAST_RUN.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
        (ROOT/'RUNNING.json').unlink(missing_ok=True)
