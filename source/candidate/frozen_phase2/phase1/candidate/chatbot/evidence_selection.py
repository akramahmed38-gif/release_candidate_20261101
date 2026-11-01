"""Prefer complete topic-specific rules and preserve unresolved scope holds."""
import re
from .canonical_context import TOPICS,norm,mentions

TRANSACTIONS={'deposit','withdrawal','activation','registration','limits','fees','documents','workflow','transaction_codes'}

def relevant_caveat(unit,topic,conditions=()):
    if not unit.get('scope_caveat'):return False
    exempt=set(unit.get('caveat_exempt_conditions',[]))
    channels=set(conditions)&{'atm','branch'}
    if channels and channels<=exempt:return False
    if unit.get('partial_procedure') and unit.get('omitted_source_lines'):
        # The withheld identity-entry instruction is a procedure gap. It does
        # not make an independently supported service code unknowable.
        return topic=='workflow'
    return True

def topic_heading(unit):
    heading=norm(unit.get('rule_heading') or unit.get('heading',''))
    if unit.get('verification')=='reviewed_repair' and not any(
            mentions(heading,a) for aliases in TOPICS.values() for a in aliases):
        # A verified repaired page may have a generic "Page 1" label. Its
        # reviewed rule heading, before the first colon, supplies its scope.
        heading=norm(unit['body'].split('\n')[0].split(':',1)[0])
    return heading

def topic_support(unit,topic,modifiers=()):
    heading=topic_heading(unit)
    direct=any(mentions(heading,a) for a in TOPICS.get(topic,()))
    if topic=='workflow':direct=bool(unit.get('supports_complete_procedure'))
    if topic=='documents' and unit.get('document_inventory_view'):direct=True
    if topic=='activation' and 'requirements' in modifiers:
        direct=direct and bool(re.search(r'شرط|شروط|قبل|متطلبات|مستند|حد ادني|حد ادنى|عند ايداع|\bminimum\b|\bat least\b|\bmust\b|\brequir',norm(unit['body'])))
    return direct

def topic_rank(item,topic):
    unit=item['unit'];heading=topic_heading(unit)
    other=sum(any(mentions(heading,a) for a in TOPICS[t]) for t in TRANSACTIONS if t!=topic)
    # Prefer an exact limits section to a "limits and fees" summary. This
    # changes selection order, not candidate counts or validation thresholds.
    specific=0 if any(mentions(heading,a) for a in TOPICS.get(topic,())) else 2
    if topic=='documents':
        inventory=bool(re.search(r'(?:اوراق|مستندات|documents).{0,30}(?:مطلوب|الزام|requir)|(?:مطلوب|الزام|requir).{0,30}(?:اوراق|مستندات|documents)',heading))
        incidental=bool(re.search(r'ارفع|توقيع|تواريخ|signature|upload|dates?',heading))
        specific=0 if inventory or unit.get('document_inventory_view') else 2 if incidental else 1
    if topic=='workflow' and re.search(r'كامله|كامل|complete|full',heading):specific=-1
    workflow_role=0
    if topic=='workflow':
        # A broad workflow tag also labels outcome explanations. Prefer actual
        # procedural navigation/numbered steps, without declaring completeness.
        body=norm(unit['body'])
        procedural=bool(re.search(r'خطوات|ثم|اتبع|اتباع|افتح|يتم فتح|\bsteps?\b|\bthen\b',body))
        outcome=bool(re.search(r'لماذا|ليه|\bwhy\b',heading))
        workflow_role=0 if procedural and not outcome else 2 if outcome else 1
    return (workflow_role,not item.get('direct_support'),specific,other,-unit.get('extraction_priority',1),-item['score'],unit['unit_id'])

def reconcile_uncertain_scopes(items,topic):
    if topic!='limits':return items,[]
    uncertain=[i for i in items if i['unit'].get('scope_caveat') and
               re.search(r'لا يمكن استخراج حد|cannot.{0,30}single|range.{0,30}uncertain',norm(i['unit']['body']))]
    if not uncertain:return items,[]
    kept=[];held=[]
    for item in items:
        unit=item['unit'];text=norm(unit['body'])
        same_service=any(set(unit.get('service_ids',[])) & set(u['unit'].get('service_ids',[])) for u in uncertain)
        if same_service and item not in uncertain and re.search(r'(?:اول|first)\s*3\s*(?:شهور|اشهر|months)',text):
            # An unqualified summary cannot resolve a source's explicitly
            # uncertain first-period limit. Do not assert both as one policy.
            held.append({'unit_id':unit['unit_id'],'source_path':unit['source_path'],
                'source_sha256':unit['source_sha256'],'reason':'unresolved_universal_summary_of_explicitly_uncertain_period'})
        else:kept.append(item)
    return kept,held
