"""Fail-closed guards for the isolated existing HR application process."""
from pathlib import Path
import ipaddress,json,os,socket,sys
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'state'
class IsolationViolation(RuntimeError):pass

def contained(value):
    path=Path(os.fsdecode(value)).resolve()
    if not path.is_relative_to(ROOT.resolve()):raise IsolationViolation('Staging write outside authorized candidate directory')
    if str(path).startswith('\\\\'):raise IsolationViolation('UNC writes forbidden')
    return path

def configuration():
    state={key:STATE/key for key in ['databases','uploads','assets','models','output','indexes','generations','jobs','temp']}
    state['logs']=ROOT/'logs'
    for p in state.values():contained(p).mkdir(parents=True,exist_ok=True)
    return state

def validate_settings(settings):
    for key in ['PATH_LOGS','PATH_DATA_ROOT','PATH_ASSETS_ROOT','PATH_MODELS_ROOT','PATH_OUTPUT_ROOT','SQLITE_DB_PATH']:
        contained(getattr(settings,key))
    if os.environ.get('TRAINING_SMTP_DISABLED')!='1' or os.environ.get('SMTP_DISABLED')!='1':raise IsolationViolation('Notifications must be disabled')
    if os.environ.get('FAWRY_ISOLATED_ADMIN')!='1':raise IsolationViolation('Explicit isolated startup required')
    return {'database':str(contained(settings.SQLITE_DB_PATH)),'write_paths_verified':True,'network':'loopback only','notifications':'disabled','background_maintenance':'disabled'}

def install_guards():
    """Covers Python file mutation, SQLite admission and network/subprocess I/O.

    The application also uses explicit isolated configuration and disables
    schedulers/seeding. Guards are defense in depth, not a complete OS sandbox.
    """
    def check_path(path):
        if isinstance(path,(str,bytes,os.PathLike)):contained(path)
    def audit(event,args):
        if event=='open':
            path,mode,flags=args
            if flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):check_path(path)
        elif event=='sqlite3.connect':
            target=args[0]
            if str(target)!=':memory:':check_path(target)
        elif event in {'os.remove','os.rmdir','os.mkdir','os.chmod','os.truncate'}:check_path(args[0])
        elif event in {'os.rename','os.replace','os.link','os.symlink'}:
            check_path(args[0]);check_path(args[1])
        elif event in {'subprocess.Popen','os.system','os.startfile','os.exec','os.posix_spawn'}:
            raise IsolationViolation('External process actions are disabled in staging web process')
    sys.addaudithook(audit)
    def allowed(host):
        if isinstance(host,bytes):host=host.decode('ascii')
        if host=='localhost':return True
        try:return ipaddress.ip_address(host).is_loopback
        except (ValueError,TypeError):return False
    getaddrinfo=socket.getaddrinfo
    def local_lookup(host,*args,**kwargs):
        if not allowed(host):raise IsolationViolation('Non-loopback network lookup denied')
        return getaddrinfo(host,*args,**kwargs)
    socket.getaddrinfo=local_lookup
    for method in ['connect','connect_ex','bind']:
        original=getattr(socket.socket,method)
        def wrapped(self,address,*args,_original=original,**kwargs):
            if not isinstance(address,tuple) or not allowed(address[0]):raise IsolationViolation('Non-loopback socket denied')
            return _original(self,address,*args,**kwargs)
        setattr(socket.socket,method,wrapped)
    original_sendto=socket.socket.sendto
    def local_sendto(self,data,*args):
        address=args[-1]
        if not isinstance(address,tuple) or not allowed(address[0]):raise IsolationViolation('Non-loopback datagram denied')
        return original_sendto(self,data,*args)
    socket.socket.sendto=local_sendto
