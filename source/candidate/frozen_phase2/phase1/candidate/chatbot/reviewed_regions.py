"""Immutable region-level reconstructions, bound to source and extraction hashes.

This keeps complete verified instruction units instead of replacing isolated
words in a flattened screenshot. Unreviewed regions never become approved.
"""
import copy
import hashlib
import json
from pathlib import Path

SCHEMA='source-verified-regions-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def load_regions(root):
    path=Path(root)/'extraction_review_manifest.json'
    value=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'schema':SCHEMA,'regions':[]}
    if value.get('schema')!=SCHEMA:raise ValueError('Unsupported reviewed region schema')
    seen=set()
    for row in value['regions']:
        relative=Path(row['source_path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('material','daily_brief','KnowledgeBase'):
            raise ValueError('Invalid reviewed learning source path')
        if len(row['source_sha256'])!=64:raise ValueError('Source digest is required')
        key=(row['source_path'],row['location_type'],str(row['location_value']))
        if key in seen:raise ValueError('Duplicate reviewed source region')
        seen.add(key)
        if not row.get('anchors') or not row.get('units'):raise ValueError('Reviewed extraction anchors and units are required')
        for unit in row['units']:
            if hashlib.sha256(unit['text'].encode()).hexdigest()!=unit['text_sha256']:
                raise ValueError('Reviewed text changed after verification')
            if unit['state'] not in ('source_verified','source_verified_policy_review'):
                raise ValueError('Unverified text cannot enter the reviewed artifact')
    return value


def apply_regions(rows,manifest,fingerprints):
    """Replace only exact affected regions; return new rows, audit and tombstones."""
    by_id={row['id']:row for row in rows};excluded=set();added=[];audit=[]
    for region in manifest['regions']:
        anchors=region['anchors']
        # A per-file preparation pass should ignore other source regions.
        if not any(a['id'] in by_id for a in anchors):continue
        if fingerprints.get(region['source_path'])!=region['source_sha256']:
            raise ValueError('Reviewed original source version changed')
        for anchor in anchors:
            row=by_id.get(anchor['id'])
            if row is None or hashlib.sha256(row['text'].encode()).hexdigest()!=anchor['text_sha256']:
                raise ValueError('Reviewed extraction version changed')
            meta=row['metadata']
            if (meta.get('source_path','').replace('\\','/')!=region['source_path'] or
                meta.get('source_sha256')!=region['source_sha256'] or
                meta.get('location_type')!=region['location_type'] or
                str(meta.get('location_value'))!=str(region['location_value'])):
                raise ValueError('Reviewed extraction provenance mismatch')
        if excluded.intersection(a['id'] for a in anchors):raise ValueError('Overlapping replacement regions')
        excluded.update(a['id'] for a in anchors)
        source=by_id[anchors[0]['id']]['metadata']
        units=[u for u in region['units'] if u['state']=='source_verified']
        if not units:raise ValueError('A full source region cannot be silently withheld')
        for unit in units:
            metadata={k:copy.deepcopy(v) for k,v in source.items() if k not in
                      ('prompt_text','answer_text','question_text','qa_id','alternate_questions','chunk_index')}
            metadata.update(prompt_text=unit['text'],extraction_method='source_verified_region_reconstruction',
                extraction_quality='verified_instruction_unit',answer_eligibility='verified_passage_only',
                verified_answer_passages=[unit['text']],repair_ids=[unit['id']],
                region_review_id=region['id'],source_region=region['source_region'],
                extraction_review_digest=digest(region),reviewed_unit_id=unit['id'])
            added.append({'id':'reviewed-'+digest({'source':region['source_sha256'],'region':region['id'],'unit':unit}),
                          'text':unit['text'],'metadata':metadata})
        audit.append({'region_id':region['id'],'source_path':region['source_path'],
            'source_sha256':region['source_sha256'],'location':region['location_value'],
            'replaced_chunks':len(anchors),'verified_units':len(units),
            'policy_review_units_withheld':sum(u['state']=='source_verified_policy_review' for u in region['units']),
            'unverified_visual_regions':region.get('unverified_visual_regions',[]),
            'status':'verified_regions_reconstructed'})
    return [row for row in rows if row['id'] not in excluded]+added,audit,sorted(excluded)
