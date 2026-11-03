"""Publish one local admin revision after its owning web process is stopped."""
from pathlib import Path
import ast,hashlib,json,shutil,time,uuid
ROOT=Path(__file__).resolve().parent
if (ROOT/'RUNNING.json').exists():raise SystemExit('Stop owned staging application first')
names=['admin_knowledge.py','catalog_queries.py','source_preview.py','engine_worker.py','knowledge_workspace.html','knowledge_workspace.js']
for name in names:
    path=ROOT/'next_revision'/name
    if path.suffix=='.py':ast.parse(path.read_text(encoding='utf-8'))
backup=ROOT/'state/revision_backups'/('catalog_'+uuid.uuid4().hex[:10]);backup.mkdir(parents=True)
assert backup.resolve().is_relative_to(ROOT.resolve())
before={}
for name in names:
    active=ROOT/name
    if active.exists():before[name]=hashlib.sha256(active.read_bytes()).hexdigest();shutil.copy2(active,backup/name)
    shutil.copy2(ROOT/'next_revision'/name,active)
receipt={'revision':'catalog-source-preview-v2','backup':str(backup),'before_sha256':before,'after_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},'production_changed':False,'sources_changed':False,'business_approvals_granted':0}
(ROOT/'CATALOG_REVISION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps({'revision':receipt['revision'],'backup':str(backup)}))
