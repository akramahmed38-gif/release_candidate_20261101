"""One low-priority, resumable refresh; no credentials or portal restarts."""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import time

from .content_catalog import catalog_signature, discover_content, read_vocabulary, vocabulary_hash
from .content_preparation import ContentPreparer, EXTRACTOR_VERSION,preparation_signature
from .content_state import atomic_json, publish_generation, read_active_generation, source_changes


class SyncAlreadyRunning(Exception):pass


class SyncLock:
    def __init__(self,path):self.path,self.stream=Path(path),None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.stream=self.path.open('a+b')
        if not self.path.stat().st_size:self.stream.write(b'0');self.stream.flush()
        self.stream.seek(0)
        try:
            import os
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.stream.close();self.stream=None
            raise SyncAlreadyRunning()
        return self
    def __exit__(self,*args):
        if self.stream:self.stream.close()


def refresh_stale_catalog(root, database=None):
    """Short independent scan, also runs while a long extraction is in progress."""
    root=Path(root);state=root/'data/chatbot_content'
    database=Path(database or root.parent/'databases/hr_learning_system.db')
    with SyncLock(state/'stale.lock'):
        active=read_active_generation(root)
        if not active:return
        files,_=discover_content(root)
        changes=source_changes(active[2],files,vocabulary_hash(read_vocabulary(database)))
        changed=set(changes['deleted']+changes['changed'])
        if not changed and not changes['vocabulary_changed']:return
        path=state/'stale_sources.json'
        value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        blocked=value.setdefault('blocked_generations',{})
        blocked.setdefault(active[0],{'paths':[],'vocabulary_stale':False})
        for entry in blocked.values():
            entry['paths']=sorted(set(entry.get('paths',[]))|changed)
            entry['vocabulary_stale']=bool(entry.get('vocabulary_stale') or changes['vocabulary_changed'])
        atomic_json(path,{**value,'blocked_generations':blocked})


def run_once(root, database=None, builder=None, preparer=None):
    import hashlib
    root=Path(root)
    database=Path(database or root.parent/'databases/hr_learning_system.db')
    state=root/'data/chatbot_content'
    if not root.is_dir():raise ValueError('Project root unavailable')
    with SyncLock(state/'sync.lock'):
        active=read_active_generation(root)
        previous=active[2] if active else {}
        files,_=discover_content(root)
        words=read_vocabulary(database)
        voc_hash=vocabulary_hash(words)
        signature=preparation_signature(root,files,voc_hash)
        changes=source_changes(previous,files,voc_hash)
        if active and previous.get('signature')==signature:
            atomic_json(state/'sync_status.json',{'status':'current','checked_at':time.time(),'source_files':len(files),'vocabulary_items':len(words),'generation':active[0]})
            return {'status':'current','generation':active[0]}
        stale_path=state/'stale_sources.json'
        refresh_stale_catalog(root,database)
        with SyncLock(state/'stale.lock'):
            stale_value=json.loads(stale_path.read_text(encoding='utf-8')) if stale_path.exists() else {}
            if not active:
                stale_value={'paths':sorted(set(changes['deleted']+changes['changed'])),'vocabulary_stale':False,'blocked_generations':{}}
                atomic_json(stale_path,stale_value)
        logger=logging.getLogger('learning_content_sync');logger.disabled=True
        if preparer is None:
            runtime_path=root/'chatbot_runtime.json'
            settings=json.loads(runtime_path.read_text(encoding='utf-8-sig')) if runtime_path.exists() else {}
            pdf_workers=int(settings.get('content_pdf_workers',1))
            if not 1<=pdf_workers<=2:raise ValueError('Invalid background PDF worker limit')
            if pdf_workers>1:
                from prepare_pdf_ocr_batch import run as prepare_pdf_batch
                prepare_pdf_batch(root,state/'prepared',database,workers=pdf_workers)
        prep=preparer or ContentPreparer(root,state/'prepared',database)
        manifest=prep.prepare()
        if not manifest.get('complete'):
            result={'status':'pending_extraction','checked_at':time.time(),'source_files':manifest['source_files'],'ready_files':manifest['ready_files'],'pending_files':[{key:row[key] for key in ['path','status','error_type'] if key in row} for row in manifest['files'] if row['status']!='ready']}
            atomic_json(state/'sync_status.json',result)
            return result
        if builder is None:
            from .content_index import build_candidate
            builder=build_candidate
        generation,candidate=builder(root,state/'prepared',manifest,logger)
        # A second snapshot prevents publishing an index already superseded by
        # an edit/removal that arrived during extraction or embedding.
        current_files,_=discover_content(root)
        current_words=read_vocabulary(database)
        current_signature=preparation_signature(root,current_files,vocabulary_hash(current_words))
        if current_signature!=manifest['signature']:
            result={'status':'source_changed_during_build','checked_at':time.time()}
            atomic_json(state/'sync_status.json',result)
            return result
        publish_generation(root,generation,candidate,lambda target,value:None)
        # Old processes must keep blocking superseded sources until the runtime
        # has loaded this generation. The new generation can answer immediately.
        with SyncLock(state/'stale.lock'):
            latest=json.loads(stale_path.read_text(encoding='utf-8')) if stale_path.exists() else stale_value
            atomic_json(stale_path,{**latest,'published_generation':generation})
        result={'status':'published','checked_at':time.time(),'generation':generation,'source_files':manifest['source_files'],'vocabulary_items':manifest['vocabulary_items'],'chunks':manifest['chunks']}
        atomic_json(state/'sync_status.json',result)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    try:
        result=run_once(args.root)
        print(json.dumps({key:value for key,value in result.items() if key!='pending_files'}))
        raise SystemExit(0 if result['status'] in {'current','published'} else 2)
    except SyncAlreadyRunning:
        print('{"status":"already_running"}')
    except Exception as exc:
        atomic_json(args.root/'data/chatbot_content/sync_status.json',{'status':'failed','error_type':type(exc).__name__,'checked_at':time.time()})
        print(json.dumps({'status':'failed','error_type':type(exc).__name__}))
        raise SystemExit(1)
