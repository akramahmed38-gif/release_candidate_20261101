"""Owned loopback IPC worker; never a login or a production sidecar."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
import hashlib,hmac,json,os,sys,threading,time,uuid
class AdmissionDenied(RuntimeError):
    def __init__(self,events,wait_ms):self.events=events;self.wait_ms=wait_ms
ROOT=Path(__file__).resolve().parent
def progress(stage):print(json.dumps({'stage':stage,'epoch':time.time()}),flush=True)
progress('worker_start')
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT))
from isolation import install_guards
install_guards()
progress('guards_installed')
RELEASE=ROOT.parent
sys.path.insert(0,str(RELEASE/'source/candidate'))
from candidate import CatalogEngine
progress('candidate_imported')
from run_catalog import prepare
from observed_guard import ObservedBudget
BUDGET=ObservedBudget(stable_window=True)
WORK=ROOT/'state/e'/uuid.uuid4().hex[:8]
progress('preparing_private_sources')
prepare(WORK)
progress('sources_prepared')
ENGINE=CatalogEngine(WORK,test_mode=True)
progress('engine_initialized')
KEY=(ROOT/'.private/engine.key').read_text(encoding='ascii')
LOCK=threading.Lock()
AUTH=WORK/'test_eligibility.json'
BASE_AUTH=json.loads(AUTH.read_text(encoding='utf-8'))

def answer(data):
    question=str(data.get('question','')).strip()
    if not question or len(question)>4000:raise ValueError('Question length')
    mode=data.get('knowledge_mode','approved')
    if mode not in {'approved','review_preview'}:raise ValueError('Unsupported knowledge mode')
    if mode=='approved':
        return {'answer':'No genuinely approved evidence is eligible in this staging snapshot. To inspect unapproved technical fixtures, use the admin knowledge workspace and explicitly select review-preview records.\nلا توجد معلومات معتمدة مؤهلة في هذه البيئة. معاينة المعلومات غير المعتمدة متاحة من مساحة مراجعة المعرفة فقط.',
                'answer_status':'unsupported','complete':False,'clarification_needed':False,'sources':[],'citations':[],
                'supported_fact_ids':[],'knowledge_mode':mode,'backend':'approval_gate_no_model_call','normal_runtime_eligible':False,'native_acceptance':'NOT RUN'}
    selected=data.get('selected_fact_ids',[])
    if not isinstance(selected,list) or not selected or any(not isinstance(x,str) or x not in ENGINE.facts for x in selected):raise ValueError('Explicit existing technical fixture selection required')
    from catalog_store import rows
    eligible={f['fact_id'] for f in rows('fact') if f.get('test_fixture_only') and f.get('review_status')=='pending' and not f.get('quarantine_reason')}
    if not set(selected)<=eligible:raise ValueError('Selection includes held or revoked records')
    actor=str(data.get('actor_scope',''))
    if not actor:raise ValueError('Authenticated actor scope required')
    scope=hashlib.sha256((actor+'|'+','.join(sorted(set(selected)))).encode()).hexdigest()
    conversation=str(data.get('conversation_id') or uuid.uuid4().hex)
    if len(conversation)>200:raise ValueError('Conversation identifier length')
    with LOCK:
        old=ENGINE.definition['authorized_test_ids']
        try:
            ENGINE.definition['authorized_test_ids']=list(set(selected))
            AUTH.write_text(json.dumps({**BASE_AUTH,'authorized_test_fact_ids':list(set(selected))}),encoding='utf-8')
            guard_started=time.perf_counter()
            try:BUDGET.wait()
            except RuntimeError as exc:
                if str(exc)=='ResourceBudgetUnavailable':raise AdmissionDenied(list(BUDGET.events),(time.perf_counter()-guard_started)*1000) from None
                raise
            guard_wait=(time.perf_counter()-guard_started)*1000
            cpu_started=time.process_time()
            result=ENGINE.ask(question,scope+':'+conversation,scope)
            if not set(result.get('supported_fact_ids',[]))<=set(selected):raise RuntimeError('Selection boundary failed')
            result.update(knowledge_mode=mode,backend='local_Core_BM25_existing_candidate',native_acceptance='NOT RUN',normal_runtime_eligible=False,fixture_only=True)
            result['worker_resource_wait_ms']=guard_wait
            result['worker_process_cpu_ms']=(time.process_time()-cpu_started)*1000
            result['sources']=[{'source_name':c['source_document'],'location_label':json.dumps(c['locator'],ensure_ascii=False),'fact_id':c['fact_id'],'url':'/training/api/v1/admin/knowledge-citation/'+c['fact_id']+'?version='+c['source_sha256'],'source':c} for c in result.get('citations',[])]
            result['answer']='UNAPPROVED ADMIN REVIEW PREVIEW — NOT POLICY / معاينة غير معتمدة\n\n'+result['answer']
            return result
        finally:
            ENGINE.definition['authorized_test_ids']=old
            AUTH.write_text(json.dumps(BASE_AUTH),encoding='utf-8')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,value,status=200):
        body=json.dumps(value,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path!='/health':return self.reply({'detail':'Not found'},404)
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+KEY):return self.reply({'detail':'Unauthorized'},401)
        return self.reply({'ready':True,'backend':'Core_BM25','native':'NOT RUN','launch_id':os.environ['STAGING_ENGINE_LAUNCH_ID']})
    def do_POST(self):
        if self.path!='/ask':return self.reply({'detail':'Not found'},404)
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+KEY):return self.reply({'detail':'Unauthorized'},401)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=24000:raise ValueError('Invalid body size')
            data=json.loads(self.rfile.read(length));started=time.perf_counter()
            result=answer(data);result['worker_wall_ms']=(time.perf_counter()-started)*1000
            self.reply(result)
        except AdmissionDenied as exc:self.reply({'detail':'Resource admission denied; RAM/CPU headroom is unavailable. No answer or model call was attempted.','error_code':'resource_budget_unavailable','stage':'admission','guard_events':exc.events,'guard_wait_ms':exc.wait_ms,'complete':False},503)
        except ValueError as exc:self.reply({'detail':str(exc)},422)
        except Exception as exc:self.reply({'detail':'Isolated answer failed','error_type':type(exc).__name__,'complete':False},500)

class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer normally resolves a reverse-DNS hostname here. IPC has a
        # fixed loopback identity and must not wait on corporate DNS.
        TCPServer.server_bind(self)
        self.server_name='localhost'
        self.server_port=self.socket.getsockname()[1]

if __name__=='__main__':
    progress('binding_loopback_without_dns')
    server=LocalHTTPServer(('127.0.0.1',0),Handler)
    progress('loopback_ready')
    (ROOT/'.private/engine_endpoint.json').write_text(json.dumps({'pid':os.getpid(),'parent_pid':os.getppid(),'launch_id':os.environ['STAGING_ENGINE_LAUNCH_ID'],'port':server.server_port,'backend':'Core_BM25','native':'NOT RUN'}),encoding='utf-8')
    server.serve_forever()
