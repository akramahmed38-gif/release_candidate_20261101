"""Bounded restore drill for one synthetic knowledge namespace.

No identities, credentials, real policy, production indexes or historical backup
are copied. This proves a knowledge-state boundary, not whole-app recovery.
"""
from pathlib import Path
from contextlib import closing
import hashlib,json,shutil,sqlite3,uuid
import synthetic_store as store

ROOT=Path(__file__).resolve().parent
RESTORES=ROOT/'state/restore_drills'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def contained(path,base):
    result=Path(path).resolve()
    if not result.is_relative_to(Path(base).resolve()):raise store.WorkflowError('Restore path escaped disposable storage')
    return result

def initialize(path):
    with closing(sqlite3.connect(path)) as c:
        c.execute('create table record(kind text,id text,version text,data text,primary key(kind,id,version))')
        c.commit()

def restored_row(destination,namespace):
    database=contained(Path(destination)/'knowledge.sqlite',RESTORES)
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('pragma query_only=on')
        pointer=c.execute("select data from record where kind='synthetic_pointer' and id=? and version='active'",(namespace,)).fetchone()
        if pointer is None:raise store.WorkflowError('Restored active revision unavailable')
        revision=json.loads(pointer[0])['revision']
        row=c.execute("select data from record where kind='synthetic_revision' and id=? and version=?",(namespace,str(revision))).fetchone()
        if row is None:raise store.WorkflowError('Restored source revision unavailable')
        value=json.loads(row[0])
    if value.get('namespace')!=namespace or value.get('normal_runtime_eligible') is not False or value.get('real_approvals')!=0 or value.get('simulated') is not True:
        raise store.WorkflowError('Restore must remain synthetic and ineligible for real policy')
    return value

def restore_bundle(bundle,destination):
    """Verify all bytes before creating a NEW disposable target."""
    bundle=contained(bundle,RESTORES);destination=contained(destination,RESTORES)
    if destination.exists():raise store.WorkflowError('Restore target must be new')
    manifest=json.loads((bundle/'MANIFEST.json').read_text(encoding='utf8'))
    if manifest.get('scope')!='synthetic_knowledge_namespace' or manifest.get('normal_runtime_eligible') is not False:
        raise store.WorkflowError('Unsupported restore bundle')
    namespace=manifest['namespace'];store.validate_namespace(namespace)
    files=manifest['files']
    if not isinstance(files,dict) or not 2<=len(files)<=33 or 'knowledge.sqlite' not in files:
        raise store.WorkflowError('Bounded database/source manifest required')
    for relative,expected in files.items():
        p=Path(relative)
        if p.is_absolute() or '..' in p.parts or (relative!='knowledge.sqlite' and not relative.startswith('uploads/'+namespace+'/')):
            raise store.WorkflowError('Unrecognized restore member')
        source=contained(bundle/p,bundle)
        if not source.is_file() or sha(source.read_bytes())!=expected:raise store.WorkflowError('Restore manifest hash mismatch')
    with closing(sqlite3.connect((bundle/'knowledge.sqlite').as_uri()+'?mode=ro',uri=True)) as c:
        c.execute('pragma query_only=on')
        if c.execute('pragma integrity_check').fetchone()[0]!='ok':raise store.WorkflowError('Snapshot database integrity failed')
        if c.execute("select count(*) from record where kind not in ('synthetic_revision','synthetic_pointer') or id!=?",(namespace,)).fetchone()[0]:
            raise store.WorkflowError('Snapshot contains nonsynthetic records')
    destination.mkdir(parents=True,exist_ok=False)
    for relative,expected in files.items():
        target=contained(destination/relative,destination);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(bundle/relative,target)
        if sha(target.read_bytes())!=expected:raise store.WorkflowError('Restored member hash mismatch')
    row=restored_row(destination,namespace)
    if row['revision']!=manifest.get('active_revision'):raise store.WorkflowError('Restored generation pointer differs from manifest')
    if store.verify(row,destination/'uploads'):raise store.WorkflowError('Restored source/view binding invalid')
    return row

def drill(namespace,field,language,actor):
    store.validate_namespace(namespace)
    if not RESTORES.resolve().is_relative_to(ROOT.resolve()):raise store.WorkflowError('Disposable restore root is outside staging')
    RESTORES.mkdir(parents=True,exist_ok=True)
    identity='restore-'+uuid.uuid4().hex;work=RESTORES/identity;bundle=work/'bundle';bundle.mkdir(parents=True,exist_ok=False)
    with store.db() as source:
        source.execute('BEGIN IMMEDIATE')
        active=store.current(source,namespace)
        positive=store.evaluate_preview(active,field,language)
        if not active.get('positive_control') or not positive['complete']:
            raise store.WorkflowError('First obtain a working positive preview of this exact simulated revision')
        rows=source.execute("select kind,id,version,data from record where id=? and kind in ('synthetic_pointer','synthetic_revision')",(namespace,)).fetchall()
        revisions=[json.loads(row[3]) for row in rows if row[0]=='synthetic_revision']
        if not 1<=len(revisions)<=32:raise store.WorkflowError('Use at most32 synthetic revisions for this bounded drill')
        initialize(bundle/'knowledge.sqlite')
        with closing(sqlite3.connect(bundle/'knowledge.sqlite')) as target:
            target.executemany('insert into record values(?,?,?,?)',[tuple(row) for row in rows]);target.commit()
        files={'knowledge.sqlite':sha((bundle/'knowledge.sqlite').read_bytes())}
        for row in revisions:
            if row.get('normal_runtime_eligible') is not False or row.get('real_approvals')!=0 or row.get('simulated') is not True:
                raise store.WorkflowError('Only synthetic revisions can enter the restore bundle')
            if store.verify(row):raise store.WorkflowError('All snapshotted synthetic source revisions must be intact')
            raw=store.source_path(row).read_bytes()
            if sha(raw)!=row['source_sha256']:raise store.WorkflowError('Source changed during snapshot')
            relative='uploads/'+namespace+'/'+str(row['revision'])+'.json';p=bundle/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            files[relative]=sha(raw)
    manifest={'scope':'synthetic_knowledge_namespace','namespace':namespace,'active_revision':active['revision'],
              'normal_runtime_eligible':False,'real_approvals':0,'files':files,
              'credentials_included':False,'production_or_native_index_included':False}
    (bundle/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    destination=work/'restored';row=restore_bundle(bundle,destination)
    restored=store.evaluate_preview(row,field,language,destination/'uploads')
    same=restored['complete'] and restored['citations']==positive['citations'] and restored['answer']==positive['answer']
    if not same:raise store.WorkflowError('Restored answer or original source binding differs')
    # Revoke ONLY the restored copy, after its working positive control.
    row['state']='revoked'
    with closing(sqlite3.connect(destination/'knowledge.sqlite')) as c:
        c.execute("update record set data=? where kind='synthetic_revision' and id=? and version=?",(json.dumps(row),namespace,str(row['revision'])));c.commit()
    revoked=store.evaluate_preview(restored_row(destination,namespace),field,language,destination/'uploads')
    original=store.preview(namespace,field,language,actor)
    passed=(not revoked['complete'] and not revoked['citations'] and original['complete'] and original['citations']==positive['citations'])
    receipt={'drill_id':identity,'scope':'synthetic_knowledge_namespace_only','namespace':namespace,'revision':active['revision'],
             'source_sha256':active['source_sha256'],'passed':passed,'snapshot_restore_positive_match':bool(same),
             'restored_revocation_holds':not revoked['complete'],'original_namespace_still_complete':original['complete'],
             'positive':positive,'restored':restored,'revoked_copy':revoked,'original_after':original,
             'normal_runtime_eligible':False,'real_policy_approvals':0,'whole_application_restore_proven':False,
             'identity_or_native_index_restore_proven':False,'historical_backup_touched':False,
             'cleanup_manifest':[p.relative_to(ROOT).as_posix() for p in work.rglob('*') if p.is_file()]}
    (work/'RESULTS.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf8')
    with store.db() as c:store.event(c,namespace,'restore_drill',actor,active['revision'],active['source_sha256'],identity)
    return receipt
