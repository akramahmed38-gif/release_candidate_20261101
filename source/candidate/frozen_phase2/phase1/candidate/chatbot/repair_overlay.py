"""Read an immutable base Chroma snapshot plus a small verified correction collection."""
import hashlib
import json
from pathlib import Path


class RepairOverlayStore:
    def __init__(self,config,logger,collection_name=None):
        from .vector_store import ChromaVectorStore
        self.config=config;self.logger=logger
        manifest=json.loads((config.data_path/'content_manifest.json').read_text(encoding='utf-8'))
        overlay=manifest['repair_overlay']
        if overlay.get('schema')!='verified-passage-overlay-v1':raise ValueError('Unsupported correction overlay')
        reference=config.data_path/'base_content_manifest.json'
        if hashlib.sha256(reference.read_bytes()).hexdigest()!=overlay['base_manifest_sha256']:
            raise ValueError('Base generation snapshot fingerprint mismatch')
        self.collection_name=overlay['delta_collection']
        self.base=ChromaVectorStore(config,logger,overlay['base_collection'])
        self.delta=ChromaVectorStore(config,logger,overlay['delta_collection'])
        self.excluded=set(overlay['excluded_chunk_ids'])
        self.source_fingerprints=overlay.get('affected_source_hashes',{})
        self.source_root=Path(getattr(config,'project_path',config.data_path)).resolve()
        self._source_stamps={};self._allowed_sources=set()
        self.refresh_source_state()
        if self.base.count()!=overlay['base_chunk_count'] or self.delta.count()!=overlay['delta_chunk_count']:
            raise ValueError('Correction overlay collection coverage mismatch')
        base_ids=set(self.base.collection.get(ids=list(self.excluded),include=[])['ids'])
        if base_ids!=self.excluded:raise ValueError('Correction anchors are absent from base index')
        self._expected_count=manifest['chunks']
        if self.count()!=self._expected_count:raise ValueError('Correction overlay total coverage mismatch')

    def count(self):return self.base.count()-len(self.excluded)+self.delta.count()

    def refresh_source_state(self):
        allowed=set()
        source_root=self.source_root.resolve()
        for relative,fingerprint in self.source_fingerprints.items():
            try:
                path=(source_root/relative).resolve();path.relative_to(source_root)
                info=path.stat();stamp=(info.st_size,info.st_mtime_ns)
                cached=self._source_stamps.get(relative)
                if cached and cached[0]==stamp:current=cached[1]
                else:
                    current=hashlib.sha256(path.read_bytes()).hexdigest()
                    self._source_stamps[relative]=(stamp,current)
                if current==fingerprint:allowed.add(relative)
            except (OSError,ValueError):pass
        self._allowed_sources=allowed

    def source_allows(self,metadata):
        relative=str(metadata.get('source_path','')).replace('\\','/')
        return relative not in self.source_fingerprints or relative in self._allowed_sources

    def fetch_all_chunks(self):
        return [r for r in self.base.fetch_all_chunks() if r['id'] not in self.excluded]+self.delta.fetch_all_chunks()

    def semantic_search(self,query_embedding,n_results):
        base_budget=min(self.base.count(),n_results+len(self.excluded))
        base=[r for r in self.base.semantic_search(query_embedding,base_budget) if r['id'] not in self.excluded]
        self.refresh_source_state()
        delta=[r for r in self.delta.semantic_search(query_embedding,min(n_results,self.delta.count())) if self.source_allows(r['metadata'])]
        base=[r for r in base if self.source_allows(r['metadata'])]
        return sorted(base+delta,key=lambda r:(r['distance'],r['id']))[:n_results]

    def score_candidates(self,query_embedding,ids):
        ids=set(ids)-self.excluded
        result=self.base.score_candidates(query_embedding,ids)
        result.update(self.delta.score_candidates(query_embedding,ids))
        return result

    def add_chunks(self,*args,**kwargs):raise ValueError('Correction overlays are immutable')
    def reset_collection(self,*args,**kwargs):raise ValueError('Correction overlays are immutable')
    def delete_collection(self,*args,**kwargs):raise ValueError('Correction overlays are immutable')


def vector_store_for_generation(config,logger,collection_name=None):
    path=config.data_path/'content_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    if manifest.get('repair_overlay'):return RepairOverlayStore(config,logger,collection_name)
    from .vector_store import ChromaVectorStore
    return ChromaVectorStore(config,logger,collection_name)


class OverlaySourceFilter:
    def __init__(self,base,store):self.base,self.store=base,store
    def refresh(self):
        if self.base:self.base.refresh()
        self.store.refresh_source_state()
    def allows(self,metadata):return (not self.base or self.base.allows(metadata)) and self.store.source_allows(metadata)


def attach_overlay_filter(retriever,store):
    if hasattr(store,'source_allows'):retriever.source_filter=OverlaySourceFilter(retriever.source_filter,store)
