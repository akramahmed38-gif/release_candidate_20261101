"""Attach a pure nominal response modifier to a clause-supported predicate.

No new language cues, evidence, services or question identifiers are introduced.
The planner and raw audit supply their own independently constructed requests;
this shared structural operation does not establish semantic independence.
"""
import re
from linguistic_spans import (
    _answer_scope_data, forms, mark, nominal_scalar_focus, tokens,
)

QUOTES = re.compile(r'“[^”]*”|«[^»]*»|"[^"\n]*"|‘[^’]*’')


def _pure_proof(raw, start, end, entities):
    if not 0 <= start < end <= len(raw):
        return None
    if any(m.start() < end and start < m.end() for m in QUOTES.finditer(raw)):
        return None
    text = raw[start:end]
    local_entities = [(a-start, b-start, sid) for a, b, sid in entities
                      if start <= a < b <= end]
    masked = list(text)
    for a, b, _ in local_entities:
        masked[a:b] = ' ' * (b-a)
    masked = ''.join(masked)
    data = _answer_scope_data()
    allowed = {form for key in ('modifiers', 'scalar_heads', 'focus_words', 'possessive_determiners')
               for phrase in data.get(key, []) for word in tokens(phrase) for form in forms(word)}
    if not all(forms(word) & allowed for word in tokens(masked)):
        return None
    proofs = nominal_scalar_focus(text, [(a, b) for a, b, _ in local_entities])
    if not proofs:
        return None
    return {
        'span': mark(raw, start, end, 'response_scope_modifier'),
        'focus_proofs': [
            {key: mark(raw, start+value['start'], start+value['end'], value['role'])
             for key, value in proof.items()} for proof in proofs
        ],
        'explicit_service_ids': sorted({sid for _, _, sid in local_entities}),
    }


def _predicate_key(request):
    # Shared original predicate spans identify a coordinated predicate. Mere
    # equality of intent or service labels cannot establish that coordination.
    support = tuple(sorted({(s['start'], s['end']) for s in request.get('evidence_spans', [])
                            if s.get('role') == 'requested_predicate'}))
    return request.get('intent_id'), support


def attach_scalar_scope(raw, requests, unresolved, entities=()):
    """Return unresolved obligations and auditable attachments; mutate facets.

    Only an already recognized minimum-funding predicate supports the existing
    amount-only projection. Different predicates, multiple distinct antecedent
    heads, quoted instructions and unknown residual tokens remain unresolved.
    No whole-question span is used as proof of an operation or field.
    """
    remaining, attachments = [], []
    for issue in unresolved:
        if issue.get('kind', issue.get('code')) not in {
            'predicate_unresolved', 'raw_predicate_unresolved'
        }:
            remaining.append(issue)
            continue
        span = issue.get('span') or {}
        proof = _pure_proof(raw, span.get('start', -1), span.get('end', -1), entities)
        if not proof:
            remaining.append(issue)
            continue
        parents = [r for r in requests if r.get('role') == 'requested'
                   and r.get('clause_span', {}).get('end', len(raw)+1) <= span['start']]
        named = set(proof['explicit_service_ids'])
        if named:
            parents = [r for r in parents if r.get('service_id') in named]
        # A modifier cannot silently jump over a nearer incompatible request.
        nearest_end = max((r['clause_span']['end'] for r in parents), default=-1)
        nearest = [r for r in parents if r['clause_span']['end'] == nearest_end]
        compatible = [r for r in parents if r.get('intent_id') == 'initial_funding']
        keys = {_predicate_key(r) for r in compatible}
        if (not nearest or any(r.get('intent_id') != 'initial_funding' for r in nearest)
                or len(keys) != 1 or not next(iter(keys))[1]
                or (named and named != {r.get('service_id') for r in compatible})):
            remaining.append(issue)
            continue
        # Unrecognized intervening content cannot acquire a known antecedent
        # merely because a previous funding request happens to be available.
        if any(other is not issue and other.get('span', {}).get('start', -1) >= nearest_end
               and other.get('span', {}).get('end', len(raw)+1) <= span['start']
               for other in unresolved):
            remaining.append(issue)
            continue
        edge = {**proof, 'facet': 'amount_only',
                'target_request_ids': [r['request_id'] for r in compatible],
                'basis': 'pure_nominal_scope_to_single_current_predicate_anchor'}
        for request in compatible:
            request['requested_facets'] = list(dict.fromkeys(request.get('requested_facets', []) + ['amount_only']))
            request.setdefault('answer_scope_modifiers', []).append(proof)
        attachments.append(edge)
    return remaining, attachments
