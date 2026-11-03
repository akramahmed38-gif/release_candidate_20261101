"""Read-only diagnostics for the owned worker; no process/model startup."""
from pathlib import Path
import json
from urllib.request import Request, build_opener, ProxyHandler
ROOT=Path(__file__).resolve().parent

def diagnostics(root=ROOT, opener=None):
    result={'environment':'isolated_admin_staging','backend':'Core_BM25','worker_ready':False,
            'native_acceptance':'NOT RUN','bge_m3_executed':False,'chroma_executed':False,
            'qwen_serving':False,'approvals_granted':0,'employee_access':False}
    try:
        endpoint=json.loads((root/'.private/engine_endpoint.json').read_text(encoding='utf-8'))
        port=endpoint['port']
        if type(port) is not int or not 1024<=port<=65535:raise ValueError('Invalid endpoint')
        key=(root/'.private/engine.key').read_text(encoding='ascii')
        request=Request(f'http://127.0.0.1:{port}/health',headers={'Authorization':'Bearer '+key})
        transport=opener or build_opener(ProxyHandler({}))
        with transport.open(request,timeout=2) as response:health=json.load(response)
        if health.get('launch_id')!=endpoint.get('launch_id') or not health.get('ready') or health.get('backend')!='Core_BM25':raise ValueError('Worker identity mismatch')
        result['worker_ready']=True
    except Exception:
        result['error']='Owned staging worker unavailable or identity unverified; no startup attempted'
    return result
