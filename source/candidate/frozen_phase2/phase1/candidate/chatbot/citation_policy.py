"""Developer-controlled citation provenance; no model calls or invented references."""
import json
from pathlib import Path

from .content_state import StaleSourceFilter, read_active_generation


def load_policy(root):
    path = Path(root) / 'chatbot_citations.json'
    value = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    enabled = value.get('enabled', False)
    minimum = value.get('min_references', 1)
    if type(enabled) is not bool or type(minimum) is not int or not 1 <= minimum <= 5:
        raise ValueError('Invalid developer citation settings')
    return enabled, minimum


def _apply_citation_policy(response, root, source_root=None):
    source_root=Path(source_root or root)
    if not isinstance(response, dict):
        return response
    result = dict(response)
    if result.get('canonical',{}).get('application_policy_response'):
        return {**result,'sources':[],'primary_source':None,'supporting_sources':[],
                'citations_enabled':True,'citation_status':'application_boundary_no_business_claim'}
    enabled, minimum = load_policy(root)
    result['citations_enabled'] = enabled
    if not enabled:
        for key in ('sources', 'supporting_sources'):
            result[key] = []
        result['primary_source'] = None
        return result
    # Smalltalk and clarification have no factual source requirement.
    if result.get('type') == 'clarification' or result.get('fallback_used') or result.get('smalltalk_handled') or result.get('smalltalk_type'):
        result.update(sources=[], primary_source=None, supporting_sources=[], citation_status='not_applicable')
        return result
    active = read_active_generation(root)
    requested_generation = result.get("knowledge_generation")
    if requested_generation and (not active or active[0] != requested_generation):
        raise ValueError("Knowledge changed during answer; retry with current evidence")
    valid = []
    seen = set()
    if active:
        generation, _, manifest = active
        catalog = {row['path']: row for row in manifest.get('files', [])}
        stale = StaleSourceFilter(root, generation)
        stale.refresh()
        vocabulary = None
        for source in result.get('sources', []) or []:
            if not isinstance(source, dict):
                continue
            path = str(source.get('source_path', '')).replace('\\', '/')
            if path in seen or not stale.allows({'source_path': path}):
                continue
            if path.startswith('BusinessVocabulary/'):
                from .content_catalog import read_vocabulary, vocabulary_hash
                if vocabulary is None:
                    rows = read_vocabulary(source_root.parent / 'databases/hr_learning_system.db')
                    vocabulary = {str(row['id']) for row in rows} if vocabulary_hash(rows) == manifest.get('vocabulary_hash') else set()
                if path.split('/', 1)[1] not in vocabulary:
                    continue
            else:
                row = catalog.get(path)
                if not row or row.get('status') != 'ready':
                    continue
                target = (source_root / path).resolve()
                target.relative_to(source_root.resolve())
                try:
                    info = target.stat()
                except OSError:
                    continue
                if source.get('source_sha256') and source['source_sha256'] != row.get('sha256'):
                    continue
                if info.st_size != row.get('size') or info.st_mtime_ns != row.get('mtime_ns'):
                    continue
            seen.add(path)
            valid.append({**source, 'content_generation': generation, 'provenance_verified': True})
    if len(valid) < minimum:
        # Do not pad references with irrelevant material to meet a configured minimum.
        result.update(answer='\u0644\u0645 \u0623\u062a\u0645\u0643\u0646 \u0645\u0646 \u062a\u0648\u062b\u064a\u0642 \u0645\u0635\u0627\u062f\u0631 \u062d\u062f\u064a\u062b\u0629 \u0643\u0627\u0641\u064a\u0629. \u064a\u0631\u062c\u0649 \u062a\u0648\u0636\u064a\u062d \u0627\u0644\u0633\u0624\u0627\u0644.',
                      sources=[], primary_source=None, supporting_sources=[], fallback_used=True,
                      type='clarification', citation_status='insufficient_current_sources')
        # Localization happens immediately after this policy.
        return result
    result.update(sources=valid, primary_source=valid[0], supporting_sources=valid[1:],
                  citation_status='provenance_verified', citation_min_references=minimum)
    return result


def apply_citation_policy(response, root, source_root=None):
    try:
        return _apply_citation_policy(response, root,source_root)
    except Exception:
        if not isinstance(response, dict):
            return response
        return {**response, 'answer': 'Current source verification is unavailable. Please try again later.',
                'sources': [], 'primary_source': None, 'supporting_sources': [],
                'fallback_used': True, 'type': 'clarification', 'citation_status': 'verification_unavailable'}
