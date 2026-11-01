"""Loopback developer demonstration; never an employee or production route."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import argparse, hashlib, hmac, json, os, secrets, sys, threading, time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'source/candidate'))

HTML = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Fawry isolated developer demo</title>
<h1>Fawry isolated developer demo</h1>
<p>UNAPPROVED EVIDENCE TEST ONLY. Not official policy. No employee pilot access.</p>
<p>Local Core retrieval only. Native BGE/Chroma and Qwen have NOT been validated here.</p>
<label>Developer access token <input id="token" type="password" autocomplete="off"></label>
<button id="connect">Connect</button><button id="fresh">New conversation</button>
<label>Question <textarea id="question" rows="4" cols="65" dir="auto"></textarea></label>
<button id="ask">Ask test evidence</button><pre id="answer" dir="auto"></pre>
<script src="/app.js"></script></html>'''
JS = '''let conversation=null;
async function call(path,body){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error);return d;}
async function fresh(){const d=await call('/conversations',{});conversation=d.conversation_id;document.getElementById('answer').textContent='New isolated conversation';}
document.getElementById('connect').onclick=async()=>{try{await call('/session',{token:document.getElementById('token').value});document.getElementById('token').value='';await fresh();}catch(e){document.getElementById('answer').textContent=e.message;}};
document.getElementById('fresh').onclick=()=>fresh().catch(e=>document.getElementById('answer').textContent=e.message);
document.getElementById('ask').onclick=async()=>{try{if(!conversation)throw Error('Connect first');const d=await call('/ask',{question:document.getElementById('question').value,conversation_id:conversation});document.getElementById('answer').textContent=d.answer+'\\n\\n'+JSON.stringify({status:d.answer_status,citations:d.citations,timing:d.demo_http_handler_ms},null,2);}catch(e){document.getElementById('answer').textContent=e.message;}};'''


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, engine, token, audit_path):
        if not isinstance(token,str) or len(token)<32:raise ValueError('Developer token must have at least 32 characters')
        self.engine=engine;self.token=token;self.sessions={};self.guard=threading.RLock()
        self.audit_path=Path(audit_path);self.audit_path.parent.mkdir(parents=True,exist_ok=True)
        self.login_failures=[]
        super().__init__(('127.0.0.1',0),Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data,status=200,kind='application/json',cookie=None):
        body=(json.dumps(data,ensure_ascii=False) if kind=='application/json' else data).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8')
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(body)
    def safe_origin(self):
        host='127.0.0.1:'+str(self.server.server_port)
        return self.headers.get('Host')==host and self.headers.get('Origin', 'http://'+host)=='http://'+host
    def do_GET(self):
        if not self.safe_origin():return self.reply({'error':'origin_rejected'},403)
        if self.path=='/':return self.reply(HTML,kind='text/html')
        if self.path=='/app.js':return self.reply(JS,kind='application/javascript')
        if self.path=='/health':return self.reply({'status':'developer_demo','employee_access':False,'facts_approved':False,'backend':self.server.engine.backend.mode,'native':'NOT RUN'})
        return self.reply({'error':'not_found'},404)
    def do_POST(self):
        started=time.perf_counter();request_id=secrets.token_hex(12)
        if not self.safe_origin():return self.reply({'error':'origin_rejected'},403)
        if self.path not in {'/session','/conversations','/ask','/logout'}:return self.reply({'error':'not_found'},404)
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply({'error':'json_required'},415)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=12000:raise ValueError()
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError()
        except (ValueError,UnicodeError):return self.reply({'error':'invalid_request'},400)
        with self.server.guard:
            now=time.monotonic()
            if self.path=='/session':
                self.server.login_failures=[t for t in self.server.login_failures if now-t<60]
                if len(self.server.login_failures)>=5:return self.reply({'error':'login_backoff'},429)
                token=data.get('token')
                if set(data)!={'token'} or not isinstance(token,str) or not hmac.compare_digest(token,self.server.token):
                    self.server.login_failures.append(now);return self.reply({'error':'unauthorized'},401)
                sid=secrets.token_urlsafe(32);self.server.sessions[sid]={'expires':now+3600,'conversations':set()}
                return self.reply({'authenticated':True,'employee_access':False},cookie='rc_session='+sid+'; HttpOnly; SameSite=Strict; Path=/')
            try:
                cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''));sid=cookie['rc_session'].value
            except (KeyError,ValueError):return self.reply({'error':'unauthorized'},401)
            session=self.server.sessions.get(sid)
            if not session or session['expires']<=now:return self.reply({'error':'unauthorized'},401)
            if self.path=='/logout':
                self.server.sessions.pop(sid,None);return self.reply({'logged_out':True},cookie='rc_session=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/')
            if self.path=='/conversations':
                if data:return self.reply({'error':'invalid_request'},400)
                if len(session['conversations'])>=30:return self.reply({'error':'conversation_limit'},429)
                cid=secrets.token_urlsafe(24);session['conversations'].add(cid)
                return self.reply({'conversation_id':cid})
            if set(data)!={'question','conversation_id'} or not isinstance(data.get('question'),str) or not 0<len(data['question'].strip())<=1500 or not isinstance(data.get('conversation_id'),str):
                return self.reply({'error':'invalid_request'},400)
            if data['conversation_id'] not in session['conversations']:return self.reply({'error':'conversation_not_owned'},403)
            try:
                answer=self.server.engine.ask(data['question'],data['conversation_id'],sid)
                if not answer.get('fixture_only') or answer.get('normal_runtime_eligible') is not False:raise RuntimeError('Test-only response invariant')
                answer['demo_http_handler_ms']=(time.perf_counter()-started)*1000
                event={'request_id':request_id,'status':answer.get('answer_status'),'handler_ms':answer['demo_http_handler_ms'],'fixture_only':True}
                with self.server.audit_path.open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
                return self.reply(answer)
            except Exception as exc:
                with self.server.audit_path.open('a',encoding='utf-8') as f:f.write(json.dumps({'request_id':request_id,'error_type':type(exc).__name__})+'\n')
                return self.reply({'error':'request_failed','request_id':request_id,'complete':False},503)


def create_engine(workspace):
    from candidate import CatalogEngine
    from run_catalog import prepare
    prepare(Path(workspace))
    return CatalogEngine(Path(workspace),test_mode=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--technical-fixture-demo',action='store_true');parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args()
    if not args.technical_fixture_demo:raise SystemExit('Only explicitly labelled developer fixtures are available; employee pilot is blocked')
    token=os.environ.get('FAWRY_RC_DEVELOPER_TOKEN','')
    if len(token)<32:raise SystemExit('Set FAWRY_RC_DEVELOPER_TOKEN to a private developer token of at least 32 characters')
    engine=create_engine(args.workspace)
    server=DemoServer(engine,token,args.workspace/'demo_audit.jsonl')
    print(json.dumps({'url':'http://127.0.0.1:'+str(server.server_port),'employee_access':False,'approved_facts':0,'native':'NOT RUN'}),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
