"""Publish the tested simulation-only admin extension into a stopped candidate."""
from pathlib import Path
import ast,hashlib,json,shutil,uuid
ROOT=Path(__file__).resolve().parent
if (ROOT/'RUNNING.json').exists():raise SystemExit('Owned staging web process must be stopped')
names=['synthetic_store.py','synthetic_routes.py','catalog_store.py','knowledge_workspace.html','knowledge_workspace.js']
for name in names:
    path=ROOT/'next_revision'/name
    if path.suffix=='.py':ast.parse(path.read_text(encoding='utf-8'))
backup=ROOT/'state/revision_backups'/('synthetic_'+uuid.uuid4().hex[:10]);backup.mkdir(parents=True)
assert backup.resolve().is_relative_to(ROOT.resolve())
main=ROOT/'application/main.py';shutil.copy2(main,backup/'main.py')
for name in names:
    active=ROOT/name
    if active.exists():shutil.copy2(active,backup/name)
    shutil.copy2(ROOT/'next_revision'/name,active)
text=main.read_text(encoding='utf-8');needle='app.include_router(admin_knowledge_router)'
assert text.count(needle)==1 and 'from synthetic_routes import' not in text
text=text.replace(needle,needle+'\nfrom synthetic_routes import router as synthetic_workflow_router\napp.include_router(synthetic_workflow_router)')
ast.parse(text);main.write_text(text,encoding='utf-8')
receipt={'revision':'synthetic-lifecycle-v1','backup':str(backup),'files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names},'source_main_sha256':hashlib.sha256(main.read_bytes()).hexdigest(),'real_facts_modified':False,'real_approvals_granted':0,'production_changed':False}
(ROOT/'SYNTHETIC_REVISION.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps({'revision':receipt['revision'],'backup':str(backup)}))
