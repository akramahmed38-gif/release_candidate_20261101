"""Read-only canonical projection with independent source and approval gates."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
import threading


class CanonicalStore:
    def __init__(self, path, source_root, base_generation, expected_sha256):
        self.path = Path(path).resolve(); self.source_root = Path(source_root).resolve()
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError('Canonical projection fingerprint mismatch')
        with self.connect() as c:
            self.metadata = {k:json.loads(v) for k,v in c.execute('SELECT key,value FROM metadata')}
            self.profiles = {k:json.loads(v) for k,v in c.execute('SELECT service_id,payload FROM profiles')}
        if self.metadata.get('base_generation') != base_generation:
            raise ValueError('Canonical projection and repaired generation are incompatible')
        if self.metadata.get('schema') != 'canonical-eligible-v1':
            raise ValueError('Canonical projection schema is incompatible')
        self._stamps = {}; self._lock = threading.Lock()

    def connect(self):
        return closing(sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=2))

    def source_current(self, unit):
        rel = unit['source_path'].replace('\\','/')
        try:
            path = (self.source_root/rel).resolve(); path.relative_to(self.source_root)
            if rel.split('/')[0] not in ('KnowledgeBase','material','daily_brief'): return False
            stat = path.stat(); stamp = (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            with self._lock: cached = self._stamps.get(rel)
            if cached is None or cached[0] != stamp:
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                with self._lock: self._stamps[rel] = (stamp,sha)
            else: sha = cached[1]
            return sha == unit['source_sha256']
        except (OSError,ValueError): return False

    def candidates(self, service, topic):
        with self.connect() as c:
            rows = c.execute('SELECT u.payload,a.payload FROM unit_scope s JOIN units u ON u.unit_id=s.unit_id '
                'LEFT JOIN approvals a ON a.unit_id=u.unit_id WHERE s.service_id=? AND s.topic_id=?',
                (service,topic)).fetchall()
        return [(json.loads(u),json.loads(a) if a else None) for u,a in rows]

    def _approved_scope(self, unit, approval, slot):
        if not self.source_current(unit): return 'stale'
        if unit['verification'] not in ('exact_source_lines','reviewed_repair','exact_source_and_explicit_owner_confirmation'):
            return 'quarantined'
        if unit.get('requires_policy_review'): return 'review_required'
        if not approval or unit.get('serve_automatically') is not True: return 'review_required'
        if approval.get('approval_status') != 'approved_current' or not approval.get('business_owner'):
            return 'review_required'
        if (approval.get('source_sha256') != unit['source_sha256'] or
            approval.get('text_sha256') != hashlib.sha256(unit['body'].encode()).hexdigest() or
            approval.get('service_id') != slot['service_id'] or approval.get('topic_id') != slot['topic_id']):
            return 'review_required'
        if approval.get('predicate') not in slot.get('modifiers',[]):
            # A discount approval does not approve a base fee or a complete
            # withdrawal procedure. Never universalize its approval scope.
            return 'review_required'
        if set(slot.get('modifiers',[])) & {'base_fees','aggregate_channel_rule'}:
            return 'review_required'
        channels = set(slot.get('conditions',[])) & {'atm','branch'}
        if channels and approval.get('channel') not in channels: return 'scope_mismatch'
        if set(slot.get('conditions',[])) & {'daily','high_risk'}: return 'scope_mismatch'
        return 'supported'

    def eligibility(self, unit, approval, slot):
        from .evidence_eligibility import assess_unit
        current=self.source_current(unit)
        approved=current and self._approved_scope(unit,approval,slot)=='supported'
        return assess_unit(unit,slot,current,approved_scope=approved)

    def gate(self, unit, approval, slot):
        result=self.eligibility(unit,approval,slot)
        if result.eligible:return 'supported'
        return 'stale' if result.reason=='stale_or_removed_source' else 'review_required'

    def discovery_links(self, service, topic, limit=16):
        # Relationships navigate a catalog; callers may not take the other
        # service's content as support for the requested service.
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute(
                'SELECT payload FROM relationships WHERE (subject=? OR object=?) AND topic_id=? LIMIT ?',
                (service,service,topic,min(limit,16)))]

    def pending_locators(self, service, topic):
        with self.connect() as c:
            return [json.loads(r[0]) for r in c.execute(
                'SELECT payload FROM review_reference WHERE service_id=? AND topic_id=?', (service,topic))]
