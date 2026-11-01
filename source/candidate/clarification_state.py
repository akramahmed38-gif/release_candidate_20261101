"""Resume a user's pending request only after explicit service clarification.

No defaults, facts, approvals or test IDs. Original request text and reply
spans remain separate; source/coverage validation still processes the request.
"""
import hashlib
from linguistic_spans import tokens,mark


def pending_service_request(question,contract,turn):
    requests=contract.get('requests',[]);unresolved=contract.get('unresolved_spans',[])
    if (not requests or not unresolved
            or any(u.get('kind')!='service_unresolved' for u in unresolved)
            or any(r.get('service_id') is not None or r.get('role')!='requested'
                   or r.get('unsupported_named_provider') for r in requests)
            or contract.get('excluded_requests') or contract.get('user_claims')):
        return None
    return {'question':question,'sha256':hashlib.sha256(question.encode()).hexdigest(),
            'turn_id':str(turn),'intent_ids':sorted({r['intent_id'] for r in requests}),
            'authority':'original_user_request_not_business_evidence'}


def service_reply(question,pending,planner):
    if not isinstance(pending,dict):return None
    original=pending.get('question')
    if not isinstance(original,str) or hashlib.sha256(original.encode()).hexdigest()!=pending.get('sha256'):return None
    entities=planner.entities(question)
    services={e['service_id'] for e in entities if e.get('entity_role','service')=='service'}
    if len(services)!=1 or not entities:return None
    service=next(iter(services))
    if service not in planner.definition['service_profiles']:return None
    residual=list(question)
    for entity in entities:
        if entity['service_id']!=service:return None
        residual[entity['start']:entity['end']]=' '*(entity['end']-entity['start'])
    # Only a provider-identification utterance can fill the missing service.
    # New predicates, negation, quantities and competing providers stay new turns.
    grammar=set(tokens('I mean meant the service wallet actually specifically أقصد اقصد قصدي أعني اعني المحفظة الخدمة'))
    if not set(tokens(''.join(residual)))<=grammar:return None
    return {'service_id':service,'reply':question,
            'service_spans':[mark(question,e['start'],e['end'],'explicit_service_reply') for e in entities],
            'pending_turn_id':pending['turn_id'],'pending_question_sha256':pending['sha256'],
            'authority':'explicit_current_user_service_binding_only'}
