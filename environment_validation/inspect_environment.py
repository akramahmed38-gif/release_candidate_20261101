"""Read-only workstation prerequisites; never launches production or inference."""
from pathlib import Path
import hashlib,importlib.metadata,json,os,platform,sys,time
ROOT=Path(__file__).resolve().parents[1]

def main():
    packages={}
    for name in ['chromadb','numpy','requests','fastapi','uvicorn','psutil','playwright']:
        try:packages[name]={'installed':True,'version':importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:packages[name]={'installed':False}
    source=json.loads((ROOT/'evidence/I046_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    matches=[]
    for old,digest in source['files'].items():
        path=ROOT/'source'/old
        matches.append({'path':str(path.relative_to(ROOT)),'matches_i046':hashlib.sha256(path.read_bytes()).hexdigest()==digest})
    resources={}
    try:
        import psutil
        vm=psutil.virtual_memory();resources={'whole_workstation_ram_bytes':vm.total,'available_bytes':vm.available,'cpu_logical':psutil.cpu_count(),'attributable_native_model_ram':'NOT MEASURED'}
    except ImportError:resources={'status':'psutil unavailable; no RAM claim'}
    report={'host':platform.node(),'os':platform.platform(),'python':sys.version,'executable':sys.executable,'packages':packages,'resources':resources,'source_identity':matches,'all_i046_candidate_bytes_match':all(x['matches_i046'] for x in matches),'native_server_execution':'BLOCKED_NOT_RUN','unc_is_not_server_execution':True,'model_calls':0,'production_started':False,'employee_access_authorized':False}
    output=ROOT/'environment_validation'/('WORKSTATION_'+time.strftime('%Y%m%d_%H%M%S')+'.json')
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps({'report':str(output),'all_i046_candidate_bytes_match':report['all_i046_candidate_bytes_match'],'native':'BLOCKED_NOT_RUN'}))

if __name__=='__main__':main()
