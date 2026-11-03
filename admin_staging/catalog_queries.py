"""Catalog metadata queries. Recognition and availability never grant approval."""
import json,re

def declared_services(record):
    found={record['service_id']} if isinstance(record.get('service_id'),str) else set()
    for key in ['service_ids','service_ids_json','scopes_json']:
        value=record.get(key,[])
        if isinstance(value,str):
            try:value=json.loads(value)
            except (ValueError,TypeError):value=[]
        if isinstance(value,list):found.update(x for x in value if isinstance(x,str))
    return found

def filter_records(records,*,service='',review_status='',language='',source_version='',eligible=None):
    if source_version and not re.fullmatch('[a-f0-9]{64}',source_version):raise ValueError('Use an exact SHA-256 source version')
    if language not in {'','ar','en_test','missing_en_test'}:raise ValueError('Unknown language-view filter')
    # No genuine source/version-bound approval registry is connected yet.
    # A metadata boolean or synthetic approval must not manufacture eligibility.
    if eligible is True:return []
    result=[]
    for r in records:
        if service and service not in declared_services(r):continue
        if review_status and r.get('review_status','pending')!=review_status:continue
        if source_version and r.get('source_sha256')!=source_version:continue
        english=bool(r.get('english_test_view')) and not r.get('quarantine_reason')
        arabic=bool(r.get('arabic')) or r.get('arabic_view')=='original_source_reference' and bool(r.get('body'))
        if language=='ar' and not arabic:continue
        if language=='en_test' and not english:continue
        if language=='missing_en_test' and english:continue
        result.append(r)
    return result
