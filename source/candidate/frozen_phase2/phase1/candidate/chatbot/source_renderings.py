"""Version-bound presentation of source text; never grants policy approval."""
import hashlib,re

def checked_rendering(unit,language):
    original_sha=hashlib.sha256(unit['body'].encode()).hexdigest()
    if original_sha!=unit.get('text_sha256'):return None
    if unit.get('body_language')==language:
        return {'text':unit['body'],'text_sha256':original_sha,'kind':'original_reviewed_source_language',
                'source_body_sha256':original_sha,'operational_policy_approval_added':False}
    value=(unit.get('reviewed_renderings') or {}).get(language)
    if not isinstance(value,dict) or value.get('status')!='technical_source_equivalence_reviewed':return None
    if value.get('source_sha256')!=unit['source_sha256'] or value.get('source_body_sha256')!=original_sha:return None
    text=value.get('text')
    if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=value.get('text_sha256'):return None
    if language=='en' and re.search(r'[\u0621-\u064a]',text):return None
    return {**value,'kind':'source_equivalent_language_rendering','operational_policy_approval_added':False}
