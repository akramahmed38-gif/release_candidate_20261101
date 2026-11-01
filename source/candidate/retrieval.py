"""Private per-service/topic hybrid retrieval using existing page/section vectors."""
from pathlib import Path
from dataclasses import replace
from time import perf_counter
import json,logging,os,hashlib,uuid
from runtime_engine import ROOT,CoreBackend

class NativeBackend(CoreBackend):
    mode='BGE_M3_CHROMA_BM25_THREE_INDEPENDENT_SOURCE_UNITS'
    def __init__(self,facts,workspace):
        super().__init__(facts)
        import chromadb
        from chromadb.config import Settings
        from chatbot.config import load_config
        from chatbot.generation import OllamaClient
        from native_support import CpuBudget,snapshot_native_chroma
        self.workspace=Path(workspace);self.budget=CpuBudget()
        self.config=replace(load_config(self.workspace),project_path=self.workspace,generation_threads=2,ollama_url='http://127.0.0.1:11434')
        class EmbeddingsOnly(OllamaClient):
            def generate_payload(self,*args,**kwargs):raise RuntimeError('Qwen forbidden')
        self.embed=EmbeddingsOnly(self.config,logging.getLogger('fixture'))
        definition=json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
        tags=self.embed._request('/api/tags',method='GET',timeout_seconds=5)
        if not any(m['name']==definition['expected_embedding_model'] and m.get('digest')==definition['expected_embedding_digest'] for m in tags['models']):raise ValueError('BGE identity mismatch')
        preparation=Path(os.environ['LOCALAPPDATA'])/'HRTrainingExtractionExpanded/20261026_235743_874744cb'
        native=json.loads((preparation/'native/native_build_summary.json').read_text(encoding='utf-8-sig'))
        target=Path(native['target']).resolve();target.relative_to(preparation.resolve())
        if native['generation']!=definition['source_content_generation']:raise ValueError('Generation mismatch')
        manifest=json.loads((target/'content_manifest.json').read_text(encoding='utf-8-sig'));overlay=manifest['repair_overlay']
        if hashlib.sha256((target/'base_content_manifest.json').read_bytes()).hexdigest()!=overlay['base_manifest_sha256']:raise ValueError('Base manifest mismatch')
        for path,sha in definition['sources'].items():
            if next(r['sha256'] for r in manifest['files'] if r['path']==path)!=sha:raise ValueError('Source version mismatch')
        copy=self.workspace/'native_snapshot'
        self.budget.wait();snapshot=snapshot_native_chroma(target/'chroma',copy,overlay['base_collection'])
        settings=Settings(anonymized_telemetry=False)
        self.source=chromadb.PersistentClient(path=str(copy),settings=settings)
        collection=self.source.get_collection(overlay['base_collection'],embedding_function=None)
        vectors={}
        for unit,anchor in definition['anchors'].items():
            if not any(f['source_unit_id']==unit for f in facts.values()):continue
            cid=anchor['chunk_id']
            if cid in overlay['excluded_chunk_ids']:raise ValueError('Superseded anchor')
            row=collection.get(ids=[cid],include=['embeddings','metadatas'])
            if row['ids']!=[cid]:raise ValueError('Exact anchor missing')
            metadata=row['metadatas'][0];fact=next(f for f in facts.values() if f['source_unit_id']==unit)
            if metadata['source_path']!=fact['source_document'] or metadata['source_sha256']!=fact['source_sha256']:raise ValueError('Anchor source mismatch')
            vectors[unit]=[float(v) for v in row['embeddings'][0]]
        self.client=chromadb.PersistentClient(path=str(self.workspace/'fixture_chroma'),settings=settings)
        self.collection=self.client.create_collection('phase2_unapproved_'+uuid.uuid4().hex[:12],metadata={'hnsw:space':'cosine','hnsw:num_threads':2},embedding_function=None)
        self.collection.add(ids=list(facts),documents=[f['arabic']+'\n'+f['english'] for f in facts.values()],embeddings=[vectors[f['source_unit_id']] for f in facts.values()],metadatas=[{'service_id':f['service_id'],'unit_id':f['source_unit_id'],'fact_id':f['fact_id'],'test_only':True} for f in facts.values()])
        self.initialization={'source_generation':native['generation'],'units':len(vectors),'fact_rows':len(facts),'source_documents':len(definition['sources']),'document_embeddings_created':0,'snapshot':snapshot,'embedding_digest':definition['expected_embedding_digest'],'thresholds':{'semantic':self.config.min_semantic_score,'final':self.config.min_final_score,'overlap':self.config.min_keyword_overlap},'threads':2}

    def search_slot(self,question,service,topic,ids):
        from chatbot.normalization import tokenize_for_search
        wait=perf_counter();self.budget.wait();wait_ms=(perf_counter()-wait)*1000
        with self.embed._embedding_cache_lock:self.embed._embedding_cache.clear()
        expanded=question+' '+service.replace('_',' ')+' '+topic.replace('_',' ')
        start=perf_counter();vector=self.embed.embed_texts([expanded])[0];embed_ms=(perf_counter()-start)*1000
        start=perf_counter()
        data=self.collection.query(query_embeddings=[vector],where={'$and':[{'service_id':service},{'fact_id':{'$in':ids}}]},n_results=min(self.config.semantic_candidates,len(ids)),include=['distances'])
        chroma_ms=(perf_counter()-start)*1000
        start=perf_counter();tokens=tokenize_for_search(expanded)
        scores={fid:self.score(self.stats,tokens,self.rows[fid]) for fid in ids}
        bm25_ms=(perf_counter()-start)*1000;accepted=[];ranks=[]
        for fid,distance in zip(data['ids'][0],data['distances'][0]):
            sem=max(0,1-float(distance)/2);bm25=scores[fid];final=.6*sem+.4*bm25/(1+bm25);overlap=len(set(tokens)&set(self.rows[fid]))
            eligible=final>=self.config.min_final_score and (sem>=self.config.min_semantic_score or overlap>=self.config.min_keyword_overlap)
            if eligible:accepted.append(fid)
            ranks.append({'fact_id':fid,'semantic':sem,'bm25':bm25,'final':final,'overlap':overlap,'eligible':eligible})
        return accepted,{'backend':self.mode,'query_embedding_calls':1,'query_embedding_ms':embed_ms,'chroma_ms':chroma_ms,'bm25_ms':bm25_ms,'resource_wait_ms':wait_ms,'ranks':ranks,'generation_calls':0}
