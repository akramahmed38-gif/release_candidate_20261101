import io,json,tempfile,unittest
from pathlib import Path
from staging_diagnostics import diagnostics
class Transport:
    def __init__(self,value):self.value=value;self.calls=[]
    def open(self,request,timeout):
        self.calls.append((request.full_url,timeout))
        if isinstance(self.value,Exception):raise self.value
        return io.StringIO(json.dumps(self.value))
class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'.private').mkdir()
        (self.root/'.private/engine.key').write_text('synthetic-secret',encoding='ascii')
        self.endpoint={'port':12345,'launch_id':'owned'}
        self.save()
    def save(self):
        (self.root/'.private/engine_endpoint.json').write_text(json.dumps(self.endpoint),encoding='utf-8')
    def test_owned_worker(self):
        t=Transport({'ready':True,'launch_id':'owned','backend':'Core_BM25'})
        r=diagnostics(self.root,t);self.assertTrue(r['worker_ready']);self.assertEqual(t.calls,[('http://127.0.0.1:12345/health',2)])
        self.assertEqual(r['native_acceptance'],'NOT RUN');self.assertFalse(r['qwen_serving'])
        self.assertNotIn('synthetic-secret',json.dumps(r));self.assertNotIn('owned',json.dumps(r))
    def test_wrong_launch(self):
        self.assertFalse(diagnostics(self.root,Transport({'ready':True,'launch_id':'other','backend':'Core_BM25'}))['worker_ready'])
    def test_missing_receipt(self):
        (self.root/'.private/engine_endpoint.json').unlink();t=Transport({})
        self.assertFalse(diagnostics(self.root,t)['worker_ready']);self.assertEqual(t.calls,[])
    def test_bad_endpoint_no_network(self):
        self.endpoint['port']='https://external';self.save();t=Transport({})
        self.assertFalse(diagnostics(self.root,t)['worker_ready']);self.assertEqual(t.calls,[])
    def test_transport_error_redacted(self):
        r=diagnostics(self.root,Transport(RuntimeError('synthetic-secret')))
        self.assertFalse(r['worker_ready']);self.assertNotIn('synthetic-secret',json.dumps(r))
    def test_other_backend_rejected(self):
        self.assertFalse(diagnostics(self.root,Transport({'ready':True,'launch_id':'owned','backend':'native'}))['worker_ready'])
if __name__=='__main__':unittest.main()
