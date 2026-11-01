"""Same query representation and ranking in both arms; only work reuse differs."""
from pathlib import Path
from time import perf_counter
import hashlib,json
from candidate import ROOT,frozen
import retrieval as previous
previous.ROOT=ROOT
class NativeBackend(previous.NativeBackend):
    def __init__(self,facts,workspace,reuse=True):
        self.reuse=reuse
        super().__init__(facts,workspace)
        self.mode='NATIVE_CATALOG_REQUEST_REUSE' if reuse else 'NATIVE_CATALOG_INSTRUMENTED_NO_REUSE'
        from observed_guard import ObservedBudget
        self.budget=ObservedBudget(stable_window=False)
    def begin_request(self,q,intent,definition,generation):
        self.vectors={};self.seen=set();self.context=(intent,definition,hashlib.sha256(generation).hexdigest())
        self.counters={'logical_slots':0,'unique_embedding_keys':0,'actual_embedding_calls':0,'retrieval_calls':0,'embedding_reuses':0,'cross_request_hits':0,'generation_calls':0,'keys':[],'mode':self.mode}
    def search_slot(self,question,service,topic,ids):
        from chatbot.normalization import tokenize_for_search,normalize_text
        intent,definition,generation=self.context
        # Whole natural question retains all its topics. Explicit service scope
        # is identical for that service's slots, not merged across providers.
        expanded=question+' '+service.replace('_',' ')
        normalized=normalize_text(expanded,for_search=True).lower().strip()
        scope=sorted((f['source_document'],f['source_sha256'],f['english_sha256']) for f in self.facts.values() if f['service_id']==service)
        key=hashlib.sha256(json.dumps([normalized,self.config.embedding_model,definition['expected_embedding_digest'],generation,service,intent['conditions'],scope],sort_keys=True).encode()).hexdigest()
        self.counters['logical_slots']+=1;self.seen.add(key);self.counters['unique_embedding_keys']=len(self.seen)
        wait=perf_counter();self.budget.wait();wait_ms=(perf_counter()-wait)*1000
        start=perf_counter();hit=self.reuse and key in self.vectors
        if hit:vector=self.vectors[key];self.counters['embedding_reuses']+=1
        else:
            with self.embed._embedding_cache_lock:self.embed._embedding_cache.clear()
            vector=self.embed.embed_texts([expanded])[0];self.counters['actual_embedding_calls']+=1
            if self.reuse:self.vectors[key]=vector
        embedding_ms=(perf_counter()-start)*1000
        self.counters['keys'].append({'service':service,'topic':topic,'key':key,'reused':hit})
        start=perf_counter()
        data=self.collection.query(query_embeddings=[vector],where={'$and':[{'service_id':service},{'fact_id':{'$in':ids}}]},n_results=min(self.config.semantic_candidates,len(ids)),include=['distances'])
        chroma_ms=(perf_counter()-start)*1000;self.counters['retrieval_calls']+=1
        start=perf_counter();tokens=tokenize_for_search(expanded);scores={fid:self.score(self.stats,tokens,self.rows[fid]) for fid in ids}
        bm25_ms=(perf_counter()-start)*1000;accepted=[];ranks=[]
        for fid,distance in zip(data['ids'][0],data['distances'][0]):
            semantic=max(0,1-float(distance)/2);score=scores[fid];final=.6*semantic+.4*score/(1+score);overlap=len(set(tokens)&set(self.rows[fid]))
            eligible=final>=self.config.min_final_score and (semantic>=self.config.min_semantic_score or overlap>=self.config.min_keyword_overlap)
            if eligible:accepted.append(fid)
            ranks.append({'fact_id':fid,'semantic':semantic,'bm25':score,'final':final,'overlap':overlap,'eligible':eligible})
        return accepted,{'query_embedding_calls':0 if hit else 1,'query_embedding_ms':embedding_ms,'resource_wait_ms':wait_ms,'guard_events':list(self.budget.events),'chroma_ms':chroma_ms,'bm25_ms':bm25_ms,'ranks':ranks,'embedding_key':key,'request_reused':hit,'generation_calls':0}
