"""Reuse complete reviewed image units only for an exact original binary hash."""
import copy
import hashlib
import json
from pathlib import Path


def load_image_reviews(root):
    path=Path(root)/'extraction_image_reviews.json'
    result=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'schema':'source-verified-images-v1','sources':[]}
    if result.get('schema')!='source-verified-images-v1':raise ValueError('Unsupported image review schema')
    seen=set()
    for source in result['sources']:
        relative=Path(source['source_path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('material','daily_brief','KnowledgeBase') or relative.suffix.lower() not in ('.png','.jpg','.jpeg'):
            raise ValueError('Reviewed image is outside supported learning libraries')
        if source['source_path'] in seen or len(source['source_sha256'])!=64:raise ValueError('Invalid reviewed image identity')
        seen.add(source['source_path'])
        if not source.get('units'):raise ValueError('A reviewed image must retain verified content')
        for row in source['units']:
            meta=row['metadata']
            if meta.get('source_path')!=source['source_path'] or meta.get('source_sha256')!=source['source_sha256']:
                raise ValueError('Reviewed image provenance mismatch')
            if meta.get('location_type')!='image' or str(meta.get('location_value'))!='1' or not meta.get('location_label'):
                raise ValueError('Reviewed image location is required')
            if row['text_sha256']!=hashlib.sha256(row['text'].encode()).hexdigest():raise ValueError('Reviewed image text changed')
            if meta.get('answer_eligibility')!='verified_passage_only' or meta.get('verified_answer_passages')!=[row['text']]:
                raise ValueError('Reviewed image scope mismatch')
    return result


def reviewed_image_units(manifest,source_path,source_sha256):
    source=next((s for s in manifest['sources'] if s['source_path']==source_path and s['source_sha256']==source_sha256),None)
    if source is None:return None
    return [{k:copy.deepcopy(v) for k,v in row.items() if k!='text_sha256'} for row in source['units']]
