"""Fourteen-fixture catalog candidate. No normal runtime entry."""
from pathlib import Path
from time import perf_counter
import sys,json,threading,hashlib
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'frozen_phase2'))
import runtime_engine as frozen
sys.path.insert(0,str(ROOT))
from request_planner import CurrentQueryPlanner as CatalogPlanner
from evidence_contracts import select_for_request,approve_view,completeness_review,route_for_request
from source_snapshot import preserve_valid_slots
from question_coverage import audit_question
from chatbot.conversation_memory import ConversationStore
from chatbot.reference_validation import scoped_numeric_checks

class CatalogEngine(frozen.MultiEngine):
    def __init__(self,workspace,backend_factory=frozen.CoreBackend,test_mode=False,definition_override=None):
        if not test_mode:raise frozen.IsolationError('Unapproved fixture cannot enter normal mode')
        self.workspace=Path(workspace)
        if json.loads((self.workspace/'ISOLATED_TEST_ONLY.json').read_text())!={'fixture_only':True,'production_use_allowed':False,'approvals_pending':True}:raise frozen.IsolationError('Isolation marker')
        self.definition=definition_override if definition_override is not None else json.loads((ROOT/'fixture_data/definition.json').read_text(encoding='utf-8'))
        from registry import load_records
        self.facts,self.rejected_records=load_records(self.definition,self.workspace/'source_files',set(self.definition['authorized_test_ids']))
        if not self.facts:raise frozen.IsolationError('Registry has no eligible technical fixtures')
        for f in self.facts.values():
            if any(f[k] for k in ['normal_runtime_eligible','human_fidelity_approved','business_approved']):raise frozen.IsolationError('Approval promotion')
            for key in ['arabic','english']:
                if hashlib.sha256(f[key].encode()).hexdigest()!=f[key+'_sha256']:raise frozen.IsolationError('View fingerprint')
            if not scoped_numeric_checks(f['arabic'],f['english'],f['aspect'])[0]:raise frozen.IsolationError('Unchanged numerical validator')
        self.store=ConversationStore();self.catalog=CatalogPlanner(self.definition,self.store)
        self.store=self.catalog.store
        self.backend=backend_factory(self.facts);self.lock=threading.Lock();self._intent=None
        self.before_emit_hook=None
        self.approval_registry={}
        self.request_selections={}
    def interpret(self,q,cid,sid):
        if self._intent is not None:return self._intent
        return self.catalog.plan(q,cid,sid)
    def required(self,service,topic):
        requests=[r for r in self._intent.get('request_contract',{}).get('requests',[]) if r['service_id']==service and r['topic']==topic]
        result=[]
        for request in requests:
            selected=select_for_request(request,self.facts,self.definition,self.catalog.adapter)
            self.request_selections[request['request_id']]=selected
            ids=[fid for fid in selected['eligible_fact_ids'] if approve_view(self.facts[fid],self._intent['language'],self.approval_registry,fixture_mode=True,authorized_fixture_ids=self.definition['authorized_test_ids'])]
            result.extend(fid for fid in ids if fid not in result)
        return result
    def ask(self,q,conversation='fixture',session='synthetic'):
        queued=perf_counter()
        with self.lock:
            wait_ms=(perf_counter()-queued)*1000
            t=perf_counter()
            self.request_selections={}
            prior_context=self.store.get_business_context(conversation,session) or {}
            self._intent=self.catalog.plan(q,conversation,session)
            contract=self._intent['request_contract']
            # Keep unsupported channel scopes explicit instead of treating a
            # supported subset as the complete requested tariff.
            extra=[]
            for service,topic in self._intent['slots']:
                scope=self._intent.get('slot_conditions',{}).get(service+'|'+topic,self._intent.get('conditions',[]))
                parents=self.catalog.catalog.get('channel_parents',{})
                channels=set(scope)&({'atm','branch'}|set(parents))
                channels-=set(parents[c] for c in channels if c in parents)
                scoped=[f for f in self.facts.values() if f['service_id']==service and topic in f['selection_tags'] and f['required_channel']]
                if scoped:
                    supported={f['required_channel'] for f in scoped}
                    extra.extend((service,topic+' / missing channel '+c) for c in channels-supported)
            self._intent['slots'].extend(extra)
            planning_ms=(perf_counter()-t)*1000;t=perf_counter()
            original_sources=self.definition['sources']
            requested=[fid for service,topic in self._intent['slots'] for fid in self.required(service,topic)]
            self.definition['sources']={f['source_document']:f['source_sha256'] for fid,f in self.facts.items() if fid in requested}
            scope_ms=(perf_counter()-t)*1000;t=perf_counter()
            auth=self.workspace/'test_eligibility.json';auth_before=auth.read_bytes()
            generation=self.workspace/'generation.json';generation_before=generation.read_bytes()
            if hasattr(self.backend,'begin_request'):self.backend.begin_request(q,self._intent,self.definition,generation_before)
            setup_ms=(perf_counter()-t)*1000
            try:
                result=super().ask(q,conversation,session)
                evidence_started=perf_counter()
                proof=completeness_review(contract,result['supported_fact_ids'],result['citations'],self.facts,self.definition,self.catalog.adapter,language=result['reply_language'],approval_registry=self.approval_registry,fixture_mode=True,authorized_fixture_ids=self.definition['authorized_test_ids'])
                result['request_contract']=contract
                result['evidence_contract']=proof
                result['request_selections']=dict(self.request_selections)
                if proof['unrelated_fact_ids'] or proof['scope_violations'] or proof['citation_violations']:
                    result.update(type='unavailable',complete=False,supported_fact_ids=[],citations=[],answer='The request/evidence binding could not be verified; no business answer emitted.')
                    result['contract_rejection']=True
                elif result['complete'] and not proof['complete']:
                    result['complete']=False
                if contract['unresolved_spans']:
                    labels=list(dict.fromkeys(x['kind'] for x in contract['unresolved_spans']))
                    result['clarification_dimensions']=labels
                    result['answer']+='\n\n'+('Unresolved request dimensions: ' if result['reply_language']=='en' else 'أبعاد طلب تحتاج إلى توضيح: ')+', '.join(labels)
                    result['complete']=False
                coverage_started=perf_counter()
                # The audit must see the authoritative pinned catalog rather
                # than the planner-pruned source-read optimization. Actual
                # emitted sources still pass registry and pre-emission hashes.
                audit_definition={**self.definition,'sources':original_sources}
                coverage=audit_question(q,result,self.facts,audit_definition,prior_context)
                result['question_coverage']=coverage
                unsafe=set(coverage['excluded_fact_ids'])|set(coverage['unrelated_fact_ids'])
                if unsafe:
                    preserve_valid_slots(result,[],self.facts,self.definition,invalid_fact_ids=unsafe,reason='question_scope_not_supported')
                    # Re-evaluate the independently enumerated question after
                    # removing an unsafe bundled fact.  This lets valid
                    # sibling assertions become complete without allowing the
                    # rejected fact to influence status or citations.
                    coverage=audit_question(q,result,self.facts,audit_definition,prior_context)
                    result['question_coverage']=coverage
                    unsafe=set(coverage['excluded_fact_ids'])|set(coverage['unrelated_fact_ids'])
                if coverage.get('fulfillment_convergence_applied') and coverage['complete_eligible']:
                    # The independent raw-question audit may prove that every
                    # original requested dimension is exactly source-bound
                    # even when the planner retained a conservative,
                    # non-business unresolved span.  In that case it is the
                    # authoritative completeness gate: no fact is added or
                    # rewritten, and exclusions/unrelated facts/citations
                    # have already been checked above.
                    result['complete']=True
                    result.pop('clarification_dimensions',None)
                elif not coverage['complete_eligible']:
                    result['complete']=False
                    result['answer']+='\n\n'+('Some requested parts could not be verified.' if result['reply_language']=='en' else 'بعض الأجزاء المطلوبة تحتاج إلى توضيح أو دليل إضافي.')
                result['answer_status']=coverage['decision']
                coverage_ms=(perf_counter()-coverage_started)*1000
                evidence_ms=(perf_counter()-evidence_started)*1000-coverage_ms
                recorded_retrieval=[s.get('retrieval',{}) for s in result.get('slots',[])]
                t=perf_counter()
                if self.before_emit_hook:self.before_emit_hook()
                stale=[]
                emitted_sources={c['source_document'] for c in result.get('citations',[])}
                for source,expected in self.definition['sources'].items():
                    if source not in emitted_sources:continue
                    try:valid=hashlib.sha256((self.workspace/'source_files'/source).read_bytes()).hexdigest()==expected
                    except OSError:valid=False
                    if not valid:stale.append(source)
                if stale:
                    preserve_valid_slots(result,stale,self.facts,self.definition)
                    result['evidence_contract']=completeness_review(contract,result['supported_fact_ids'],result['citations'],self.facts,self.definition,self.catalog.adapter,language=result['reply_language'],approval_registry=self.approval_registry,fixture_mode=True,authorized_fixture_ids=self.definition['authorized_test_ids'])
                if auth.read_bytes()!=auth_before or generation.read_bytes()!=generation_before:
                    result.update(type='unavailable',complete=False,supported_fact_ids=[],citations=[],slots=[],answer='Test eligibility or generation changed during this request; no business answer emitted.')
                    result['invalidation_reason']='eligibility_or_generation_changed_before_emission'
                recheck_ms=(perf_counter()-t)*1000;t=perf_counter()
                result['request_generation_sha256']=hashlib.sha256(generation_before).hexdigest()
                result['work_counters']=getattr(self.backend,'counters',{'actual_embedding_calls':0,'mode':'core_without_native_proof'})
                result['source_cache']['request_snapshot_pinned']=True
                result['source_cache']['eligibility_rechecked_before_emission']=True
                metadata_ms=(perf_counter()-t)*1000
            finally:
                t=perf_counter();self.definition['sources']=original_sources;self._intent=None;cleanup_ms=(perf_counter()-t)*1000
            timings=result['timings_ms'];timings['cached_intent_lookup_ms']=timings['interpretation_ms']
            timings.update(interpretation_ms=planning_ms,evidence_contract_ms=evidence_ms,question_coverage_ms=coverage_ms,admission_wait_ms=wait_ms,dependency_scope_ms=scope_ms,request_setup_ms=setup_ms,pre_emit_verification_ms=recheck_ms,response_metadata_ms=metadata_ms,cleanup_ms=cleanup_ms)
            timings['engine_wall_ms']=(perf_counter()-queued)*1000
            primary=['admission_wait_ms','interpretation_ms','evidence_contract_ms','question_coverage_ms','dependency_scope_ms','request_setup_ms','source_verification_ms','fact_selection_ms','retrieval_ms','validation_and_assembly_ms','pre_emit_verification_ms','response_metadata_ms','cleanup_ms']
            timings['engine_unattributed_overhead_ms']=timings['engine_wall_ms']-sum(timings[k] for k in primary)
            retrieval=recorded_retrieval
            breakdown={key:sum(r.get(key,0) for r in retrieval) for key in ['resource_wait_ms','query_embedding_ms','chroma_ms','bm25_ms']}
            breakdown['retrieval_key_ranking_and_overhead_ms']=timings['retrieval_ms']-sum(breakdown.values())
            result['retrieval_breakdown_ms']=breakdown
            if self._intent is None:
                interpreted=result['interpretation']
                if interpreted.get('ambiguous'):status='interpretation_ambiguous'
                elif contract['unresolved_spans']:status='interpretation_incomplete'
                elif interpreted.get('foreign') and any(r.get('unsupported_named_provider') for r in contract['requests']):status='recognized_unsupported_named_provider'
                elif not interpreted['services']:status='service_unresolved'
                elif not interpreted['topics'] or interpreted['topics']==['unspecified']:status='topic_unrecognized'
                elif result['complete']:status='complete_scoped_answer'
                elif result['supported_fact_ids']:status='partial_scoped_answer'
                else:status='recognized_scope_without_eligible_evidence'
                result['resolution_status']=status
                if status in ['interpretation_ambiguous','service_unresolved','topic_unrecognized']:
                    result['clarification_needed']=True
                if result['complete']:result['answer_status']='complete'
                elif result['supported_fact_ids']:result['answer_status']='supported_partial'
                elif result['question_coverage'].get('conflicts'):result['answer_status']='conflict'
                elif contract['unresolved_spans'] or result['question_coverage']['decision']=='clarify':result['answer_status']='clarify'
                elif result['question_coverage']['decision']=='live_lookup_required' or any(route_for_request(r,self.catalog.adapter)=='live_record_required' for r in contract['requests']):result['answer_status']='live_lookup_required'
                else:result['answer_status']='unsupported'
                result['clarification_needed']=bool(contract['unresolved_spans'] or result['question_coverage']['decision']=='clarify' or status in ['interpretation_ambiguous','service_unresolved','topic_unrecognized'])
            unresolved_conditions=any(row.get('kind') in {'condition_operand_unresolved','condition_target_unresolved'}
                                      for row in contract['unresolved_spans'])
            if not result['complete'] and not unresolved_conditions:
                reviews=result['evidence_contract'].get('request_reviews',[])
                names=[]
                for request in contract['requests']:
                    if not any(c.get('operator')=='exclusive_temporal_restriction' for c in request.get('conditions',[]) if isinstance(c,dict)):continue
                    if not any(review.get('request_id')==request['request_id'] and any(
                        gap.get('code')=='condition_not_established' for gap in review.get('gaps',[])) for review in reviews):continue
                    name=self.definition['service_profiles'].get(request.get('service_id'),{}).get('name',request.get('service_id'))
                    if name and name not in names:names.append(name)
                if names:
                    text=('لا تثبت المراجع المتاحة القيد الزمني المطلوب لهذه الخدمة.' if result['reply_language']=='ar'
                          else 'The selected sources do not establish the requested timing restriction.')
                    result['scope_gap_messages']=[{'service':name,'dimension':'timing_restriction','message':text} for name in names]
                    result['answer']=result['answer'].rstrip()+'\n\n'+'\n'.join(name+': '+text for name in names)
            return result
