"""Immutable language-handler registration, separate from policy mappings."""
from pathlib import Path
from functools import lru_cache
import json

@lru_cache(maxsize=1)
def compositional_fallback_exemptions():
    root=Path(__file__).resolve().parent
    registry=json.loads((root/'resources/predicate_ownership.json').read_text(encoding='utf8'))
    if registry.get('schema_version')!='predicate_ownership_1':raise ValueError('Unsupported predicate ownership registry')
    values=registry.get('catalog_fallback_exempt_intents')
    known={r['intent_id'] for r in json.loads((root/'resources/intents.json').read_text(encoding='utf8'))['intents']}
    if not isinstance(values,list) or not values or any(not isinstance(v,str) or v not in known for v in values) or len(values)!=len(set(values)):
        raise ValueError('Invalid compositional predicate ownership')
    return frozenset(values)
