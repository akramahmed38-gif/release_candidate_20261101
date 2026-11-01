"""Hash-pinned diagnostic bundle; not a native acceptance or deployment receipt."""
from pathlib import Path
import ast,hashlib,json,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    original=json.loads((ROOT/'evidence/I046_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for name,digest in original['files'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise RuntimeError('I046 source identity changed: '+name)
    definition=json.loads((ROOT/'source/candidate/fixture_data/definition.json').read_text(encoding='utf-8'))
    assert len(definition['facts'])==21
    assert all(f.get(k) is False for f in definition['facts'] for k in ['normal_runtime_eligible','human_fidelity_approved','business_approved'])
    files=[p for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [ROOT/'native_packages/native_smoke.py',ROOT/'native_packages/README.md']
    for p in files:
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'),feature_version=(3,10))
    pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest={'release_commit':commit,'historical_candidate':'8e2faa3','native_status':'BLOCKED_NOT_RUN','employee_access':False,'diagnostic_only':True,'files':pins}
    (ROOT/'native_packages/SOURCE_PINS.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    files.append(ROOT/'native_packages/SOURCE_PINS.json')
    out=ROOT/'native_packages'/('RC_DIAGNOSTIC_'+commit[:12]+'.zip')
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    receipt={'archive':out.name,'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'file_count':len(files),'source_commit':commit,'native_executed':False,'static_python310_parse':'PASS','fixtures_production_eligible':False}
    (out.with_suffix('.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt))

if __name__=='__main__':main()
