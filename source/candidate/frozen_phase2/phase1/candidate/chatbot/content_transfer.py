"""Move verified extraction caches across machines, never databases or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
from contextlib import contextmanager
from types import SimpleNamespace


class DirectoryBundle:
    def __init__(self,path):self.root=Path(path).resolve()
    def path(self,name):
        if name!='manifest.json' and not re.fullmatch(r'(?:parts|ocr_cache)/[0-9a-f]{64}\.json',name):raise ValueError('Invalid cache entry path')
        target=(self.root/name).resolve()
        if self.root not in target.parents:raise ValueError('Cache entry escapes bundle')
        return target
    def read(self,name):return self.path(name).read_bytes()
    def getinfo(self,name):return SimpleNamespace(file_size=self.path(name).stat().st_size)


@contextmanager
def open_bundle(path):
    if Path(path).is_dir():yield DirectoryBundle(path)
    else:
        with zipfile.ZipFile(path) as archive:yield archive


def unpack_bundle(bundle,destination):
    """Use transparent JSON files when an archive transfer is unavailable."""
    destination=Path(destination)
    with zipfile.ZipFile(bundle) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        files={}
        for entry in manifest['entries']:
            name=entry['path']
            if not re.fullmatch(r'(?:parts|ocr_cache)/[0-9a-f]{64}\.json',name):raise ValueError('Invalid entry')
            data=archive.read(name)
            if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Checksum mismatch')
            files[name]=data
        for name,data in files.items():
            target=destination/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(data)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=hashlib.sha256(data).hexdigest():raise ValueError('Transfer verification failed')
        destination.mkdir(parents=True,exist_ok=True)
        (destination/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return {'cache_files':len(files),'format':'verified_json_directory','production_activated':False}

from .content_catalog import discover_content, content_hash
from .content_preparation import extraction_cache_version
from .content_sync import SyncLock


def export_cache(root, prepared, destination):
    root,prepared,destination=Path(root),Path(prepared),Path(destination)
    files,_=discover_content(root)
    entries=[];sources=[]
    destination.parent.mkdir(parents=True,exist_ok=True)
    pending=destination.with_name(destination.name+'.pending')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as archive:
        for source in files:
            digest=content_hash(root/source.path)
            key=hashlib.sha256((extraction_cache_version(Path(source.path).suffix)+source.path+digest).encode()).hexdigest()
            part='parts/'+key+'.json'
            if not (prepared/part).exists():continue
            data=(prepared/part).read_bytes()
            chunks=json.loads(data)
            if not isinstance(chunks,list) or not chunks:continue
            archive.writestr(part,data)
            entries.append({'path':part,'sha256':hashlib.sha256(data).hexdigest()})
            sources.append({'path':source.path,'sha256':digest,'part':part})
        for path in sorted((prepared/'ocr_cache').glob('*.json')):
            if not re.fullmatch(r'[0-9a-f]{64}\.json',path.name):continue
            data=path.read_bytes();json.loads(data)
            name='ocr_cache/'+path.name;archive.writestr(name,data)
            entries.append({'path':name,'sha256':hashlib.sha256(data).hexdigest()})
        manifest={'format':'learning-extraction-cache-v1','source_files':sources,'entries':entries,
                  'account_database_included':False,'native_index_included':False}
        archive.writestr('manifest.json',json.dumps(manifest))
    pending.replace(destination)
    return {'cached_source_files':len(sources),'cache_files':len(entries),'bundle_bytes':destination.stat().st_size,
            'production_activated':False,'native_index_included':False}


def import_cache(root, bundle):
    root=Path(root).resolve();bundle=Path(bundle)
    if str(root).startswith('\\\\'):raise ValueError('Import must use the server local path')
    prepared=root/'data/chatbot_content/prepared'
    if root not in prepared.resolve().parents:raise ValueError('Cache path escapes application directory')
    files,_=discover_content(root);current={source.path:source for source in files}
    imported=skipped=0
    with SyncLock(root/'data/chatbot_content/sync.lock'),open_bundle(bundle) as archive:
        if archive.getinfo('manifest.json').file_size>8*1024*1024:raise ValueError('Manifest too large')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('format')!='learning-extraction-cache-v1':raise ValueError('Unsupported bundle')
        if len(manifest['entries'])>50000:raise ValueError('Too many cache entries')
        if sum(archive.getinfo(entry['path']).file_size for entry in manifest['entries'])>512*1024*1024:raise ValueError('Cache bundle too large')
        verified={}
        for entry in manifest['entries']:
            name=entry['path']
            if not re.fullmatch(r'(?:parts|ocr_cache)/[0-9a-f]{64}\.json',name):raise ValueError('Invalid cache entry path')
            if name in verified or archive.getinfo(name).file_size>32*1024*1024:raise ValueError('Invalid cache entry')
            data=archive.read(name)
            if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Cache checksum mismatch')
            json.loads(data);verified[name]=data
        # Validate the entire archive before writing any cache file.
        allowed={name for name in verified if name.startswith('ocr_cache/')}
        for source in manifest['source_files']:
            actual=current.get(source['path'])
            if actual is None or content_hash(root/actual.path)!=source['sha256']:
                skipped+=1;continue
            key=hashlib.sha256((extraction_cache_version(Path(actual.path).suffix)+actual.path+source['sha256']).encode()).hexdigest()
            expected='parts/'+key+'.json'
            if source['part']!=expected or expected not in verified:raise ValueError('Cache/source identity mismatch')
            allowed.add(expected);imported+=1
        for name in allowed:
            target=prepared/name
            if prepared.resolve() not in target.resolve().parents:raise ValueError('Cache destination escapes prepared directory')
            target.parent.mkdir(parents=True,exist_ok=True)
            pending=target.with_name(target.name+'.import.pending')
            pending.write_bytes(verified[name]);pending.replace(target)
    return {'reused_source_files':imported,'changed_or_removed_files_skipped':skipped,
            'production_activated':False,'source_files_changed':False,'native_index_built':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['export','import'])
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--prepared',type=Path);args=parser.parse_args()
    try:
        if args.mode=='export' and args.prepared is None:raise ValueError('Prepared cache path required')
        result=export_cache(args.root,args.prepared,args.bundle) if args.mode=='export' else import_cache(args.root,args.bundle)
        print(json.dumps(result,indent=2))
    except Exception as exc:
        print(json.dumps({'status':'cache_transfer_failed','error_type':type(exc).__name__}))
        raise SystemExit(1)
