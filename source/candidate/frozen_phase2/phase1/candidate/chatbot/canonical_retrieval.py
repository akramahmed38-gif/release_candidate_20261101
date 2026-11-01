"""Independent scoped BGE-M3/Chroma and existing BM25 retrieval per evidence slot."""
from collections import defaultdict
from time import perf_counter
import math

from .normalization import tokenize_for_search
from .profiling import record_timing
from .evidence_selection import topic_support,topic_rank,reconcile_uncertain_scopes,relevant_caveat


class SlotRetriever:
    def __init__(self, service, projection):
        self.service, self.projection = service, projection
        # Reuse the current corpus, tokenization and exact BM25 scoring. This
        # index is private, immutable and built once, never a document rebuild.
        self.by_source = defaultdict(list)
        for row in service.retriever.corpus:
            self.by_source[row['metadata'].get('source_path','').replace('\\','/')].append(row)

    def _semantic(self, embedding, paths):
        store = self.service.vector_store
        stores = [store.base,store.delta] if hasattr(store,'base') else [store]
        variants = sorted({p for path in paths for p in (path,path.replace('/','\\'))})
        rows = []
        for native in stores:
            collection = native.collection
            count = collection.get(where={'source_path':{'$in':variants}},include=[])['ids']
            if not count: continue
            data = collection.query(query_embeddings=[embedding],
                n_results=min(self.service.config.semantic_candidates,len(count)),
                where={'source_path':{'$in':variants}},include=['distances'])
            for cid,distance in zip(data['ids'][0],data['distances'][0]):
                if hasattr(store,'excluded') and cid in store.excluded: continue
                rows.append((cid,max(0,1-float(distance)/2)))
        return dict(sorted(rows,key=lambda r:(-r[1],r[0]))[:self.service.config.semantic_candidates])

    def retrieve(self, slot, question):
        started = perf_counter(); pairs = self.projection.candidates(slot['service_id'],slot['topic_id'])
        accepted=[]; excluded=defaultdict(int)
        for unit,approval in pairs:
            status=self.projection.gate(unit,approval,slot)
            if status=='supported': accepted.append((unit,approval))
            else: excluded[status]+=1
        diagnostics={'service_id':slot['service_id'],'topic_id':slot['topic_id'],
            'conditions':slot['conditions'],'modifiers':slot['modifiers'],'discovered_units':len(pairs),
            'excluded_counts':dict(excluded),'status':'unsupported','evidence':[],
            'relationships_discovery_only':len(self.projection.discovery_links(slot['service_id'],slot['topic_id']))}
        pending=self.projection.pending_locators(slot['service_id'],slot['topic_id'])
        diagnostics['pending_pdf_locators']=pending
        diagnostics['review_references']=[{k:u.get(k) for k in ('unit_id','source_path','source_sha256','line_start','line_end','status','verification')}
                                          for u,a in pairs if self.projection.gate(u,a,slot)!='supported']
        if not accepted:
            diagnostics['status']='stale' if pairs and excluded.get('stale')==len(pairs) else 'review_required' if pairs or pending else 'unsupported'
            diagnostics['retrieval_ms']=(perf_counter()-started)*1000
            return diagnostics
        paths={u['source_path'] for u,_ in accepted}
        query=self.projection.profiles[slot['service_id']]['name']+' '+slot['topic_id']+' '+question
        t=perf_counter(); embedding=self.service.ollama_client.embed_texts([query])[0]
        diagnostics['embedding_ms']=(perf_counter()-t)*1000
        t=perf_counter(); semantic=self._semantic(embedding,paths)
        diagnostics['chroma_ms']=(perf_counter()-t)*1000
        tokens=tokenize_for_search(query); t=perf_counter()
        scoped=[r for path in paths for r in self.by_source.get(path,[])
                if r['id'] not in getattr(self.service.vector_store,'excluded',set())]
        lexical={r['id']:self.service.retriever._bm25_score(tokens,r['doc_tokens']) for r in scoped}
        lexical=dict(sorted(((k,v) for k,v in lexical.items() if v>0),key=lambda x:(-x[1],x[0]))[:self.service.config.keyword_candidates])
        ids=set(semantic)|set(lexical)
        # Bounded catalog-guided expansion for reviewed source locations. Keep
        # the original semantic/BM25 budgets; score real existing vectors for
        # these anchors instead of inventing a hit or rebuilding embeddings.
        guided=[]
        for unit,_ in accepted:
            if unit.get('verification')!='reviewed_repair' or not topic_support(unit,slot['topic_id'],slot.get('modifiers',[])):continue
            tokens_for_unit=set(tokenize_for_search(unit['body']))
            candidates=[r for r in scoped if r['metadata'].get('source_path','').replace('\\','/')==unit['source_path']
                and (not unit.get('location_value') or str(r['metadata'].get('location_value',''))==str(unit['location_value']))]
            candidates.sort(key=lambda r:(-len(tokens_for_unit & set(r['doc_tokens'])),r['id']))
            for row in candidates[:1]:
                if row['id'] not in ids and row['id'] not in guided:guided.append(row['id'])
        guided=guided[:16];ids.update(guided)
        diagnostics['guided_reviewed_source_anchors']=len(guided)
        semantic.update(self.service.vector_store.score_candidates(embedding,ids-set(semantic)))
        diagnostics['bm25_ms']=(perf_counter()-t)*1000
        selected=[]
        for unit,approval in accepted:
            # Full reviewed units are the evidence, not truncated raw index
            # snippets. Native search must independently find that source and
            # location; approval alone is not a fabricated retrieval hit.
            anchors=[r for r in scoped if r['id'] in ids and
                r['metadata'].get('source_path','').replace('\\','/')==unit['source_path'] and
                (not unit.get('location_value') or
                 str(r['metadata'].get('location_value',''))==str(unit['location_value']))]
            if not anchors: continue
            unit_tokens=set(tokenize_for_search(unit['body']))
            scored=[]
            for row in anchors:
                overlap=len(unit_tokens & set(row['doc_tokens']))/max(1,len(unit_tokens))
                reviewed_page=(unit.get('verification')=='reviewed_repair' and unit.get('location_type')=='page'
                               and str(row['metadata'].get('location_value',''))==str(unit.get('location_value')))
                if overlap < .25 and not reviewed_page: continue
                score=.6*semantic.get(row['id'],0)+.4*overlap
                scored.append((score,row['id']))
            if not scored: continue
            score,cid=max(scored)
            # Rank actual topic support above incidental words and metadata.
            # Verified repairs replace damaged extraction of that source;
            # their priority is not a claim of business-policy supersession.
            from .canonical_context import TOPICS,norm,mentions
            heading=norm(unit.get('rule_heading') or unit['heading'])
            direct=topic_support(unit,slot['topic_id'],slot.get('modifiers',[]))
            if slot['topic_id']=='documents' and __import__('re').search(r'(?:اوراق|مستندات).{0,20}(?:مطلوبه|الزاميه)',heading):
                score+=.25
            pure_discount=bool(approval and approval.get('predicate')=='withdrawal_discount')
            if pure_discount and 'withdrawal_discount' not in slot.get('modifiers',[]):direct=False
            score+=.35*direct+.04*unit.get('extraction_priority',1)
            selected.append({'unit':unit,'approval':approval,'anchor_chunk_id':cid,'score':score,
                'direct_support':direct,'eligibility':self.projection.eligibility(unit,approval,slot).to_dict()})
        selected,held=reconcile_uncertain_scopes(selected,slot['topic_id'])
        diagnostics['held_scope_conflicts']=held
        selected.sort(key=lambda r:topic_rank(r,slot['topic_id']))
        # Prefer complete rule units; avoid repeating equivalent source rows.
        kept=[];seen=set()
        for item in selected:
            key=(item['unit']['source_sha256'],item['unit']['text_sha256'])
            if key in seen:continue
            seen.add(key);kept.append(item)
            if len(kept)>=self.service.config.top_k:break
        diagnostics['evidence']=kept
        diagnostics['status']='supported' if any(x['direct_support'] for x in kept) else 'partial' if kept else 'unsupported'
        diagnostics['coverage']='direct_source_rule' if diagnostics['status']=='supported' else 'source_subset_or_missing'
        if any(relevant_caveat(x['unit'],slot['topic_id'],slot.get('conditions',[])) for x in kept):
            diagnostics['status']='partial';diagnostics['coverage']='explicit_source_uncertainty'
        # Finding one relevant paragraph establishes eligibility, not complete
        # coverage of an open-ended documents/procedure request. Preserve that
        # distinction even when a source uses a promising section heading.
        if kept:
            primary=kept[0]['unit'];body=norm(primary['body'])
            open_list=bool(__import__('re').search(r'من اهم|بعض المتطلبات|تشمل.*ما يلي|among|some requirements',body))
            if (slot['topic_id'] in ('documents','activation','workflow') and
                    (open_list or (primary.get('partial_procedure') and slot['topic_id']=='workflow') or
                     (slot['topic_id']=='workflow' and not primary.get('supports_complete_procedure')))):
                diagnostics['status']='partial';diagnostics['coverage']='source_verified_subset_not_complete_procedure'
        diagnostics['completeness']={'eligible_evidence_present':bool(kept),
            'requested_slot_fully_supported':diagnostics['status']=='supported',
            'assessment':diagnostics['coverage'],'independent_business_answer_review_required':True}
        diagnostics['retrieval_ms']=(perf_counter()-started)*1000
        record_timing('canonical.slot_retrieval_ms',diagnostics['retrieval_ms'],accumulate=True)
        return diagnostics
