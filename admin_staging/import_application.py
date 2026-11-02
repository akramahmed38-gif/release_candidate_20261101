"""Read-only, resumable source import; never imports environment or production state."""
from pathlib import Path
import concurrent.futures,hashlib,json,os,re,time
ROOT=Path(__file__).resolve().parent
ORIGIN=Path(r'\\10.100.175.10\Projects\Production\FP Branches + Forms\HR Training App')
DEST=ROOT/'application'
SKIP={'__pycache__','node_modules','frotend','.git','backups','data','logs','output','uploads'}

def main():
 DEST.mkdir(exist_ok=True);manifest=ROOT/'IMPORTED_APPLICATION_MANIFEST.json';prior=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {};records={r['path']:r for r in prior.get('files',[])};errors=[];jobs=[]
 def error(err):errors.append({'kind':'discovery_error','path':str(err.filename),'error_type':type(err).__name__})
 for folder in ['src','chatbot','hr-training-frontend/src','hr-training-frontend/build','hr-training-frontend/public']:
  for base,dirs,files in os.walk(ORIGIN/folder,onerror=error,followlinks=False):
   dirs[:]=[d for d in dirs if d not in SKIP]
   for name in files:
    p=Path(base)/name
    if name.startswith('.env') or p.suffix.lower() in {'.db','.sqlite','.sqlite3','.pyc','.log','.bak'}:continue
    if folder in ['src','chatbot'] and p.suffix not in {'.py','.json'}:continue
    if p.suffix!='.py' and any(w in name.lower() for w in ['credential','secret','token']):continue
    jobs.append(p.relative_to(ORIGIN))
 for name in ['main.py','chatbot_sidecar.py','config.py','logger.py','normalization.py','ocr.py','vector_store.py','retriever.py','ingestion.py','hr-training-frontend/package.json','hr-training-frontend/package-lock.json','hr-training-frontend/vite.config.cjs','hr-training-frontend/index.html']:
  jobs.append(Path(name))
 def copy(rel):
  source=ORIGIN/rel
  for attempt in range(3):
   try:
    before=source.stat();data=source.read_bytes();after=source.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Source changed during copy')
    break
   except OSError:
    if attempt==2:raise
    time.sleep(.2)
  original=hashlib.sha256(data).hexdigest();changed=False
  if rel.as_posix()=='src/routes/users/auth_utils.py':
   s=data.decode('utf-8-sig');s,n=re.subn(r'^SECRET_KEY\s*=.*$','SECRET_KEY = os.environ["STAGING_JWT_SECRET"]',s,flags=re.M);assert n==1;data=s.encode('utf-8');changed=True
  staged=hashlib.sha256(data).hexdigest();target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():
   if hashlib.sha256(target.read_bytes()).hexdigest()!=staged:
    existing=records.get(rel.as_posix())
    if existing: return {**existing,'staging_edit_preserved':True}
    raise RuntimeError('Untracked destination edit; refusing overwrite')
  else:target.write_bytes(data)
  return {'path':rel.as_posix(),'original_sha256':original,'staged_sha256':staged,'source_size':after.st_size,'source_mtime_ns':after.st_mtime_ns,'staging_security_transform':changed}
 def save():
  manifest.write_text(json.dumps({'source':'existing HR application, read only','files':list(records.values()),'errors':errors,'complete':not errors and len(records)>=len(jobs),'excluded':['env','databases','uploads','logs','indexes','weights','node_modules','backups'],'production_modified':False},indent=2)+'\n',encoding='utf-8')
 print('discovered',len(jobs),'files',flush=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  future={pool.submit(copy,p):p for p in jobs}
  for i,f in enumerate(concurrent.futures.as_completed(future),1):
   rel=future[f]
   try:r=f.result();records[r['path']]=r
   except Exception as e:errors.append({'kind':'copy_error','path':rel.as_posix(),'error_type':type(e).__name__})
   if i%25==0:save();print('copied',len(records),'of',len(jobs),'errors',len(errors),flush=True)
 save();print('import result',len(records),'files','errors',errors,flush=True)
 if errors:raise SystemExit(1)
if __name__=='__main__':main()
