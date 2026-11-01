"""Transport user request scope across licensed dialogue ellipsis, never facts."""
from copy import deepcopy
import re


def additive_provider_reference(question, entity_spans):
    """An additive cue plus named entities; a bare brand is insufficient."""
    if not entity_spans:
        return False
    masked=list(question)
    for start,end in entity_spans:
        masked[start:end]=' '*(end-start)
    return bool(re.fullmatch(r'\s*(?:and(?:\s+also)?|also|و|w)\s*[?؟.!]*\s*',
                             ''.join(masked),re.I))


def antecedent_scope(previous, intent, target_service):
    """Select a unique typed view; never choose arbitrary conflicting scope."""
    records=[row for row in previous.get('request_references',[])
             if isinstance(row,dict) and row.get('intent_id')==intent]
    direct=[row for row in records if row.get('service_id')==target_service]
    if direct:
        records=direct
    keys=('channels','conditions','period','procedure_scope','requested_facets')
    signatures=[]
    for row in records:
        view={key:deepcopy(row.get(key)) for key in keys if row.get(key) is not None}
        if view not in signatures:
            signatures.append(view)
    if len(signatures)!=1:
        return None
    return {'scope':signatures[0], 'turn_id':previous.get('turn_id'),
            'source_services':list(dict.fromkeys(row.get('service_id') for row in records)),
            'request_ids':[row.get('request_id') for row in records],
            'raw_question':previous.get('raw_question'),
            'prior_scope_bindings':[deepcopy(row['inherited_scope']) for row in records if row.get('inherited_scope')],
            'evidence_spans':[deepcopy(span) for row in records for span in row.get('evidence_spans',[])]}
