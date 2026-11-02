"""Current-turn task mode and final response contract; never business policy."""
import hashlib,re
from linguistic_spans import spans,tokens,mark

QUOTES=re.compile(r'“[^”]*”|«[^»]*»|"[^"\n]*"|‘[^’]*’')
MODE_ACTIONS=['classify','classification','routing','tag','صنف','صنّف','حدد','7added']
FOCUS=['only','فقط','بس','bas']
DIMENSIONS=['service','intent','الخدمة','المقصد','الخدمات','الطلبات']

def task_mode(raw):
    masked=list(raw)
    for m in QUOTES.finditer(raw):masked[m.start():m.end()]=' '*(m.end()-m.start())
    work=''.join(masked)
    actions=[(a,b,word) for word in MODE_ACTIONS for a,b in spans(work,word)]
    for a,b,word in actions:
        prefix=work[max(0,a-30):a]
        if any(spans(prefix,n) for n in ['do not','not','لا','مش']):continue
        focus=[p for w in FOCUS for p in spans(work,w) if abs(p[0]-a)<100]
        dims=[p for w in DIMENSIONS for p in spans(work,w)]
        explicit=bool(focus and (word not in ['حدد','7added'] or len(dims)>=2))
        if not explicit:continue
        # An explicit second request for operational answers is not swallowed
        # by a pure tagging mode. It remains in the ordinary mixed-task path.
        if re.search(r'\b(?:also|and then)\s+(?:answer|explain|tell)\b|وكمان\s+(?:جاوب|اشرح)',work,re.I):continue
        return {'mode':'interpretation_only','action_span':mark(raw,a,b,'task_action'),
                'focus_spans':[mark(raw,x,y,'response_scope') for x,y in focus],
                'business_answer_requested':False}
    return {'mode':'business_answer','business_answer_requested':True}


def classify_current(raw,planner,base,mode):
    """Bind catalog labels to each explicitly named entity, without examples.

    Longest overlapping label wins; equal-span ambiguity stays unresolved.
    Unrelated entity clauses never inherit a previous entity's predicate.
    This is lexical interpretation, not semantic or source-policy approval.
    """
    entities=planner.entities(raw)
    entities=[e for e in entities if not any(o['start']<=e['start'] and e['end']<=o['end'] and o['end']-o['start']>e['end']-e['start'] for o in entities)]
    entities=sorted(entities,key=lambda r:(r['start'],-r['end']))
    grouped={}
    for e in entities:grouped.setdefault((e['start'],e['end']),[]).append(e)
    groups=sorted(grouped.items());requests=[];unresolved=[]
    for index,((start,end),owners) in enumerate(groups):
        stop=groups[index+1][0][0] if index+1<len(groups) else len(raw)
        text=raw[end:stop]; candidates=[]
        if len({e['service_id'] for e in owners})!=1:
            unresolved.append({'kind':'ambiguous_service_name','span':mark(raw,start,end,'unresolved')});continue
        service=owners[0]['service_id']
        for row in planner.intents:
            iid=row['intent_id']
            if iid in {'other_or_unknown','permission','explanation'}:continue
            cues=[iid.replace('_',' ')]+[cue for key in ['en_cues','ar_eg_cues','ar_msa_cues','franco_eg_cues'] for cue in row.get(key,[])]
            for cue in cues:
                for a,b in spans(text,cue):
                    # One-word cues need an explicit nominal field, not a
                    # hidden verb within a larger operator or entity name.
                    if len(tokens(cue))==1 and cue!=iid.replace('_',' '):continue
                    candidates.append((end+a,end+b,iid))
        longest=[p for p in candidates if not any(q[0]<=p[0] and p[1]<=q[1] and q[1]-q[0]>p[1]-p[0] for q in candidates)]
        amb={p for p in longest if any(q[:2]==p[:2] and q[2]!=p[2] for q in longest)}
        accepted=sorted(set(longest)-amb)
        if not accepted:
            unresolved.append({'kind':'classification_predicate_unresolved','service_id':service,'span':mark(raw,end,stop,'unresolved')})
        if amb:unresolved.append({'kind':'classification_predicate_ambiguous','service_id':service,'span':mark(raw,end,stop,'unresolved')})
        for a,b,iid in accepted:
            if any(r['service_id']==service and r['intent_id']==iid for r in requests):continue
            channels=[h['channel'] for h in planner.channel_hits(text)]
            requests.append({'request_id':'T'+str(len(requests)+1),'service_id':service,'intent_id':iid,
                'topic':planner.adapter.get(iid,{}).get('topic',iid),'channels':list(dict.fromkeys(channels)),
                'conditions':[],'period':None,'requested_facets':[],'role':'requested','mode':'classify',
                'procedure_scope':None,'evidence_spans':[mark(raw,a,b,'requested_label')],
                'clause_span':mark(raw,start,stop,'classification_clause'),'commit_basis':'current_entity_catalog_label'})
    if not groups:unresolved.append({'kind':'service_unresolved','span':mark(raw,0,len(raw),'unresolved')})
    contract=base['request_contract'];contract['business_planner_diagnostic_requests']=contract['requests']
    contract.update(requests=requests,unresolved_spans=unresolved,decision='classify_only',task_mode=mode)
    base.update(services=list(dict.fromkeys(r['service_id'] for r in requests)),topics=list(dict.fromkeys(r['topic'] for r in requests)),
                slots=[],slot_conditions={},slot_periods={},conditions=[],result_mode='interpretation_only')
    return base


def scalar_view(fact,language):
    """Extract a literal qualified amount, bound to its immutable parent view.

    Only an existing single minimum-deposit field with no additional policy
    scope is eligible. No generated translation, new quantity or approval.
    """
    scope=fact.get('scope',{})
    if not set(scope)<= {'minimum_initial_deposit_egp','timing'}:return None
    value=scope.get('minimum_initial_deposit_egp')
    if type(value) not in (int,float):return None
    key='english' if language=='en' else 'arabic';text=fact[key]
    pattern=(r'(?:a minimum of|at least)\s+(\d+(?:\.\d+)?)\s+EGP' if language=='en' else
             r'(?:حد أدنى[\s:*]*\d+\s+جنيه(?:\*\*)?|\d+\s+جنيه\s+كحد أدنى)')
    hits=list(re.finditer(pattern,text,re.I))
    if len(hits)!=1:return None
    m=hits[0];numbers=re.findall(r'\d+(?:\.\d+)?',m.group())
    if len(numbers)!=1 or float(numbers[0])!=value:return None
    return {'text':m.group(),'start':m.start(),'end':m.end(),'parent_view_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_sha256':fact['source_sha256'],'field':'minimum_initial_deposit_egp','projection':'literal_parent_view_span','test_only':True}


def finalize(result,contract,facts,definition):
    """One presentation state after all source/generation eligibility rechecks."""
    if result.get('invalidation_reason') or result.get('contract_rejection'):return
    lang=result['reply_language'];english=lang=='en'
    if contract.get('task_mode',{}).get('mode')=='interpretation_only':
        complete=bool(contract['requests']) and not contract['unresolved_spans']
        result.update(type='interpretation',complete=complete,supported_fact_ids=[],citations=[],slots=[],
            answer_status='complete' if complete else 'clarify',clarification_needed=not complete,
            resolution_status='classification_complete' if complete else 'classification_incomplete',
            business_answer_coverage=False,response_mode='interpretation_only')
        labels=[r['service_id']+' / '+r['intent_id']+(' / '+','.join(r['channels']) if r['channels'] else '') for r in contract['requests']]
        result['answer']=('Request classification only; no business rules asserted.' if english else 'تصنيف الطلبات فقط؛ لا تتضمن الإجابة أحكام خدمات.')+'\n'+'\n'.join(labels)
        if not complete:result['answer']+='\n'+('Please clarify the unresolved service or intent.' if english else 'يرجى توضيح الخدمة أو المقصد غير المحسوم.')
        result['business_audit_not_applicable']=result['question_coverage']
        result['question_coverage']={'decision':result['answer_status'],'complete_eligible':complete,'scope':'interpretation_only_not_business_coverage','unresolved_spans':contract['unresolved_spans']}
        return
    if not result.get('complete'):return
    proof=result.get('evidence_contract',{})
    if any(proof.get(k) for k in ['scope_violations','citation_violations','unrelated_fact_ids']):return
    # Rendering from admitted immutable views removes stale intermediate
    # clarification prose, rather than deleting arbitrary answer clauses.
    result['presentation_reconciliation']={'prior_resolution_status':result.get('resolution_status'),
        'prior_clarification_needed':result.get('clarification_needed'),'planner_unresolved':contract['unresolved_spans']}
    result.update(answer_status='complete',clarification_needed=False,resolution_status='complete_scoped_answer')
    result.pop('clarification_dimensions',None)
    views={};projections={}
    for fid in result['supported_fact_ids']:
        f=facts[fid];relevant=[r for r in contract['requests'] if r['service_id']==f['service_id'] and r['topic'] in f['selection_tags']]
        narrow=bool(relevant) and all('amount_only' in r.get('requested_facets',[]) for r in relevant)
        projected=scalar_view(f,lang) if narrow else None
        views[fid]=projected['text'] if projected else f['english' if english else 'arabic']
        if projected:projections[fid]=projected
    result['rendered_view_projections']=projections
    groups=[]
    for service in dict.fromkeys(facts[fid]['service_id'] for fid in result['supported_fact_ids']):
        groups.append(definition['service_profiles'][service]['name']+':\n'+'\n'.join(views[fid] for fid in result['supported_fact_ids'] if facts[fid]['service_id']==service))
    banner='UNAPPROVED TEST FIXTURE — approvals pending.' if english else 'اختبار معزول غير معتمد؛ الموافقات معلقة.'
    scope='Only the selected source references are covered; this is not a complete eligibility checklist or end-to-end service procedure.' if english else 'الإجابة محددة بالمراجع المتاحة، وليست قائمة كاملة بشروط الفتح أو إجراءات الخدمة.'
    result['answer']='\n\n'.join([banner]+groups+[scope])
