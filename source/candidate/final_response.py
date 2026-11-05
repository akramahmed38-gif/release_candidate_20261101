"""One final response decision after existing source and coverage checks.

This reducer does not interpret language or certify that the planner found every
meaning. It makes the decisions already produced by those gates explicit and
consistent. Unknown meanings omitted by both lexical paths remain a defect.
"""
from copy import deepcopy


def finalize_response(result, contract):
    evidence=result.get('evidence_contract') or {}
    coverage=result.get('question_coverage') or {}
    requests=contract.get('requests') or []
    unresolved=deepcopy(contract.get('unresolved_spans') or [])
    raw_acts=deepcopy(coverage.get('raw_question_act_inventory',{}).get('unresolved_acts') or [])
    for act in raw_acts:
        unresolved.append({'kind':'uninterpreted_question_act','span':act['span'],
                           'basis':'separate_original_question_act_inventory'})
    facts=list(result.get('supported_fact_ids') or [])
    classification=contract.get('task_mode',{}).get('mode')=='interpretation_only'
    reason=result.get('invalidation_reason')
    invalidated=list(result.get('invalidated_fact_ids') or [])
    # The existing source-snapshot gate can remove one changed slot while
    # retaining independent, rechecked slots. Global authorization/generation
    # revocation remains fatal; a partial source change must not erase siblings.
    subset_invalidation=(reason in {'source_changed_before_emission','question_scope_not_supported'}
                         and bool(invalidated) and not set(facts).intersection(invalidated))
    invalid=bool(result.get('contract_rejection') or (reason and not subset_invalidation))
    violations=any(evidence.get(k) for k in ('scope_violations','citation_violations','unrelated_fact_ids'))
    violations=violations or any(coverage.get(k) for k in ('excluded_fact_ids','unrelated_fact_ids'))
    convergence=coverage.get('fulfillment_convergence_applied') is True and coverage.get('complete_eligible') is True
    missing=deepcopy(coverage.get('missing_demands') or [])
    if subset_invalidation:
        missing.append({'code':reason,'invalidated_fact_ids':invalidated})
    conflicts=deepcopy(coverage.get('conflicts') or [])
    reviews=deepcopy(evidence.get('request_reviews') or [])
    actions=deepcopy(contract.get('forbidden_actions') or [])
    if invalid or violations:
        status='error'
        # A rejected binding must never survive as an asserted business claim.
        facts=[];result.update(supported_fact_ids=[],citations=[],slots=[])
        result['answer']=('The answer could not pass source and request verification; no business claim is emitted.'
                          if result.get('reply_language')=='en' else
                          'تعذر التحقق من ارتباط الإجابة بالطلب والمصدر؛ لم تصدر إجابة تتضمن أحكام الخدمة.')
    elif classification:
        status='complete' if requests and not unresolved else 'clarification_required'
        facts=[];result.update(supported_fact_ids=[],citations=[],slots=[])
    elif actions:
        status='partial' if facts else 'action_not_permitted'
    elif (result.get('complete') is True and facts and coverage.get('complete_eligible') is True
          and (evidence.get('complete') is True or convergence)
          and not missing and not conflicts and (not unresolved or convergence)):
        status='complete'
    elif facts:
        status='partial'
    elif unresolved or coverage.get('decision')=='clarify':
        status='clarification_required'
    elif conflicts:
        status='conflict'
    elif result.get('answer_status')=='live_lookup_required' or coverage.get('decision')=='live_lookup_required':
        status='live_lookup_required'
    else:
        status='unsupported'
    # Existing, independently verified fulfillment convergence may discharge a
    # conservative planner diagnostic. Preserve it in the audit, not as a new
    # clarification demand in an otherwise complete response.
    clarification=[] if status=='complete' else unresolved
    if raw_acts and not invalid and not violations:
        # Quote the unanswered part as input, never as a policy assertion.
        lead=('Additional question not yet interpreted; please clarify: '
              if result.get('reply_language')=='en' else
              '\u062c\u0632\u0621 \u0622\u062e\u0631 \u0645\u0646 \u0627\u0644\u0633\u0624\u0627\u0644 \u0644\u0645 \u064a\u062a\u0645 \u062a\u0641\u0633\u064a\u0631\u0647\u061b \u064a\u0631\u062c\u0649 \u062a\u0648\u0636\u064a\u062d\u0647: ')
        result['answer']=result.get('answer','').rstrip()+'\n\n'+lead+'; '.join('"'+act['span']['text']+'"' for act in raw_acts)
    needs_clarification=status=='clarification_required' or (status=='partial' and bool(clarification))
    legacy={'partial':'supported_partial','clarification_required':'clarify'}.get(status,status)
    result.update(complete=status=='complete',answer_status=legacy,clarification_needed=needs_clarification)
    if not needs_clarification:result.pop('clarification_dimensions',None)
    final={'schema_version':'final_response_1','status':status,'mode':'interpretation_only' if classification else 'business_answer',
           'complete':status=='complete','clarification_needed':needs_clarification,
           'requested_clauses':deepcopy(requests),'resolved_fact_ids':facts,
           'citations':deepcopy(result.get('citations') or []),'request_evidence_reviews':reviews,
           'unsupported_requested_parts':missing,'conflicts':conflicts,
           'clarifications':clarification,'forbidden_actions':actions,
           'answer':result.get('answer',''),
           'coverage_limitations':{'semantic_independence_claimed':coverage.get('semantic_independence_claimed',False),
                                   'unrecognized_meaning_recovery_proven':False},
           'prior_diagnostics':{'planner_unresolved':unresolved,'fulfillment_convergence_applied':convergence}}
    result['final_response']=final
    return final
