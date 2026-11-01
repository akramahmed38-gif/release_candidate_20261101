"""Same admission thresholds/deadline/backoff; optional minimum sampling window."""
import ctypes,time
class ObservedBudget:
    def __init__(self,stable_window=False,sample=None,sleep=None,clock=None):
        self.stable_window=stable_window;self.sample=sample or windows_sample
        self.sleep=sleep or time.sleep;self.clock=clock or time.monotonic
        self.previous=self.sample();self.events=[]
    def wait(self):
        self.events=[];deadline=self.clock()+15
        while True:
            if self.stable_window:
                age=self.clock()-self.previous['at']
                if age<.2:
                    delay=.2-age
                    self.events.append({'reason':'minimum_sampling_window','sleep_seconds':delay,'sample_interval_seconds':age})
                    self.sleep(delay)
            now=self.sample();before=self.previous;self.previous=now
            delta=now['total']-before['total'];idle=now['idle']-before['idle']
            cpu=1-idle/delta if delta>0 else None
            memory_ok=now['available']>=max(1024**3,now['physical']*.10)
            reason='admitted' if memory_ok and cpu is not None and cpu<.70 else 'memory_low' if not memory_ok else 'no_cpu_delta' if cpu is None else 'cpu_high'
            event={'reason':reason,'sample_interval_seconds':now['at']-before['at'],'cpu_fraction':cpu,'available_bytes':now['available'],'required_available_bytes':max(1024**3,now['physical']*.10),'cpu_delta':delta,'idle_delta':idle,'sleep_seconds':0}
            self.events.append(event)
            if reason=='admitted':return
            if self.clock()>deadline:raise RuntimeError('ResourceBudgetUnavailable')
            event['sleep_seconds']=1;self.sleep(1)

def windows_sample():
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD),*[(name,ctypes.c_ulonglong) for name in ('total_phys','available_phys','total_page','available_page','total_virtual','available_virtual','extended')]]
    memory=Memory();memory.length=ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise RuntimeError('Memory monitor unavailable')
    idle,kernel,user=wintypes.FILETIME(),wintypes.FILETIME(),wintypes.FILETIME()
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle),ctypes.byref(kernel),ctypes.byref(user)):raise RuntimeError('CPU monitor unavailable')
    number=lambda x:(x.dwHighDateTime<<32)|x.dwLowDateTime
    return {'at':time.monotonic(),'idle':number(idle),'total':number(kernel)+number(user),'available':memory.available_phys,'physical':memory.total_phys}
