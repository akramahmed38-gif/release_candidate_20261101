"""Actual runtime/audit-hook integration in a disposable staging subtree."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,runpy,sqlite3,sys,uuid
from contextlib import redirect_stdout
STAGE=Path(__file__).resolve().parent;ROOT=STAGE.parent
sys.path.insert(0,str(STAGE))
import catalog_store,synthetic_store as store,synthetic_restore as restore

def main():
    candidate=STAGE/'isolation.py'
    spec=importlib.util.spec_from_file_location('candidate_isolation',candidate);guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    # Match the actual web process's root and working directory. No live web
    # module/global is changed; this is a new test process.
    guard.ROOT=STAGE;os.chdir(STAGE/'application')
    out=STAGE/'state'/('guarded_restore_'+uuid.uuid4().hex[:10]);out.mkdir()
    catalog_store.DB=out/'knowledge.sqlite';store.UPLOADS=out/'uploads';restore.RESTORES=out/'restore_drills'
    outside=ROOT/'environment_validation'/('outside_uri_'+uuid.uuid4().hex+'.sqlite')
    with sqlite3.connect(outside) as c:c.execute('create table disposable (value integer)')
    checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    guard.install_guards();failure=None
    try:
        raw=json.dumps({'title':'SYNTHETIC guarded restore','fields':{'marker':'SYN-GUARDED'},'views':{'en':{'marker':'SYN-GUARDED'}}}).encode()
        ns=store.new_revision(raw,'synthetic-guarded-restore')['namespace']
        for action in ['submit','simulate_fidelity','simulate_currentness','publish_simulation']:store.transition(ns,action,'synthetic-guarded-restore')
        check('Working positive control under process guards',store.preview(ns,'marker','en','synthetic-guarded-restore')['complete'])
        actual=restore.drill(ns,'marker','en','synthetic-guarded-restore')
        check('Full synthetic restore under actual audit guards',actual['passed'])
        try:
            sqlite3.connect(outside.as_uri()+'?mode=ro',uri=True).close();denied=False
        except guard.IsolationViolation:denied=True
        check('Outside SQLite URI denied even read-only',denied)
        encoded=outside.as_uri().replace('outside_uri_','%6futside_uri_')+'?mode=ro'
        try:sqlite3.connect(encoded,uri=True).close();denied=False
        except guard.IsolationViolation:denied=True
        check('Percent-encoded outside SQLite URI denied',denied)
        try:sqlite3.connect('file://remote.invalid/share/test.sqlite?mode=ro',uri=True).close();denied=False
        except guard.IsolationViolation:denied=True
        check('Non-local authority denied',denied)
        with sqlite3.connect(catalog_store.DB.as_uri()+'?mode=ro',uri=True) as c:
            check('Private URI opens actual local database',c.execute('select count(*) from record').fetchone()[0]>0)
        sys.modules['isolation']=guard
        stream=io.StringIO()
        with redirect_stdout(stream):
            try:runpy.run_path(str(STAGE/'check_isolation.py'),run_name='__main__')
            except SystemExit as exc:
                if exc.code not in (None,0):raise RuntimeError('Preserved isolation checks failed')
        baseline=json.loads(stream.getvalue().strip())
        checks.extend({'name':'preserved_'+r['test'],'passed':r['passed']} for r in baseline)
    except Exception as exc:failure={'type':type(exc).__name__,'message':str(exc)[:250]}
    result={'scope':'Python runtime plus actual staging audit-hook integration; not production/native acceptance',
            'python_version':sys.version,'passed':sum(c['passed'] for c in checks),'total':len(checks),'checks':checks,
            'execution_failure':failure,'candidate_guard_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
            'production_changed':False,'outside_disposable_fixture':str(outside)}
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    (STAGE/'GUARDED_RESTORE_LATEST.json').write_text(json.dumps({'path':str(out)}),encoding='utf8')
    print(json.dumps(result));print(str(out))
    if failure:raise SystemExit(1)

if __name__=='__main__':main()
