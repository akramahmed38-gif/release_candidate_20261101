"""Real existing BGE-M3/Chroma retrieval, private copied vectors only."""
from dataclasses import replace
from pathlib import Path
from time import perf_counter
import hashlib,json,logging,os,uuid
from pilot_engine import ROOT,LexicalBackend

class NativeBackend(LexicalBackend):
    mode='REAL_BGE_M3_CHROMA_EXISTING_BM25_PRIVATE_THREE_FACT_FIXTURE'
    def __init__(self,facts,workspace):
        super().__init__(facts)
        import chromadb
        from chromadb.config import Settings
        from chatbot.config import load_config
        from chatbot.generation import OllamaClient
        from native_support import snapshot_native_chroma,CpuBudget
        self.budget=CpuBudget();self.workspace=Path(workspace)
        self.config=replace(load_config(self.workspace),project_path=self.workspace,generation_threads=2,ollama_url='http://127.0.0.1:11434')
        class EmbedOnlyClient(OllamaClient):
            def generate_payload(self,*a,**k):raise RuntimeError('Generation forbidden in source-view test')
        logger=logging.getLogger('isolated_axis_fixture');logger.disabled=True
        self.embed=EmbedOnlyClient(self.config,logger);self.budget.wait()
        self.definition=json.loads((ROOT/'fixture_data/fixture_definition.json').read_text(encoding='utf-8'))
        models=self.embed._request('/api/tags',method='GET',timeout_seconds=5)
        installed={m['name']:m.get('digest') for m in models.get('models',[])}
        if installed.get(self.definition['expected_embedding_model'])!=self.definition['expected_embedding_digest']:raise ValueError('Existing BGE model fingerprint mismatch')
        preparation=Path(os.environ['LOCALAPPDATA'])/'HRTrainingExtractionExpanded/20261026_235743_874744cb'
        native=json.loads((preparation/'native/native_build_summary.json').read_text(encoding='utf-8-sig'))
        target=Path(native['target']).resolve();target.relative_to(preparation.resolve())
        if native['generation']!=self.definition['source_content_generation']:raise ValueError('Prepared native generation mismatch')
        manifest=json.loads((target/'content_manifest.json').read_text(encoding='utf-8-sig'))
        source=next(r for r in manifest['files'] if r['path'].replace('\\','/')==self.definition['source_document'])
        if source['sha256']!=self.definition['source_sha256']:raise ValueError('Prepared source version mismatch')
        overlay=manifest.get('repair_overlay')
        anchor_collection=manifest['collection_name']
        if overlay:
            reference=target/'base_content_manifest.json'
            if overlay.get('schema')!='verified-passage-overlay-v1' or hashlib.sha256(reference.read_bytes()).hexdigest()!=overlay['base_manifest_sha256']:raise ValueError('Repaired base manifest identity mismatch')
            if self.definition['existing_anchor_chunk_id'] in overlay['excluded_chunk_ids']:raise ValueError('Requested old anchor superseded by repair')
            anchor_collection=overlay['base_collection']
        copy=self.workspace/'native_index_snapshot'
        snapshot_info=snapshot_native_chroma(target/'chroma',copy,anchor_collection)
        settings=Settings(anonymized_telemetry=False)
        self.source_client=chromadb.PersistentClient(path=str(copy),settings=settings)
        source_collection=self.source_client.get_collection(anchor_collection,embedding_function=None)
        anchor=source_collection.get(ids=[self.definition['existing_anchor_chunk_id']],include=['embeddings','metadatas'])
        if len(anchor['ids'])!=1:raise ValueError('Exact reused source anchor missing')
        meta=anchor['metadatas'][0]
        if meta['source_path'].replace('\\','/')!=self.definition['source_document'] or str(meta['location_value'])!='1':raise ValueError('Reused anchor source/page mismatch')
        if meta.get('source_sha256')!=self.definition['source_sha256']:raise ValueError('Reused anchor version mismatch')
        vector=[float(x) for x in anchor['embeddings'][0]]
        self.client=chromadb.PersistentClient(path=str(self.workspace/'fixture_chroma'),settings=settings)
        self.collection=self.client.create_collection('unapproved_axis_fixture_'+uuid.uuid4().hex[:12],metadata={'hnsw:space':'cosine','fixture_only':True},embedding_function=None)
        # All three assertions share this reviewed page/unit. Reusing its vector
        # does not pretend that three independent embeddings were computed.
        self.collection.add(ids=list(facts),embeddings=[vector for _ in facts],documents=[f['arabic']+'\n'+f['english'] for f in facts.values()],metadatas=[{'fact_id':fid,'fixture_only':True,'source_sha256':self.definition['source_sha256'],'source_unit_id':f['source_unit_id']} for fid,f in facts.items()])
        self.initialization={'backend':self.mode,'source_generation':native['generation'],'source_anchor':self.definition['existing_anchor_chunk_id'],'unique_reused_source_vectors':1,'fixture_fact_rows':3,'document_embedding_calls':0,'embedding_dimensions':len(vector),'snapshot':snapshot_info,'embedding_model_digest':self.definition['expected_embedding_digest'],'thresholds':{'min_semantic_score':self.config.min_semantic_score,'min_final_score':self.config.min_final_score,'min_keyword_overlap':self.config.min_keyword_overlap},'num_threads':2}

    def search(self,question,aspects):
        wait=perf_counter();self.budget.wait();wait_ms=(perf_counter()-wait)*1000
        # Clear only this test client's query cache; original caches untouched.
        with self.embed._embedding_cache_lock:self.embed._embedding_cache.clear()
        expanded=question+' AXIS '+ ' '.join(a.replace('_',' ') for a in aspects)
        start=perf_counter();vector=self.embed.embed_texts([expanded])[0];embedding_ms=(perf_counter()-start)*1000
        start=perf_counter();data=self.collection.query(query_embeddings=[vector],n_results=min(self.config.semantic_candidates,len(self.facts)),include=['distances']);chroma_ms=(perf_counter()-start)*1000
        _,diagnostics=super().search(question,aspects);scores=diagnostics['bm25_scores'];accepted=[];ranks=[]
        from chatbot.normalization import tokenize_for_search
        query_tokens=set(tokenize_for_search(expanded))
        for fid,distance in zip(data['ids'][0],data['distances'][0]):
            semantic=max(0,1-float(distance)/2);lexical=scores[fid]/(1+scores[fid]);final=.6*semantic+.4*lexical
            overlap=len(query_tokens & set(self.rows[fid]))
            eligible=final>=self.config.min_final_score and (semantic>=self.config.min_semantic_score or overlap>=self.config.min_keyword_overlap)
            ranks.append({'fact_id':fid,'semantic_score':semantic,'bm25_score':scores[fid],'final_score':final,'overlap':overlap,'retrieval_eligible':eligible})
            if eligible:accepted.append(fid)
        diagnostics.update(backend=self.mode,query_embedding_calls=1,query_embedding_ms=embedding_ms,chroma_ms=chroma_ms,resource_wait_ms=wait_ms,ranks=ranks,generation_calls=0)
        return accepted,diagnostics
