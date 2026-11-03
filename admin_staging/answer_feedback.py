"""Owner-scoped diagnostic snapshots; never authentication or approval records."""
import hashlib
import json
import re
import time
import uuid
from catalog_store import db, put

IDENTIFIER = re.compile(r'trace-[a-f0-9]{32}')
REDACTIONS = [
    re.compile(r'(?i)\b(?:password|passwd|token|secret|api[_ -]?key|authorization)\s*[:=]\s*\S+'),
    re.compile(r'(?i)\bbearer\s+\S+'),
    re.compile(r'(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}'),
    re.compile(r'(?<!\d)(?:\d[ -]?){10,16}(?!\d)'),
    re.compile(r'(?:كلمة\s*(?:المرور|السر)|رمز الدخول)\s*[:=]\s*\S+'),
]


def redact(value, limit=12000):
    text = str(value or '')
    for pattern in REDACTIONS:
        text = pattern.sub('[REDACTED]', text)
    return text[:limit]


def owner(actor):
    identity = actor.get('sub') or actor.get('email') or actor.get('username')
    if not identity or identity == 'anonymous':
        raise PermissionError('Authenticated actor required')
    return hashlib.sha256(str(identity).encode()).hexdigest()


def capture(payload, result, actor):
    trace_id = 'trace-' + uuid.uuid4().hex
    # Explicit whitelist: no raw HTTP headers, cookies, tokens, environment,
    # arbitrary model output keys or private endpoint/credential paths.
    citations = [{k: c[k] for k in ('fact_id', 'source_document', 'source_sha256', 'locator') if k in c}
                 for c in result.get('citations', [])]
    requests = [{k: r[k] for k in ('service_id', 'intent_id', 'topic', 'channels', 'role', 'requested_facets') if k in r}
                for r in result.get('request_contract', {}).get('requests', [])]
    data = {'trace_id': trace_id, 'at': time.time(), 'owner': owner(actor),
            'question': redact(payload.get('question')), 'answer': redact(result.get('answer')),
            'knowledge_mode': payload.get('knowledge_mode'),
            'backend': result.get('backend'), 'native_acceptance': 'NOT RUN',
            'answer_status': result.get('answer_status'), 'complete': result.get('complete'),
            'fact_ids': result.get('supported_fact_ids', []), 'citations': citations,
            'requests': requests, 'worker_wall_ms': result.get('worker_wall_ms'),
            'resource_wait_ms': result.get('worker_resource_wait_ms'),
            'normal_runtime_eligible': False,
            'redaction_notice': 'Pattern-based redaction; do not submit secrets or personal data. Not a universal PII guarantee.'}
    # Apply redaction to all string leaves, including nested source metadata.
    def scrub(v):
        if isinstance(v, str): return redact(v)
        if isinstance(v, list): return [scrub(x) for x in v]
        if isinstance(v, dict):
            return {k: x if k in {'source_sha256', 'owner', 'trace_id', 'fact_id'} else scrub(x)
                    for k, x in v.items()}
        return v
    data = scrub(data)
    with db() as c:
        put(c, 'answer_trace', trace_id, '1', data)
    return trace_id


def read(trace_id, actor):
    if not IDENTIFIER.fullmatch(trace_id): raise LookupError('Trace unavailable')
    with db() as c:
        row = c.execute("select data from record where kind='answer_trace' and id=? and version='1'", (trace_id,)).fetchone()
    if not row: raise LookupError('Trace unavailable')
    value = json.loads(row['data'])
    if value['owner'] != owner(actor): raise LookupError('Trace unavailable')
    return {k: v for k, v in value.items() if k != 'owner'}


def report(trace_id, note, actor):
    read(trace_id, actor)
    report_id = 'feedback-' + uuid.uuid4().hex
    value = {'report_id': report_id, 'trace_id': trace_id, 'note': redact(note, 2000),
             'at': time.time(), 'owner': owner(actor), 'status': 'open',
             'policy_approval': False}
    with db() as c:
        put(c, 'answer_feedback', report_id, '1', value)
        c.execute('insert into event(at,kind,target,data) values(?,?,?,?)',
                  (time.time(), 'answer_feedback_submitted', report_id,
                   json.dumps({'trace_id': trace_id, 'actor_hash': owner(actor), 'no_approval': True})))
    return {k: v for k, v in value.items() if k != 'owner'}


def listing(actor):
    with db() as c:
        values = [json.loads(r['data']) for r in c.execute("select data from record where kind='answer_feedback' order by rowid desc")]
    return [{k: v for k, v in r.items() if k != 'owner'} for r in values if r['owner'] == owner(actor)][:100]


def export(trace_id, actor):
    value = read(trace_id, actor)
    return {'environment': 'isolated_admin_staging', 'trace': value,
            'feedback': [r for r in listing(actor) if r['trace_id'] == trace_id],
            'export_is_not_policy_approval': True}
