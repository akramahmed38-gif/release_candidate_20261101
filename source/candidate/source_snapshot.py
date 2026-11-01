"""Drop whole invalidated evidence slots, retaining independent verified views."""
import hashlib
from evidence_contracts import approve_view
from chatbot.reference_validation import scoped_numeric_checks

def preserve_valid_slots(result,stale_sources,facts,definition,invalid_fact_ids=(),reason='source_changed_before_emission'):
    stale=set(stale_sources);bad={fid for fid in result['supported_fact_ids'] if facts[fid]['source_document'] in stale}|set(invalid_fact_ids)
    slots=result.get('slots',[])
    changed=True
    while changed:
        before=set(bad)
        for slot in slots:
            ids=set(slot.get('supported_fact_ids',[]))
            if ids&bad:bad|=ids
        for fid in result['supported_fact_ids']:
            if set(facts[fid].get('dependencies',[]))&bad:bad.add(fid)
        changed=bad!=before
    good=[fid for fid in result['supported_fact_ids'] if fid not in bad]
    lang=result['reply_language'];view_key='english' if lang=='en' else 'arabic'
    authorized=definition['authorized_test_ids']
    for fid in list(good):
        f=facts[fid]
        if not approve_view(f,lang,None,fixture_mode=True,authorized_fixture_ids=authorized) or not scoped_numeric_checks(f['arabic'],f['english'],f['validation_topic'])[0]:
            raise ValueError('Source snapshot view changed or validator rejected')
    for slot in slots:
        if set(slot.get('supported_fact_ids',[]))&bad:
            slot.update(supported_fact_ids=[],complete=False,gap_reasons=[reason])
    groups=[]
    for service in dict.fromkeys(facts[fid]['service_id'] for fid in good):
        ids=[fid for fid in good if facts[fid]['service_id']==service]
        groups.append(definition['service_profiles'][service]['name']+':\n'+'\n'.join(facts[fid][view_key] for fid in ids))
    banner='UNAPPROVED TEST FIXTURE — approvals pending.' if lang=='en' else 'اختبار معزول غير معتمد؛ الموافقات معلقة.'
    held=[s['service_id']+' / '+s['topic'] for s in slots if not s.get('complete')]
    note=('Held parts: ' if lang=='en' else 'أجزاء معلقة: ')+', '.join(held)
    scope='Only the selected source references are covered; this is not a complete eligibility checklist or end-to-end service procedure.' if lang=='en' else 'الإجابة محددة بالمراجع المتاحة، وليست قائمة كاملة بشروط الفتح أو إجراءات الخدمة.'
    result.update(type='answer' if good else 'unavailable',complete=False,supported_fact_ids=good,citations=[c for c in result['citations'] if c['fact_id'] in good],answer='\n\n'.join([banner]+groups+[note,scope]),invalidation_reason=reason,invalidated_fact_ids=sorted(bad))
