from pathlib import Path
from contextlib import closing
import ctypes,hashlib,shutil,sqlite3,time


class SourceSnapshotChanged(RuntimeError):pass
class ResourceBudgetUnavailable(RuntimeError):pass


def require_local_model(config):
    from urllib.parse import urlsplit
    target=urlsplit(config.ollama_url)
    if target.scheme not in ('http','https') or target.hostname not in ('127.0.0.1','localhost','::1') or target.username is not None or target.password is not None or target.query or target.fragment or target.path not in ('','/'):
        raise RuntimeError('Isolated model checks require a credential-free loopback endpoint')


def verify_catalog_snapshot(app,manifest):
    from chatbot.content_catalog import discover_content,read_vocabulary,vocabulary_hash
    files,_=discover_content(app)
    current={r.path:(r.size,r.mtime_ns) for r in files}
    expected={r['path']:(r['size'],r['mtime_ns']) for r in manifest['files']}
    if current!=expected:raise SourceSnapshotChanged('Learning catalog changed during isolated validation')
    if vocabulary_hash(read_vocabulary(Path(app).parent/'databases/hr_learning_system.db'))!=manifest['vocabulary_hash']:
        raise SourceSnapshotChanged('Vocabulary changed during isolated validation')

class RepairCheckFailed(ValueError):pass

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def reconcile_catalog(app,previous,current):
    """A timestamp change is not a content change; verify bytes before refreshing metadata."""
    old={r['path']:r for r in previous};now={r.path:r for r in current}
    if set(old)-set(now):raise RepairCheckFailed('Removed baseline learning files require a targeted rebase')
    pending_additions=sorted(set(now)-set(old))
    normalized=[];metadata_only=[]
    for relative,row in old.items():
        actual=now[relative];updated=dict(row)
        if (row['size'],row['mtime_ns'])!=(actual.size,actual.mtime_ns):
            path=(app/relative).resolve();path.relative_to(app.resolve())
            if sha(path)!=row['sha256']:raise RepairCheckFailed('A library content version changed; targeted rebase is required')
            updated.update(size=actual.size,mtime_ns=actual.mtime_ns)
            metadata_only.append(relative)
        normalized.append(updated)
    return normalized,metadata_only,pending_additions

class CpuBudget:
    def __init__(self):self.previous=None
    def wait(self):
        from ctypes import wintypes
        class Memory(ctypes.Structure):
            _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD),*[(name,ctypes.c_ulonglong) for name in
                ('total_phys','available_phys','total_page','available_page','total_virtual','available_virtual','extended')]]
        deadline=time.monotonic()+15
        while True:
            memory=Memory();memory.length=ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise RuntimeError('Memory monitoring unavailable')
            memory_available=memory.available_phys>=max(1024**3,memory.total_phys*.10)
            idle,kernel,user=wintypes.FILETIME(),wintypes.FILETIME(),wintypes.FILETIME()
            if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):raise RuntimeError('Resource monitoring unavailable')
            number=lambda x:(x.dwHighDateTime<<32)|x.dwLowDateTime
            now=(number(idle),number(kernel)+number(user));previous=self.previous;self.previous=now
            if memory_available and previous and now[1]>previous[1] and 1-(now[0]-previous[0])/(now[1]-previous[1])<.70:return
            if time.monotonic()>deadline:raise ResourceBudgetUnavailable('Shared CPU or memory budget is unavailable')
            time.sleep(.2 if previous is None else 1)

def snapshot_native_chroma(source,target,collection):
    """SQLite backup plus the selected immutable HNSW segments; no vector rebuilding."""
    source=Path(source).resolve();target=Path(target).resolve();target.mkdir(parents=True,exist_ok=False)
    database=source/'chroma.sqlite3'
    connection=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        connection.execute('PRAGMA query_only=ON')
        before=connection.execute('PRAGMA data_version').fetchone()[0]
        identifiers=connection.execute('SELECT id FROM collections WHERE name=?',(collection,)).fetchall()
        if len(identifiers)!=1:raise RepairCheckFailed('Base collection identity is ambiguous or missing')
        segments=[str(r[0]) for r in connection.execute('SELECT id FROM segments WHERE collection=?',(identifiers[0][0],))]
        with closing(sqlite3.connect(target/'chroma.sqlite3')) as destination:connection.backup(destination)
        copied=0
        for segment in segments:
            folder=(source/segment).resolve();folder.relative_to(source)
            if not folder.is_dir():continue
            for file in folder.rglob('*'):
                if not file.is_file():continue
                file.resolve().relative_to(source)
                before_hash=sha(file);out=target/file.relative_to(source);out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(file,out)
                if sha(out)!=before_hash or sha(file)!=before_hash:raise RepairCheckFailed('Base index changed during snapshot')
                copied+=1
        if connection.execute('PRAGMA data_version').fetchone()[0]!=before:raise RepairCheckFailed('Index writer changed the snapshot source')
        return {'hnsw_files_copied':copied,'vector_rebuilding':False}
    finally:connection.close()
