"""Exact, version-bound passage repairs; original caches are never overwritten."""
import copy
import hashlib
import json
from pathlib import Path

SCHEMA='verified-passage-repairs-v1'
TEXT_FIELDS=('text','prompt_text','answer_text')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def load_repair_plan(root):
    path=Path(root)/'extraction_corrections.json'
    if not path.exists():return {'schema':SCHEMA,'records':[],'page_policies':[]}
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if value.get('schema')!=SCHEMA:raise ValueError('Unsupported passage repair schema')
    for row in [*value.get('records',[]),*value.get('page_policies',[])]:
        relative=Path(row['source_path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('material','daily_brief','KnowledgeBase'):
            raise ValueError('Repair source is outside learning libraries')
        if len(row.get('source_sha256',''))!=64:raise ValueError('Repair source fingerprint required')
    return value


def repair_plan_digest(root):
    return digest(load_repair_plan(root))


def apply_repair_plan(rows,plan,source_fingerprints):
    """Return replacements and a register, withholding unsupported corrections.

    The caller supplies hashes of the actual source files, not just cached hashes.
    Field hashes bind each replacement to a specific extraction version.
    """
    result=copy.deepcopy(rows);register=[]
    old_ids={r['id']:r['id'] for r in rows}
    def identity(row):return row['metadata'].get('repair_original_chunk_id',row['id'])
    by_id={identity(row):row for row in result}
    def current(record):return source_fingerprints.get(record['source_path'])==record['source_sha256']
    for record in plan.get('records',[]):
        entry={k:copy.deepcopy(record[k]) for k in ('id','source_path','source_sha256','location_type','location_value','bad','good','scope','evidence','root_cause')}
        entry['corrected_chunk_ids']=[]
        entry['correction_method']='source_hash_and_field_hash_bound_exact_substring_replacement'
        entry['confidence']='verified_for_the_recorded_passage_only'
        if not current(record):
            entry.update(status='blocked_exact_original_unavailable_or_changed',review_required=True);register.append(entry);continue
        anchors=record.get('anchors',[])
        conflicts=[]
        for anchor in anchors:
            row=by_id.get(anchor['chunk_id'])
            if row is None:conflicts.append('missing_chunk');continue
            meta=row['metadata']
            if record['id'] in meta.get('repair_ids',[]):continue
            if (meta.get('source_path','').replace('\\','/')!=record['source_path'] or meta.get('source_sha256')!=record['source_sha256'] or
                meta.get('location_type')!=record['location_type'] or str(meta.get('location_value'))!=str(record['location_value'])):
                conflicts.append('anchor_provenance_mismatch');continue
            for field,expected in anchor['fields'].items():
                text=row['text'] if field=='text' else meta.get(field,'')
                if field not in TEXT_FIELDS or hashlib.sha256(text.encode()).hexdigest()!=expected['sha256'] or text.count(record['bad'])!=expected['occurrences']:
                    conflicts.append('extraction_or_passage_mismatch')
        if conflicts or not anchors:
            entry.update(status='conflict_requires_review',reasons=sorted(set(conflicts or ['missing_anchor'])),review_required=True)
            register.append(entry);continue
        changed=False
        for anchor in anchors:
            row=by_id[anchor['chunk_id']];meta=row['metadata']
            if record['id'] in meta.get('repair_ids',[]):continue
            for field in anchor['fields']:
                if field=='text':row[field]=row[field].replace(record['bad'],record['good'])
                else:meta[field]=meta[field].replace(record['bad'],record['good'])
            meta['repair_ids']=sorted(set(meta.get('repair_ids',[])+[record['id']]))
            meta['repair_original_chunk_id']=anchor['chunk_id']
            meta['repair_verification']='source_hash_and_exact_passage_verified'
            changed=True
        entry.update(status='confirmed_and_repaired' if changed else 'already_applied',review_required=False)
        register.append(entry)
    approved={r['id'] for r in register if r['status'] in ('confirmed_and_repaired','already_applied')}
    for policy in plan.get('page_policies',[]):
        if not current(policy) or not set(policy.get('requires_repairs',[]))<=approved:continue
        for chunk_id in policy['chunk_ids']:
            row=by_id.get(chunk_id)
            if not row:continue
            meta=row['metadata']
            if meta.get('source_sha256')!=policy['source_sha256']:continue
            meta['repair_original_chunk_id']=chunk_id
            meta['answer_eligibility']=policy['answer_eligibility']
            meta['verified_answer_passages']=policy.get('verified_passages_by_chunk',{}).get(chunk_id,[])
            meta['extraction_quality']='passage_verified_remainder_unverified'
            if policy.get('temporal_scope'):meta['temporal_scope']=policy['temporal_scope']
    originals={r['id']:r for r in rows}
    replacements=[]
    for row in result:
        old=identity(row)
        if old in originals and row!=originals[old]:
            row['id']='repair-'+digest({'original_id':old,'text':row['text'],'metadata':row['metadata']})
            replacements.append({'old_id':old,'new_id':row['id'],'text_changed':row['text']!=originals[old]['text']})
    for entry in register:
        anchors={a['chunk_id'] for r in plan.get('records',[]) if r['id']==entry['id'] for a in r.get('anchors',[])}
        entry['corrected_chunk_ids']=[r['new_id'] for r in replacements if r['old_id'] in anchors]
    return result,register,replacements
