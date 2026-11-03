"""Disposable source lifecycle. Simulations never enter real evidence modes."""
from pathlib import Path
import hashlib,json,re,time,uuid
from catalog_store import db,SENSITIVE
ROOT=Path(__file__).resolve().parent
if ROOT.name=='next_revision':ROOT=ROOT.parent
UPLOADS=ROOT/'state/uploads/synthetic'

class WorkflowError(ValueError):pass
def digest(body):return hashlib.sha256(body).hexdigest()
def actor_id(actor):return digest(str(actor).encode())
def validate_namespace(namespace):
    if not re.fullmatch('syn-[a-f0-9]{32}',namespace):raise WorkflowError('Synthetic namespace required')
def read_row(c,kind,namespace,version):
    row=c.execute('select data from record where kind=? and id=? and version=?',(kind,namespace,str(version))).fetchone()
    if row is None:raise WorkflowError('Synthetic revision unavailable')
    return json.loads(row[0])
def write(c,kind,namespace,version,value):
    c.execute('insert into record(kind,id,version,data) values(?,?,?,?) on conflict(kind,id,version) do update set data=excluded.data',(kind,namespace,str(version),json.dumps(value,ensure_ascii=False)))
def event(c,namespace,action,actor,revision,source_sha,note=''):
    c.execute('insert into event(at,kind,target,data) values(?,?,?,?)',(time.time(),'synthetic_'+action,namespace,json.dumps({'actor_hash':actor_id(actor),'revision':revision,'source_sha256':source_sha,'note':note,'simulated':True,'real_policy_approval':False})))
def parse_source(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=65536:raise WorkflowError('Use a synthetic JSON document of at most64KiB')
    try:value=json.loads(raw)
    except (ValueError,UnicodeError):raise WorkflowError('Valid UTF-8 JSON source required') from None
    if not isinstance(value,dict) or set(value)!={'title','fields','views'}:raise WorkflowError('Source schema requires title, fields and views only')
    if not isinstance(value['title'],str) or not value['title'].startswith('SYNTHETIC ') or len(value['title'])>100:raise WorkflowError('Clearly SYNTHETIC title required')
    fields=value['fields'];views=value['views']
    if not isinstance(fields,dict) or not 1<=len(fields)<=8:raise WorkflowError('Use one to eight literal synthetic fields')
    for key,text in fields.items():
        if not re.fullmatch('[a-z][a-z0-9_]{0,39}',key) or not isinstance(text,str) or not text.startswith('SYN-') or len(text)>160:raise WorkflowError('Fields must contain SYN-prefixed test literals, never real business policy')
    if not isinstance(views,dict) or not set(views)<={'ar','en'}:raise WorkflowError('Only explicit Arabic/English test views are accepted')
    for language,renderings in views.items():
        if not isinstance(renderings,dict) or set(renderings)-set(fields):raise WorkflowError('Unknown source field in view')
        if any(fields[k]!=v for k,v in renderings.items()):raise WorkflowError('Test views must be exact source literals; no translation is generated')
    if SENSITIVE.search(json.dumps(value,ensure_ascii=False)):raise WorkflowError('Restricted content cannot be ingested through this synthetic workflow')
    return value

def current(c,namespace):
    validate_namespace(namespace);pointer=read_row(c,'synthetic_pointer',namespace,'active')
    return read_row(c,'synthetic_revision',namespace,pointer['revision'])
def source_path(row):
    path=(UPLOADS/row['namespace']/str(row['revision'])).with_suffix('.json').resolve()
    if not path.is_relative_to(UPLOADS.resolve()):raise WorkflowError('Source path escaped synthetic storage')
    return path
def verify(row):
    path=source_path(row)
    if not path.is_file():return 'source_missing'
    if path.stat().st_size>65536:return 'source_hash_changed'
    raw=path.read_bytes()
    if digest(raw)!=row['source_sha256']:return 'source_hash_changed'
    try:document=parse_source(raw)
    except WorkflowError:return 'source_document_invalid'
    if document!=row['document']:return 'source_view_binding_changed'
    return None
def new_revision(raw,actor,namespace=None):
    document=parse_source(raw);namespace=namespace or 'syn-'+uuid.uuid4().hex;validate_namespace(namespace)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("select 1 from record where kind='synthetic_pointer' and id=?",(namespace,)).fetchone():revision=current(c,namespace)['revision']+1
        else:revision=1
        row={'namespace':namespace,'revision':revision,'title':document['title'],'source_sha256':digest(raw),'document':document,'state':'draft','simulated_fidelity':None,'simulated_currentness':None,'positive_control':False,'normal_runtime_eligible':False,'real_approvals':0,'simulated':True,'created_at':time.time()}
        path=source_path(row);path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():raise WorkflowError('Synthetic revision file already exists')
        path.write_bytes(raw)
        write(c,'synthetic_revision',namespace,revision,row);write(c,'synthetic_pointer',namespace,'active',{'revision':revision})
        event(c,namespace,'ingest' if revision==1 else 'replacement_requires_review',actor,revision,row['source_sha256'])
    return row

def transition(namespace,action,actor,note=''):
    if len(note)>240 or SENSITIVE.search(note):raise WorkflowError('Use a short nonsensitive review note')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=current(c,namespace);before=row['state']
        if action=='submit':
            if before not in {'draft','rejected'}:raise WorkflowError('Only a draft/rejected revision can enter review')
            if verify(row):raise WorkflowError('Source must be replaced and reviewed after a change')
            row['state']='in_review'
        elif action=='reject':
            if before!='in_review' or not note.strip():raise WorkflowError('Reject an in-review revision with a reason')
            row.update(state='rejected',simulated_fidelity=None,simulated_currentness=None)
        elif action in {'simulate_fidelity','simulate_currentness'}:
            if before!='in_review' or verify(row):raise WorkflowError('Unchanged in-review source required')
            if action=='simulate_fidelity':
                row['simulated_fidelity']={'source_sha256':row['source_sha256'],'view_sha256':digest(json.dumps(row['document']['views'],sort_keys=True).encode()),'languages':list(row['document']['views']),'actor_hash':actor_id(actor),'simulated':True}
            else:row['simulated_currentness']={'source_sha256':row['source_sha256'],'actor_hash':actor_id(actor),'simulated':True}
        elif action=='publish_simulation':
            if before!='in_review' or verify(row) or any(not row[k] or row[k]['source_sha256']!=row['source_sha256'] for k in ['simulated_fidelity','simulated_currentness']):raise WorkflowError('Both exact-revision simulated decisions required')
            row['state']='published_simulation'
        elif action=='revoke':row['state']='revoked'
        elif action in {'delete_source','tamper_source'}:
            if not row['positive_control']:raise WorkflowError('First prove a working positive field preview for this revision')
            path=source_path(row)
            if action=='delete_source':path.unlink(missing_ok=True)
            else:path.write_bytes(b'SYNTHETIC TAMPERED TEST COPY')
        else:raise WorkflowError('Unknown synthetic lifecycle action')
        row['normal_runtime_eligible']=False;row['real_approvals']=0
        write(c,'synthetic_revision',namespace,row['revision'],row);event(c,namespace,action,actor,row['revision'],row['source_sha256'],note)
    return row

def preview(namespace,field,language,actor):
    if language not in {'ar','en'}:raise WorkflowError('Use Arabic or English test view')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=current(c,namespace);reason=verify(row)
        if not reason and row['state']!='published_simulation':reason='revision_not_published_simulation'
        if not reason and any(not row[k] or row[k]['source_sha256']!=row['source_sha256'] for k in ['simulated_fidelity','simulated_currentness']):reason='source_revision_needs_new_simulated_decisions'
        views=row['document']['views']
        if not reason and field not in row['document']['fields']:reason='missing_requested_field'
        if not reason and (language not in views or field not in views[language]):reason='missing_language_view'
        if not reason and (language not in row['simulated_fidelity']['languages'] or digest(json.dumps(views,sort_keys=True).encode())!=row['simulated_fidelity']['view_sha256']):reason='language_view_requires_new_simulated_fidelity'
        result={'mode':'synthetic_workflow_test','free_form_understanding_evaluated':False,'requested_scope':{'namespace':namespace,'field':field,'language':language},'normal_runtime_eligible':False,'real_policy_approval':False,'complete':not reason,'answer_status':'unsupported' if reason else 'complete','gap':reason,'answer':'SYNTHETIC WORKFLOW SIMULATION — NOT FAWRY POLICY. '+(reason if reason else field+': '+views[language][field]),'citations':[] if reason else [{'namespace':namespace,'revision':row['revision'],'source_sha256':row['source_sha256'],'field':field,'literal':views[language][field],'simulated':True}]}
        if not reason:
            row['positive_control']=True;write(c,'synthetic_revision',namespace,row['revision'],row);event(c,namespace,'positive_field_preview',actor,row['revision'],row['source_sha256'])
        return result

def list_documents():
    with db() as c:
        names=[r[0] for r in c.execute("select id from record where kind='synthetic_pointer' order by id")]
        result=[current(c,n) for n in names]
    for row in result:
        row['source_integrity']=verify(row) or 'unchanged'
        row['language_view_availability']={language:list(row['document']['views'].get(language,{})) for language in ['ar','en']}
    return result
def history(namespace):
    validate_namespace(namespace)
    with db() as c:return [json.loads(r[0]) for r in c.execute("select data from record where kind='synthetic_revision' and id=? order by cast(version as integer)",(namespace,))]
