"""Evaluation only: preserved expectations and interpretation/answer scoring.

Never imported by the language index builder. This module supplies no answering
instructions and does not reinterpret expected facts from available knowledge.
"""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
import json,sys,hashlib,math

ROOT=Path(__file__).resolve().parent
SUPPLIED=Path(r'C:\Users\akram.ahmed\Downloads\Fawry_Language_Understanding_Library_v1_1\Fawry_Language_Understanding_Library_v1_1')

def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def _cases(path):
    value=_read(path)
    return value['cases'] if isinstance(value,dict) else value

def _known_meanings(root):
    path=root/'evaluation_data/KNOWN_N_MEANINGS.jsonl'
    if not path.is_file():return {},None
    rows=[json.loads(s) for s in path.read_text(encoding='utf-8-sig').splitlines() if s.strip()]
    if len(rows)!=18 or len({r['case_id'] for r in rows})!=18:
        raise ValueError('KnownN meaning annotation inventory mismatch')
    return {r['case_id']:r for r in rows},hashlib.sha256(path.read_bytes()).hexdigest()

def load_cases(root=ROOT):
    """Return exactly128 historical cases; fresh material is never read here.

    frozen_expected retains each original case. The only permitted coverage
    overlay is the previously recorded P1_N09 ATM-deposit addition.
    """
    root=Path(root)
    phase1=_cases(root/'frozen_phase2/phase1/test_cases.json')
    phase2=_cases(root/'frozen_phase2/test_cases.json')
    thirtysix=_cases(root/'ACCEPTANCE_36.json')
    known24=_cases(root/'EMPLOYEE_QUESTIONS.json')
    npath=root/'evaluation_data/HISTORICAL_N18.json'
    if not npath.is_file():
        npath=Path(r'D:\FawryChatbotPreparation\question_planning_repair_20261028\heldout\NEW_CASES.json')
    eighteen=_cases(npath)
    meaning_reviews,meaning_digest=_known_meanings(root)
    batches=[
        ('frozen',[{**c,'id':'P1_'+c['id']} for c in phase1]+phase2+thirtysix),
        ('known_varied',known24),('known_N',eighteen)]
    overlays=_read(root/'COVERAGE_UPGRADES.json')
    if set(overlays)-{'P1_N09'}:
        raise ValueError('Unexpected historical coverage overlay')
    result=[]
    for suite,items in batches:
        for original in items:
            case=deepcopy(original)
            case['frozen_expected']=deepcopy(original)
            case['suite']=suite
            if case['id'] in overlays:
                upgrade=deepcopy(overlays[case['id']])
                case.update(facts=upgrade['facts'],complete=upgrade['complete'],type='answer')
                case['coverage_upgrade']=upgrade
            review=meaning_reviews.get(case['id'])
            if review is not None:
                if review['question']!=original['question'] or set(review['original_expected_fact_ids'])!=set(original['facts']):
                    raise ValueError('KnownN annotation differs from preserved question/fact scope')
                requests=deepcopy(review['requested_plan_review'])
                if any(not all(k in r for k in ['service_id','intent_id','channels']) for r in requests):
                    raise ValueError('Incomplete authored requested meaning')
                # Exact typed exclusions can be compared. Bare legacy topic
                # labels lack a service/meaning binding and remain unscored.
                raw_exclusions=deepcopy(review.get('excluded_topics',[]))
                typed=all(isinstance(x,dict) and {'service_id','intent_id'}<=set(x) for x in raw_exclusions)
                plan={'requests':requests,'scored_categories':['requested_intents','extra_intents','service_binding','channel_binding']}
                if typed:
                    plan['excluded_requests']=raw_exclusions
                    plan['scored_categories'].append('excluded_intents')
                case['expected_plan']=plan
                case['semantic_annotation']={
                    'source':'evaluation_data/KNOWN_N_MEANINGS.jsonl','source_sha256':meaning_digest,
                    'evaluation_use':review['evaluation_use'],'authorship':'Authored library review; exposed AI annotations, not human/blind acceptance',
                    'annotation_scope':'requested service/intent/channel bindings only; no inferred mode, condition, procedure or dialogue gold',
                    'excluded_topics_raw':raw_exclusions,'exclusions_scored':typed,
                    'unscored_fields':['request_mode','conditions','procedure_scope','context','user_claims','relations','references','decision']+([] if typed else ['excluded_intents'])}
            result.append(case)
    if len(result)!=128 or len({c['id'] for c in result})!=128:
        raise ValueError('Historical128 inventory mismatch')
    return result

def load_fresh_cases(path):
    """Explicit final-run loader. Call only after code/config/index freeze."""
    cases=deepcopy(_cases(path))
    if len(cases)!=48 or len({c['id'] for c in cases})!=48:
        raise ValueError('Fresh48 inventory mismatch')
    for case in cases:
        case['suite']='fresh'
    return cases

def case_fingerprints(cases):
    return {c['id']:hashlib.sha256(json.dumps(c.get('frozen_expected',c),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest() for c in cases}

def grade_business(case,response,facts):
    """Use unchanged inherited fact/citation/isolation checks; return issue list."""
    inherited=ROOT/'frozen_phase2'
    if str(inherited) not in sys.path:sys.path.insert(0,str(inherited))
    from run_phase2 import grade
    unknown=set(response.get('supported_fact_ids',[]))-set(facts)
    unknown|={c.get('fact_id') for c in response.get('citations',[]) if c.get('fact_id') not in facts}
    if unknown:
        return ['unknown_emitted_fact_or_citation']
    try:
        return grade(case,response,facts)
    except (KeyError,TypeError,ValueError):
        return ['malformed_business_answer']

def _canonical(value):
    """Stable comparison only; no business/intent synonym substitution."""
    if isinstance(value,dict):
        return tuple(sorted((k,_canonical(v)) for k,v in value.items()))
    if isinstance(value,list):
        return tuple(sorted((_canonical(x) for x in value),key=repr))
    return value

def _req_key(request,include_channels=True):
    key=(request.get('service_id'),request.get('intent_id'))
    return key+(tuple(sorted(request.get('channels',[]))),) if include_channels else key

def _group_channels(requests):
    """Evaluation normalization only; never cross provider or condition/scope.

    A single two-channel request and two otherwise identical one-channel
    requests express the same scoped meaning. Their actual contracts remain
    untouched; IDs are retained for relation comparison.
    """
    keys=['service_id','intent_id','mode','conditions','procedure_scope','object','dimensions',
          'quantity_role','minimum_role','timeframe','sequence_scope','scope','antecedent','reference']
    groups={}
    for request in requests:
        key=tuple((k,_canonical(request.get(k))) for k in keys)
        if key not in groups:
            groups[key]=deepcopy(request)
            groups[key]['_original_request_ids']=[]
        group=groups[key]
        group['channels']=sorted(set(group.get('channels',[]))|set(request.get('channels',[])))
        if request.get('request_id'):group['_original_request_ids'].append(request['request_id'])
    return list(groups.values())

def _property_contains(expected,actual):
    if isinstance(expected,dict):
        return isinstance(actual,dict) and all(k in actual and _property_contains(v,actual[k]) for k,v in expected.items())
    if isinstance(expected,list):
        if not isinstance(actual,list) or len(expected)!=len(actual):return False
        unused=list(range(len(actual)))
        for value in expected:
            match=next((i for i in unused if _property_contains(value,actual[i])),None)
            if match is None:return False
            unused.remove(match)
        return True
    return expected==actual

def grade_language(expected_plan,actual_contract):
    """Compare meanings, never expected fact IDs or fluent answer wording.

    Annotation keys may differ from runtime collection names; the two documented
    collection aliases are adapted without rewriting their semantic content.
    """
    expected=expected_plan.get('expected_plan',expected_plan)
    actual=actual_contract.get('request_contract',actual_contract)
    original_er=expected.get('requests',[]);original_ar=actual.get('requests',[])
    er=_group_channels(original_er);ar=_group_channels(original_ar)
    actual_ids={old:r['request_id'] for r in ar if r.get('request_id') for old in r['_original_request_ids']}
    categories={name:[] for name in [
        'requested_intents','extra_intents','service_binding','channel_binding',
        'conditions','procedure_scope','request_mode','excluded_intents',
        'context','user_claims','relations','references','decision']}
    ei=Counter(r.get('intent_id') for r in er);ai=Counter(r.get('intent_id') for r in ar)
    categories['requested_intents']=list((ei-ai).elements())
    categories['extra_intents']=list((ai-ei).elements())
    # Match each expected request to one actual request without discarding
    # multiplicity or choosing a different provider simply because it has facts.
    unused=set(range(len(ar)));request_ids={}
    for e in er:
        same=[i for i in unused if _req_key(ar[i],False)==_req_key(e,False)]
        if not same:
            by_intent=[i for i in unused if ar[i].get('intent_id')==e.get('intent_id')]
            if by_intent:categories['service_binding'].append({'expected':e,'actual_candidates':[ar[i] for i in by_intent]})
            continue
        index=min(same,key=lambda i:len(set(e.get('channels',[]))^set(ar[i].get('channels',[]))))
        a=ar[index];unused.remove(index)
        if a.get('request_id'):
            for old in e['_original_request_ids']:request_ids[old]=a['request_id']
        if set(e.get('channels',[]))!=set(a.get('channels',[])):
            categories['channel_binding'].append({'request':_req_key(e,False),'expected':e.get('channels',[]),'actual':a.get('channels',[])})
        for key,category in [('conditions','conditions'),('procedure_scope','procedure_scope'),('mode','request_mode')]:
            if key in e and not _property_contains(e[key],a.get(key)):
                categories[category].append({'request':_req_key(e,False),'expected':e[key],'actual':a.get(key)})
            elif key=='conditions' and key not in e and a.get(key):
                categories[category].append({'request':_req_key(e,False),'expected':[],'actual':a.get(key),'reason':'extra_user_condition'})
        # Additional typed scope fields present in authored annotations retain
        # their object/value meaning rather than collapsing into legacy topics.
        for key in ['object','dimensions','quantity_role','minimum_role','timeframe','sequence_scope','scope','antecedent','reference']:
            if key in e and not _property_contains(e[key],a.get(key)):
                category='references' if key in {'antecedent','reference'} else 'procedure_scope'
                categories[category].append({'request':_req_key(e,False),'field':key,'expected':e[key],'actual':a.get(key)})
    # Scope errors remain visible even when aggregate intent recall is perfect.
    expected_bindings=Counter(_req_key(r,False) for r in er)
    actual_bindings=Counter(_req_key(r,False) for r in ar)
    for key,count in (actual_bindings-expected_bindings).items():
        categories['service_binding'].append({'unexpected_service_intent':key,'count':count})
    def excluded_key(item):
        return (item.get('service_id'),item.get('intent_id'),tuple(sorted(item.get('channels',[]))))
    if 'excluded_requests' in expected:
        ex=Counter(excluded_key(x) for x in _group_channels(expected['excluded_requests']))
        ax=Counter(excluded_key(x) for x in _group_channels(actual.get('excluded_requests',[])))
        if ex!=ax:categories['excluded_intents'].append({'missing':list((ex-ax).elements()),'extra':list((ax-ex).elements())})
    def relabel(value):
        if isinstance(value,dict):return {k:relabel(v) for k,v in value.items()}
        if isinstance(value,list):return [relabel(v) for v in value]
        return request_ids.get(value,value) if isinstance(value,str) else value
    def relabel_actual(value):
        if isinstance(value,dict):return {k:relabel_actual(v) for k,v in value.items()}
        if isinstance(value,list):return [relabel_actual(v) for v in value]
        return actual_ids.get(value,value) if isinstance(value,str) else value
    for source,target,category in [
        ('context_mentions_not_requests','context_mentions','context'),
        ('user_claims_not_evidence','user_claims','user_claims'),
        ('context_mentions','context_mentions','context'),
        ('user_claims','user_claims','user_claims'),
        ('relations','relations','relations'),
        ('references','references','references')]:
        comparison=relabel(expected[source]) if source=='relations' and source in expected else expected.get(source)
        target_value=relabel_actual(actual.get(target,[])) if source=='relations' else actual.get(target,[])
        if source in expected and not _property_contains(comparison,target_value):
            categories[category].append({'expected_field':source,'expected':expected[source],'actual':actual.get(target,[])})
    if 'decision' in expected and expected['decision']!=actual.get('decision'):
        categories['decision'].append({'expected':expected['decision'],'actual':actual.get('decision')})
    scored=expected.get('scored_categories',list(categories))
    unscored={k:v for k,v in categories.items() if k not in scored}
    categories={k:v for k,v in categories.items() if k in scored}
    matched=sum((ei&ai).values());requested=sum(ei.values());produced=sum(ai.values())
    return {'passed':not any(categories.values()),'errors':{k:v for k,v in categories.items() if v},
            'requested_intent_count':requested,'actual_intent_count':produced,'matched_intent_count':matched,
            'requested_intent_recall':matched/requested if requested else (1.0 if not produced else 0.0),
            'intent_precision':matched/produced if produced else (1.0 if not requested else 0.0),
            'extra_intent_count':sum((ai-ei).values()),
            'scored_categories':scored,'unscored_categories':list(unscored),
            'unscored_observations':{k:v for k,v in unscored.items() if v},
            'request_normalization':{'policy':'merge channels only within identical service/intent/mode/conditions/procedure and other typed scope; actual contract unchanged',
                                     'expected_raw_requests':len(original_er),'expected_scoped_groups':len(er),
                                     'actual_raw_requests':len(original_ar),'actual_scoped_groups':len(ar)},
            'scope':'Semantic annotations compared separately from business answers; not a source-policy approval'}

def validate_contract(contract,schema_path=None):
    """Structural schema + every exact raw span, including reference spans."""
    errors=[]
    schema_path=Path(schema_path) if schema_path else ROOT/'evaluation_data/request_contract.schema.json'
    if not schema_path.is_file():schema_path=SUPPLIED/'data/request_contract.schema.json'
    schema=_read(schema_path)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        backend='explicit_structural_fallback_no_jsonschema'
        if not isinstance(contract,dict):errors.append({'path':'$','reason':'object_required'})
        else:
            for key in schema['required']:
                if key not in contract:errors.append({'path':key,'reason':'required'})
            for key in ['requests','excluded_requests','context_mentions','user_claims','unresolved_spans']:
                if key in contract and not isinstance(contract[key],list):errors.append({'path':key,'reason':'array_required'})
            if contract.get('decision') not in {'interpret_then_retrieve','clarify','record_context'}:errors.append({'path':'decision','reason':'enum'})
            if not isinstance(contract.get('raw_question'),str):errors.append({'path':'raw_question','reason':'string_required'})
            if contract.get('language') not in {None,'ar_eg','ar_msa','en','franco_eg','mixed','unknown'}:errors.append({'path':'language','reason':'enum'})
            for index,req in enumerate(contract.get('requests',[]) if isinstance(contract.get('requests'),list) else []):
                for key in ['request_id','service_id','intent_id','channels','evidence_spans']:
                    if key not in req:errors.append({'path':f'requests[{index}].{key}','reason':'required'})
                if req.get('service_id') is not None and not isinstance(req.get('service_id'),str):errors.append({'path':f'requests[{index}].service_id','reason':'string_or_null_required'})
    else:
        backend='jsonschema_draft202012'
        for error in Draft202012Validator(schema).iter_errors(contract):
            errors.append({'path':'.'.join(map(str,error.absolute_path)),'reason':error.validator})
    if not isinstance(contract,dict) or not isinstance(contract.get('raw_question'),str):
        return {'passed':False,'backend':backend,'errors':errors,'span_count':0}
    span_count=0
    def walk(value,path,raw):
        nonlocal span_count
        if isinstance(value,dict):
            own_raw=raw
            if 'raw_question' in value:
                if path=='$' or ('antecedent' in path or 'source_turn' in path):
                    if isinstance(value['raw_question'],str):own_raw=value['raw_question']
                    else:errors.append({'path':path+'.raw_question','reason':'string_required'})
                else:errors.append({'path':path+'.raw_question','reason':'nested_raw_override_not_permitted'})
            if all(k in value for k in ['start','end','text']):
                span_count+=1
                start,end,text=value['start'],value['end'],value['text']
                valid=type(start) is int and type(end) is int and isinstance(text,str) and 0<=start<=end<=len(own_raw) and own_raw[start:end]==text
                if not valid:errors.append({'path':path,'reason':'raw_unicode_span_mismatch'})
            for key,item in value.items():
                if isinstance(item,(dict,list)):walk(item,path+'.'+key,own_raw)
        elif isinstance(value,list):
            for index,item in enumerate(value):walk(item,f'{path}[{index}]',raw)
    walk(contract,'$',contract['raw_question'])
    for index,request in enumerate(contract.get('requests',[])):
        if not isinstance(request,dict):continue
        spans=request.get('evidence_spans',[])
        if not spans:errors.append({'path':f'requests[{index}].evidence_spans','reason':'missing_interpretation_evidence'})
        roles={s.get('role') for s in spans if isinstance(s,dict)}
        if spans and not roles&{'requested_predicate','referent'}:
            errors.append({'path':f'requests[{index}].evidence_spans','reason':'no_predicate_or_current_referent_span'})
    ids=[r.get('request_id') for r in contract.get('requests',[]) if isinstance(r,dict)]
    if len(set(ids))!=len(ids):errors.append({'path':'requests','reason':'duplicate_request_id'})
    return {'passed':not errors,'backend':backend,'errors':errors,'span_count':span_count,
            'schema_sha256':hashlib.sha256(schema_path.read_bytes()).hexdigest(),
            'scope':'Schema/span validity is not semantic correctness'}

def percentile(values,q):
    values=sorted(values)
    if not values:return None
    location=(len(values)-1)*q;lower=math.floor(location);upper=math.ceil(location)
    return values[lower]+(values[upper]-values[lower])*(location-lower)

def latency_summary(values):
    values=list(values)
    return {'n':len(values),'p50_ms':percentile(values,.5),'p95_ms':percentile(values,.95),
            'mean_ms':sum(values)/len(values) if values else None}
