"""Start only our private worker; browser requests cannot spawn processes."""
from pathlib import Path
import atexit,json,os,secrets,subprocess,sys,time,uuid
ROOT=Path(__file__).resolve().parent

def start():
    private=ROOT/'.private';private.mkdir(exist_ok=True)
    key=private/'engine.key'
    if not key.exists():key.write_text(secrets.token_urlsafe(48),encoding='ascii')
    endpoint=private/'engine_endpoint.json';endpoint.unlink(missing_ok=True)
    log=(ROOT/'logs/engine.log').open('ab')
    launch_id=uuid.uuid4().hex
    child=subprocess.Popen([sys.executable,'-u','-B','-X','utf8',str(ROOT/'engine_worker.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'STAGING_ENGINE_LAUNCH_ID':launch_id},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    until=time.monotonic()+60
    while time.monotonic()<until:
        if child.poll() is not None:log.close();raise RuntimeError('Owned isolated worker initialization failed; inspect private log')
        if endpoint.exists():
            value=json.loads(endpoint.read_text(encoding='utf-8'))
            # Windows virtual-environment Python may use a launcher parent.
            # Require this launch receipt and our process or immediate child.
            if value.get('launch_id')==launch_id and child.pid in {value['pid'],value.get('parent_pid')}:
                atexit.register(stop,child,log)
                return child,log
        time.sleep(.2)
    child.terminate();child.wait(timeout=10);log.close();raise RuntimeError('Owned worker startup timeout')

def stop(child,log):
    if child.poll() is None:child.terminate();child.wait(timeout=10)
    log.close()
