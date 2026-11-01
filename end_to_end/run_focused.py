"""Capture actual Python exit status, avoiding PowerShell stderr ambiguity."""
from pathlib import Path
import hashlib,json,re,subprocess,sys,time,uuid
ROOT=Path(__file__).resolve().parents[1]

def pins():
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}

def main():
    out=ROOT/'end_to_end'/('focused_'+uuid.uuid4().hex[:10]);out.mkdir();before=pins();start=time.perf_counter()
    with (out/'unittest.log').open('w',encoding='utf-8') as log:
        run=subprocess.run([sys.executable,'-B','-X','utf8','-m','unittest','discover','-s','end_to_end','-p','test_*.py'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    text=(out/'unittest.log').read_text(encoding='utf-8');count=re.findall(r'Ran (\d+) tests?',text)
    report={'python_exit_code':run.returncode,'tests':int(count[-1]) if count else None,'passed':run.returncode==0 and bool(re.search(r'^OK$',text,re.M)),'source_pins':before,'source_unchanged':before==pins(),'elapsed_ms':(time.perf_counter()-start)*1000,'runtime_source_commit':'e2322e06ae101477b1ebd1838559a29dfe01f3b0','native':'NOT RUN'}
    (out/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='source_pins'}))
    if not report['passed'] or not report['source_unchanged']:raise SystemExit(1)

if __name__=='__main__':main()
