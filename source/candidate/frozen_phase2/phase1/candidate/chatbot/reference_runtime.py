"""Source-attributed RAG answers, independently scoped per service/topic slot."""
from dataclasses import replace
from time import perf_counter
from collections import Counter
import hashlib,json,re

from .canonical_context import REQUEST,TOPICS,norm,mentions
from .canonical_runtime import CanonicalRuntime
from .generation import OllamaClient
from .profiling import record_timing
from .reply_language import _numbers,translation_concept_checks
from .reference_validation import business_numbers,scoped_numeric_checks
from .evidence_eligibility import unsafe_reason
from .semantic_claims import check_semantic_claims
from .validation_language import normalize_validation_language
from .business_glossary import source_glossary
from .slot_generation import SYSTEM,response_schema,decode_slots
from .evidence_selection import topic_rank,reconcile_uncertain_scopes,relevant_caveat


def plain(text):
    text=re.sub(r'^\s*---+\s*$','',str(text),flags=re.M)
    return re.sub(r'\n{3,}','\n\n',text).strip()


def validate_slot(answer, source, language, service_id, planner, allowed_refs, returned_refs, topic=None):
    if not isinstance(answer,str) or len(answer.strip())<8:return False,'empty_or_heading_answer'
    if not returned_refs or set(returned_refs)-set(allowed_refs):return False,'wrong_slot_citation'
    if set(allowed_refs)-set(returned_refs):return False,'missing_supporting_unit_citation'
    unsafe=unsafe_reason({'body':answer,'heading':'','service_ids':[service_id]})
    if unsafe:return False,unsafe
    numeric_source,numeric_answer,_=normalize_validation_language(source,answer)
    ok,reason=scoped_numeric_checks(numeric_source,numeric_answer,topic)
    if not ok:return False,reason
    if language=='en':
        if re.search(r'[\u0621-\u064a]',answer):return False,'english_not_verified'
        claims=check_semantic_claims(source,answer,topic)
        if claims['unsupported_claim_concepts']:return False,'unsupported_non_numeric_business_claim'
        if claims['missing_required_concepts']:return False,'missing_source_workflow_or_document_condition'
        normalized=norm(source)
        if re.search(r'لا يشترط.{0,35}رساله',normalized) and not re.search(
                r'(?:message|sms).{0,45}(?:not required|not necessary|not needed)|(?:no|without).{0,20}(?:message|sms).{0,30}(?:required|needed)|does not require.{0,20}(?:message|sms)',answer,re.I):
            return False,'message_exemption_lost'
        if re.search(r'محفظه اخري',normalized) and re.search(r'الا يكون|لا يوجد|غير مرتبط|الغاء|يجب عدم',normalized) and not re.search(
                r'(?:not|no|without|unlinked).{0,55}(?:another|other|existing).{0,15}wallet|(?:another|other|existing).{0,15}wallet.{0,55}(?:not|remove|cancel|unlink)',answer,re.I):
            return False,'existing_wallet_exclusion_lost'
        context=service_id.replace('_',' ')+' '+str(topic)+' '+answer
        checks=translation_concept_checks(source,context)
        if topic in ('deposit','withdrawal','fees') and '%' in source:
            checks.pop('free_service',None)  # Verified per-channel, not globally.
        if not all(checks.values()):return False,'missing_business_concept'
        for source_rx,target_rx in [
          (r'عالي[ةه]? المخاطر|عالي المخاطر',r'(?:if|for|when).{0,50}high[ -]risk'),
          (r'ساري[ةه]|غير منتهي[ةه]',r'valid|not expired|unexpired'),
          (r'حد ادني|حد أدنى|على الاقل|على الأقل',r'minimum|at least'),
          (r'شهريا|شهري|كل شهر',r'month|monthly'),
          (r'يوميا|يومي',r'day|daily'),
          (r'(?<!\w)مليون(?!\w)',r'million'),(r'(?<!\w)(?:ألف|الف|آلاف|الاف)(?!\w)',r'thousand'),
        ]:
            if re.search(source_rx,source,re.I) and not re.search(target_rx,answer,re.I):
                return False,'missing_condition_or_time_unit'
    elif not re.search(r'[\u0621-\u064a]',answer):return False,'arabic_not_verified'
    # Known systems named in the source can be context, never a substitute
    # provider. Reject a QNB answer to Azimut/ADIB, for example.
    entities=planner.plan(answer).services
    for entity in entities:
        family=planner.profiles.get(entity,{}).get('family')
        if entity!=service_id and family not in ('operations','platform','digital','systems','training','compliance'):
            source_entities=planner.plan(source).services
            if entity not in source_entities:return False,'wrong_service_in_answer'
    return True,None


class ReferenceRuntime(CanonicalRuntime):
    def __init__(self, service, projection, conversations, token_budget=None):
        super().__init__(service,projection,conversations)
        self.token_budget=token_budget

    def service_label(self, service_id, language):
        profile=self.projection.profiles[service_id]
        if language!='en':return profile['name']
        label=profile.get('name_en') or profile['name']
        # Presentation labels must not trigger a second translation of an
        # already verified English answer. IDs are fixed catalog identities.
        return service_id.replace('_',' ').title() if re.search(r'[\u0621-\u064a]',label) else label

    def choose(self, slot):
        evidence,held=reconcile_uncertain_scopes(slot['evidence'],slot['topic_id'])
        if held:
            slot.setdefault('held_scope_conflicts',[]).extend(held);slot['status']='partial'
        evidence=sorted(evidence,key=lambda x:topic_rank(x,slot['topic_id']))
        if not evidence:return []
        if 'withdrawal_discount' in slot.get('modifiers',[]):
            approved=[e for e in evidence if e['eligibility']['operational_policy_approved']]
            if approved:return approved
        chosen=[evidence[0]]
        complete_workflow=(slot['topic_id']=='workflow' and bool(re.search(r'كامله|كامل|complete|full',norm(evidence[0]['unit']['heading']))))
        def duplicate_partial_procedure(item):
            if not (complete_workflow and item['unit'].get('partial_procedure') and
                    item['unit']['source_sha256']==evidence[0]['unit']['source_sha256']):return False
            steps=[re.sub(r'^\s*\d+[.)-]\s*','',line) for line in item['unit']['body'].splitlines()
                   if re.match(r'^\s*\d+[.)-]\s*',line)]
            normalize=lambda text:re.sub(r'[*_`]','',norm(text))
            complete=normalize(evidence[0]['unit']['body'])
            # A "complete" heading is not proof of coverage. Skip a shorter
            # procedure only if each of its actual steps is present verbatim.
            return bool(steps) and all(normalize(step) in complete for step in steps)
        # Preserve explicitly approved withdrawal exceptions as qualifiers of
        # a source-described base fee. This never approves that base fee.
        if slot['topic_id']=='withdrawal' and 'withdrawal_discount' not in slot.get('modifiers',[]):
            chosen.extend(x for x in evidence[1:] if (x.get('approval') or {}).get('predicate')=='withdrawal_discount')
        # Complete procedures/requirements outrank a definition or heading.
        if slot['topic_id'] in ('activation','documents','workflow'):
            for x in evidence[1:]:
                if duplicate_partial_procedure(x):continue
                if x['unit'].get('prerequisite_role') or relevant_caveat(x['unit'],slot['topic_id'],slot.get('conditions',[])):
                    chosen.append(x)
        if slot['topic_id']=='documents':
            for x in evidence[1:]:
                if re.search(r'مستندات.{0,20}اضافيه|لا تحتاج مستندات|اوراق.{0,20}الزام|additional documents|proof of income',norm(x['unit']['heading'])):
                    chosen.append(x)
        if slot['topic_id']=='workflow':
            phases=set()
            for x in evidence:
                if not x['unit'].get('supports_complete_procedure'):continue
                if duplicate_partial_procedure(x):continue
                h=norm(x['unit'].get('rule_heading') or x['unit']['heading'])
                phase='before' if 'قبل' in h else 'after' if 'بعد' in h else 'execution' if re.search(r'ماكينه|سيستم|system|machine',h) else 'main'
                if phase not in phases:chosen.append(x);phases.add(phase)
        if any(relevant_caveat(x['unit'],slot['topic_id'],slot.get('conditions',[])) for x in evidence):
            chosen.extend(x for x in evidence if relevant_caveat(x['unit'],slot['topic_id'],slot.get('conditions',[])) and not duplicate_partial_procedure(x))
        unique=[];seen=set()
        for x in chosen:
            key=(x['unit']['source_sha256'],x['unit']['text_sha256'])
            if key not in seen:unique.append(x);seen.add(key)
        covered=set()
        for parent in unique:
            for relation in parent['unit'].get('covers_evidence',[]):
                for child in unique:
                    if (relation.get('topic_id')==slot['topic_id'] and
                            relation.get('review_kind')=='technical_source_equivalence_not_policy_approval' and
                            relation.get('unit_id')==child['unit']['unit_id'] and
                            relation.get('text_sha256')==child['unit']['text_sha256'] and
                            relation.get('source_sha256')==child['unit']['source_sha256']==parent['unit']['source_sha256']):
                        covered.add(child['unit']['unit_id'])
        return [x for x in unique if x['unit']['unit_id'] not in covered]

    def ask(self,question,debug=False,request_id=None):
        started=perf_counter();request=REQUEST.get() or {};original=request.get('question',question)
        cid,sid=request.get('conversation_id'),request.get('session_id')
        previous=self.conversations.get_business_context(cid,sid) if cid or sid else None
        if previous and previous.get('canonical_generation')!=self.projection.metadata['generation']:previous=None
        t=perf_counter();plan=self.planner.plan(original,previous);detection=(perf_counter()-t)*1000
        if plan.services and not plan.ambiguous and not plan.oversized and (cid or sid):
            self.conversations.set_business_context(cid,sid,{**plan.to_dict(),'canonical_generation':self.projection.metadata['generation']})
        result={'knowledge_generation':self.service.config.content_generation,'canonical_generation':self.projection.metadata['generation'],
            'sources':[],'reply_language':plan.language,'follow_up_detected':plan.inherited,'conversation_history_used':plan.inherited,
            'canonical':{'plan':plan.to_dict(),'slots':[],'timings_ms':{'service_topic_detection':detection},
                'model_calls':0,'translation_calls':0,'evidence_policy':'source_verified_RAG_is_distinct_from_operational_policy_approval'}}
        if re.search(r'chatbot',original,re.I) and re.search(r'article|مقال',original,re.I) and re.search(r'policy|سياس',original,re.I):
            return super().ask(question,debug,request_id)
        if plan.ambiguous or not plan.services or plan.oversized:
            text=('Please specify the service or narrow this comparison so I can check each rule separately.' if plan.language=='en'
                  else 'حدّد الخدمة أو ضيّق المقارنة علشان أراجع كل قاعدة بمصدرها.')
            return self.finish(result,text,'clarification','ambiguous_or_oversized_request',started)
        t=perf_counter();slots=[self.retriever.retrieve(s,original) for s in plan.slots]
        result['canonical']['timings_ms']['slot_retrieval']=(perf_counter()-t)*1000
        for index,slot in enumerate(slots,1):
            slot['slot_handle']='S'+str(index);slot['evidence']=self.choose(slot)
        available=[s for s in slots if s['evidence']]
        missing=[s for s in slots if not s['evidence'] or s['status']!='supported']
        # Safe source extraction is a normal current answer path. It preserves
        # complete verified rule units and makes no unnecessary Arabic rewrite.
        can_extract=plan.language!='en' and self.service.config.prefer_source_answers
        handles={};items={};bindings={};payload_evidence=[];payload_slots=[]
        for slot in available:
            refs=[]
            for item in slot['evidence']:
                unit=item['unit'];key=(slot['service_id'],unit['source_sha256'],unit['text_sha256'])
                if key not in handles:
                    handle='E'+str(len(handles)+1);handles[key]=handle;items[handle]=item
                    payload_evidence.append({'id':handle,'heading':unit.get('rule_heading') or unit['heading'],
                        'text':plain(unit['body']),'level':item['eligibility']['tier']})
                handle=handles[key];refs.append(handle)
                bindings[(slot['slot_handle'],handle)]=item
            slot['allowed_refs']=refs
            payload_slots.append({'id':slot['slot_handle'],'service':self.service_label(slot['service_id'],plan.language),
                                  'topic':slot['topic_id'],'refs':refs})
        outputs={};failure_reasons={}
        for slot in available:
            if all(x['eligibility']['operational_policy_approved'] and (x.get('approval') or {}).get(
                    'answer_en' if plan.language=='en' else 'answer_ar') for x in slot['evidence']):
                outputs[slot['slot_handle']]={'text':'\n'.join(x['approval']['answer_en' if plan.language=='en' else 'answer_ar']
                    for x in slot['evidence']),'refs':slot['allowed_refs'],'answer_path':'approved_structured_facts'}
        if can_extract:
            for slot in available:
                if slot['slot_handle'] in outputs:continue
                outputs[slot['slot_handle']]={'text':'\n\n'.join(
                    plain(x['unit'].get('rule_heading') or x['unit']['heading'])+'\n'+plain(x['unit']['body']) for x in slot['evidence']),
                    'refs':slot['allowed_refs'],'answer_path':'verified_source_extraction'}
        elif any(s['slot_handle'] not in outputs for s in available):
            t=perf_counter();included=[];included_evidence=[]
            terminology=source_glossary('\n'.join(e['text'] for e in payload_evidence))
            generation_system=SYSTEM+(' Passage-specific terminology (language equivalents, not additional rules): '+json.dumps(terminology,ensure_ascii=False) if terminology and plan.language=='en' else '')
            reserve=min(1536,max(384,sum(len(x['text'].split()) for x in payload_evidence)*3))
            groups={}
            for slot in payload_slots:
                if slot['id'] in outputs:continue
                key=(slot['service'],tuple(slot['refs']))
                if key not in groups:groups[key]={**slot,'covers':[slot['id']]}
                else:
                    groups[key]['covers'].append(slot['id'])
                    groups[key]['topic']+=', '+slot['topic']
            composed_slots=list(groups.values())
            # Include complete slot bundles, deduplicated across topics. Never
            # truncate an evidence unit or silently drop required conditions.
            for slot in composed_slots:
                wanted=set(slot['refs'])|{e['id'] for e in included_evidence}
                candidate_evidence=[e for e in payload_evidence if e['id'] in wanted]
                prompt=json.dumps({'language':plan.language,'question':original,'slots':included+[slot],
                    'evidence':candidate_evidence},ensure_ascii=False,separators=(',',':'))
                budget=(self.token_budget.measure(generation_system,prompt,self.service.config.generation_context_tokens,reserve)
                        if self.token_budget else {'fits':len((generation_system+prompt).encode())+256+reserve<=self.service.config.generation_context_tokens,
                            'method':'conservative_UTF8_byte_bound','prompt_token_upper_bound':len((generation_system+prompt).encode())+256,'output_reserve':reserve})
                if budget['fits']:included.append(slot);included_evidence=candidate_evidence
                else:
                    for alias in slot['covers']:failure_reasons[alias]='complete_rule_bundle_exceeds_context'
            result['canonical']['timings_ms']['prompt_construction']=(perf_counter()-t)*1000
            record_timing('canonical.prompt_construction_ms',result['canonical']['timings_ms']['prompt_construction'])
            if included:
                prompt=json.dumps({'language':plan.language,'question':original,'slots':included,'evidence':included_evidence},
                                  ensure_ascii=False,separators=(',',':'))
                if self.token_budget:result['canonical']['prompt_budget']=self.token_budget.measure(generation_system,prompt,self.service.config.generation_context_tokens,reserve)
                client=OllamaClient(replace(self.service.ollama_client.config,generation_max_tokens=reserve),self.service.logger)
                try:
                    t=perf_counter();response=client.generate_payload(prompt=prompt,system_prompt=generation_system,
                        timeout_seconds=45,response_format=response_schema(included))
                    result['canonical']['model_calls']=1
                    result['canonical']['model_metrics']={k:response.get(k) for k in ('prompt_eval_count','prompt_eval_duration','eval_count','eval_duration','done_reason')}
                    result['canonical']['generation_limits']={'num_predict':reserve,'num_ctx':self.service.config.generation_context_tokens,
                        'num_thread':self.service.config.generation_threads,'timeout_seconds':45}
                    raw=str(response.get('response') or '').strip()
                    if raw.startswith('```'):raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw)
                    generated=decode_slots(json.loads(raw),included)
                    seen=set()
                    for value in generated:
                        handle=value.get('slot');slot=next((s for s in available if s['slot_handle']==handle),None)
                        if not slot or handle in seen:continue
                        seen.add(handle);refs=value.get('refs') or []
                        source='\n'.join((bindings[(handle,r)]['unit'].get('rule_heading') or bindings[(handle,r)]['unit']['heading'])+'\n'+
                                         bindings[(handle,r)]['unit']['body'] for r in slot['allowed_refs'])
                        group=next((s for s in included if s['id']==handle),None)
                        if not group:continue
                        ok=True;reason=None
                        for alias in group['covers']:
                            member=next(s for s in available if s['slot_handle']==alias)
                            ok,reason=validate_slot(value.get('text'),source,plan.language,member['service_id'],self.planner,member['allowed_refs'],refs,member['topic_id'])
                            if not ok:break
                        for alias in group['covers']:
                            if ok and response.get('done_reason')!='length':outputs[alias]={'text':value['text'].strip(),'refs':refs,'answer_path':'one_grounded_language_generation'}
                            else:failure_reasons[alias]=reason or 'truncated_model_response'
                except Exception as exc:
                    # Error types only; never log payloads, prompts or messages.
                    result['canonical']['generation_error_type']=type(exc).__name__
                    for slot in included:
                        for alias in slot['covers']:failure_reasons[alias]='generation_unavailable'
                finally:
                    result['canonical']['model_calls']=1
                    result['canonical']['timings_ms']['model_api']=(perf_counter()-t)*1000
        paragraphs=[];render_groups={};answered=[]
        for slot in slots:
            handle=slot['slot_handle'];output=outputs.get(handle)
            diagnostic={k:v for k,v in slot.items() if k not in ('evidence','allowed_refs')}
            diagnostic['evidence_levels']=[e['eligibility'] for e in slot['evidence']]
            diagnostic['unit_ids']=[e['unit']['unit_id'] for e in slot['evidence']]
            diagnostic['answer_status']='answered' if output else 'review_required_or_unavailable'
            diagnostic['answer_failure_reason']=failure_reasons.get(handle)
            slot['answer_failure_reason']=failure_reasons.get(handle)
            result['canonical']['slots'].append(diagnostic)
            if not output:
                if slot not in missing:missing.append(slot)
                continue
            if not all(self.projection.source_current(e['unit']) for e in slot['evidence']):
                missing.append(slot);diagnostic['answer_status']='stale';continue
            answered.append(handle)
            key=(slot['service_id'],output['text'])
            if key not in render_groups:render_groups[key]={'topics':[],'refs':[]}
            render_groups[key]['topics'].append(self.topic_label(slot['topic_id'],plan.language))
            render_groups[key]['refs'].extend(output['refs'])
            for ref in output['refs']:
                item=bindings[(handle,ref)];unit=item['unit'];approval=item.get('approval') or {}
                result['sources'].append({'reference':ref,'unit_id':unit['unit_id'],'service_id':slot['service_id'],'topic_id':slot['topic_id'],
                    'source_name':unit['source_path'].split('/')[-1],'source_path':unit['source_path'],'source_sha256':unit['source_sha256'],
                    'text_sha256':unit['text_sha256'],'location_type':unit.get('location_type','lines'),'location_value':unit.get('location_value'),
                    'line_start':unit.get('line_start'),'line_end':unit.get('line_end'),
                    'source_segments':unit.get('source_segments'),'omitted_source_lines':unit.get('omitted_source_lines'),
                    'content_generation':self.service.config.content_generation,
                    'canonical_generation':self.projection.metadata['generation'],'approval_reference':approval.get('review_reference'),
                    'operational_policy_approved':item['eligibility']['operational_policy_approved'],
                    'evidence_tier':item['eligibility']['tier'],'anchor_chunk_id':item['anchor_chunk_id']})
        for (service_id,text),group in render_groups.items():
            name=self.service_label(service_id,plan.language)
            paragraphs.append(name+' / '+', '.join(dict.fromkeys(group['topics']))+'\n'+text+' '+
                              ' '.join('['+r+']' for r in dict.fromkeys(group['refs'])))
        if paragraphs:
            intro='According to the training material:\n\n' if plan.language=='en' else 'بحسب المادة التدريبية:\n\n'
            answer=intro+'\n\n'.join(paragraphs)
            if missing:answer+='\n\n'+self.gap_text(missing,plan.language)
            result['canonical']['answered_slots']=answered
            result['canonical']['missing_slots']=[s['slot_handle'] for s in missing]
            paths={output['answer_path'] for output in outputs.values()}
            result['canonical']['answer_path']='approved_structured_facts' if paths=={'approved_structured_facts'} else 'source_extraction' if can_extract else 'single_generation_requested_language'
            return self.finish(result,answer,'answer','partial_evidence' if missing else None,started)
        return self.finish(result,self.gap_text(missing or slots,plan.language),'review_required','no_verified_answer_for_requested_slots',started)

    def gap_text(self, slots, language, context=False):
        details=[]
        for slot in slots:
            label=self.service_label(slot['service_id'],language)+' / '+self.topic_label(slot['topic_id'],language)
            units=[e['unit'] for e in slot.get('evidence',[])]
            if slot.get('answer_failure_reason'):
                why=('a complete grounded rendering could not be verified' if language=='en' else 'تعذر التحقق من صياغة كاملة مدعومة بالمصدر')
            elif any(u.get('scope_caveat')=='provider_cash_in_cash_out_label_conflict' for u in units):
                why=('the provider-channel cash-in/cash-out labels conflict across the source rows; the ATM fact above is independently supported'
                    if language=='en' else 'تسمية عملية مقدم الخدمة متعارضة بين الإيداع والسحب في صفوف المصادر؛ معلومة ATM المذكورة مدعومة بشكل مستقل')
            elif slot.get('held_scope_conflicts'):
                why=('the sources do not establish one universal initial-period daily limit' if language=='en'
                    else 'المصادر لا تثبت حدًا يوميًا موحدًا لفترة الاستخدام الأولى')
            elif any(u.get('partial_procedure') and u.get('omitted_source_lines') for u in units) and slot['topic_id']=='workflow':
                why=('one identity-entry instruction requires review; it has not been applied to customer data' if language=='en'
                    else 'إحدى تعليمات إدخال بيانات الهوية تحتاج مراجعة؛ لم أطبقها على بيانات العميل')
            else:
                why=('the available verified material does not establish every requested detail' if language=='en'
                    else 'المادة الموثقة المتاحة لا تثبت كل التفاصيل المطلوبة')
            details.append(label+': '+why)
        prefix='Unresolved parts: ' if language=='en' else 'الأجزاء غير المحسومة: '
        return prefix+'; '.join(dict.fromkeys(details))

    @staticmethod
    def topic_label(topic,language):
        if language=='en':return topic.replace('_',' ')
        return {'deposit':'الإيداع','withdrawal':'السحب','activation':'التفعيل','registration':'التسجيل',
            'documents':'المستندات','workflow':'الخطوات','limits':'الحدود','transaction_codes':'كود الخدمة',
            'fees':'الرسوم','eligibility':'الشروط','risk_compliance':'الامتثال والمخاطر'}.get(topic,topic.replace('_',' '))
