from pathlib import Path
import ast,hashlib,json,zipfile,shutil
ROOT=Path(__file__).resolve().parent
dest=Path(r'\\10.100.175.10\Projects\Production\FP Branches + Forms\HR Training App\maintenance\chatbot_multi_source_20261027')
files=[p for p in ROOT.rglob('*') if p.is_file() and not any(part in ['runs','__pycache__','native_results'] for part in p.relative_to(ROOT).parts) and p.name not in ['PACKAGE_PINS.json','PHASE2_PACKAGE.zip','run_multi_source_pilot.ps1'] and not p.suffix=='.pyc']
for p in files:
    if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'),feature_version=(3,10))
bundle=ROOT/'PHASE2_PACKAGE.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
    for p in files:archive.write(p,p.relative_to(ROOT).as_posix())
digest=hashlib.sha256(bundle.read_bytes()).hexdigest()
launcher=ROOT/'run_multi_source_pilot.ps1';text=launcher.read_text(encoding='utf-8')
if '# BUNDLE_BOOTSTRAP' in text:raise ValueError('Already staged; preserve package identity')
bootstrap="""
# BUNDLE_BOOTSTRAP
if (-not (Test-Path -LiteralPath (Join-Path $package 'run_phase2.py'))) {
    $bundle = Join-Path $package 'PHASE2_PACKAGE.zip'
    if ((Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'BUNDLE_HASH') { throw 'Isolated bundle fingerprint mismatch.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($bundle, $package)
}
""".replace('BUNDLE_HASH',digest)
text=text.replace('$package = $PSScriptRoot','$package = $PSScriptRoot\n'+bootstrap)
launcher.write_text(text,encoding='utf-8')
pins={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files+[launcher]}
(ROOT/'PACKAGE_PINS.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
dest.mkdir(parents=True,exist_ok=False)
for p in [bundle,launcher,ROOT/'PACKAGE_PINS.json']:
    shutil.copy2(p,dest/p.name)
    assert hashlib.sha256((dest/p.name).read_bytes()).hexdigest()==hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'staged':str(dest),'pinned_files':len(pins),'bundle_sha256':digest,'three_staged_files_hash_verified':True,'runtime_files_changed':False}))
