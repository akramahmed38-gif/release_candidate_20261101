"""Candidate-only source/view lifecycle, with exact existing test representations."""
import copy,json
from pathlib import Path
from registry import load_records
def checks(root,work):
    definition=json.loads((root/'fixture_data/definition.json').read_text(encoding='utf-8'));authorized=set(definition['authorized_test_ids']);source=work/'source_files'
    accepted,rejected=load_records(definition,source,authorized)
    result={'batch_addition':len(accepted)==21 and not rejected,'no_normal_runtime_promotions':all(not f['normal_runtime_eligible'] and not f['business_approved'] and not f['human_fidelity_approved'] for f in accepted.values())}
    changed=copy.deepcopy(definition);record=next(f for f in changed['facts'] if f['fact_id']=='F0001');record['english']=''
    good,bad=load_records(changed,source,authorized)
    result['missing_english_held_unrelated_retained']='F0001' in bad and 'F0010' in good and 'F0036' in good
    from candidate import CatalogEngine
    candidate=CatalogEngine(work,test_mode=True,definition_override=changed)
    actual=candidate.ask('AXIS deposit fees at Fawry Plus; ADIB remittance service code.','missing-view','missing-view')
    result['missing_view_candidate_answer_keeps_unrelated_source']=actual['supported_fact_ids']==['F0036'] and not actual['complete']
    (work/'LIFECYCLE_ACTUAL_ANSWERS.json').write_text(json.dumps({'missing_english_view':actual,'note':'Same source-controlled candidate with Core BM25 retrieval; no extra BGE/model calls.'},ensure_ascii=False,indent=2),encoding='utf-8')
    changed=copy.deepcopy(definition);record=next(f for f in changed['facts'] if f['fact_id']=='F0001');record['source_sha256']='0'*64
    good,bad=load_records(changed,source,authorized)
    result['source_replacement_requires_new_review']='F0001' in bad and 'F0010' in good
    changed=copy.deepcopy(definition);record=next(f for f in changed['facts'] if f['fact_id']=='F0001');record['revision']=2
    good,bad=load_records(changed,source,authorized)
    result['revision_without_fixture_reauthorization_held']='F0001' in bad
    record['authorized_fixture_revision']=2
    good,bad=load_records(changed,source,authorized)
    result['explicit_fixture_reauthorization_is_not_business_approval']='F0001' in good and not good['F0001']['normal_runtime_eligible'] and not good['F0001']['business_approved']
    good,bad=load_records(definition,source,authorized-{'F0001'})
    result['revoked_record_held_others_retained']='F0001' in bad and 'F0010' in good
    # A forged service/scope cannot be accepted merely by preserving its text.
    changed=copy.deepcopy(definition);next(f for f in changed['facts'] if f['fact_id']=='F0001')['service_id']='qnb_wallet'
    good,bad=load_records(changed,source,authorized)
    result['provider_rebinding_rejected']='F0001' in bad and 'F0073' in good
    return result
