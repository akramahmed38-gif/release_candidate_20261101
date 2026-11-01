"""Conservative evidence eligibility, distinct from business-fact correctness."""
import json
import re

_BLOCKED={'title_only','navigation_only','requires_layout_review','unverified_remainder'}
_CONFIRMED_BAD=re.compile(r"Fawry\s+DlUs|Azimut\s+Kc\s+Instructions|AxS\s+P[٠-٩]+|cusipmerMame|يرجى\s+افراءذ|الشاشة\s+الرليسية|تقالالر\s+حالة\s+المراعة|myfawry\s+HUPER",re.I)


def contains_interpretation_instructions(text):
    """Source-authored chatbot directives are not authoritative business facts.

    Quarantine the whole mixed passage; never strip a directive and silently
    promote its embedded policy assertions into approved evidence.
    """
    value=re.sub(r'[\u0610-\u061a\u064b-\u065f\u0640]','',str(text or ''))
    return bool(re.search(r'(?:اي|أي)\s+سؤال\s+يحتوي|(?:اذا|إذا)\s+(?:كان\s+)?السؤال.*?فهو\s+يقصد',value,re.S)
                or re.search(r'\b(?:if|any|every)\s+(?:a\s+|the\s+)?(?:user\s+)?question\s+contains\b',value,re.I))


def held_policy_instruction(text):
    """An existing business-owner review hold, including duplicated assertions.

    This does not judge completed customer declarations or decide FATCA policy.
    It blocks the currently withheld universal answer instruction in answers,
    independently of which document repeated it. Other procedures stay indexed.
    """
    value=re.sub(r'[\u0610-\u061a\u064b-\u065f\u0640]','',str(text or ''))
    if not re.search(r'FATCA|فاتكا',value,re.I):return False
    universal=r'(?:جميع|كل)\s+(?:اسئلة|أسئلة|الاسئلة|الأسئلة)|\b(?:all|every)\s+(?:(?:the|FATCA)\s+){0,2}questions?\b'
    obligation=r'يجب|يتعين|يتم\s+الت[أا]كد|\b(?:must|should|always|ensure|required)\b'
    return bool(re.search(universal,value,re.I) and re.search(obligation,value,re.I) and re.search(
        r'(?:الاجابة|الإجابة|الاجاب[ةه]|الإجاب[ةه]|answer\w*)[^.!؟\n]{0,90}(?:["\u201c\u201d\s(]لا\b|\bno\b)',value,re.I))


def policy_review_response(result):
    return {**result,'answer':'تعليمات اختيار إجابة موحدة لكل أسئلة FATCA تحتاج مراجعة واعتماد من مسؤول السياسة. لا أستطيع تقديمها كإجراء عام لكل العملاء.',
        'type':'clarification','answer_type':'clarification','fallback_used':True,
        'fallback_reason':'business_policy_review_required','business_policy_review_required':True,
        'sources':[],'primary_source':None,'supporting_sources':[]}


def verified_passages(metadata):
    value=metadata.get('verified_answer_passages',[])
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):return []
    return [v for v in value if isinstance(v,str) and v.strip()] if isinstance(value,list) else []


def evidence_text(text,metadata):
    mode=metadata.get('answer_eligibility')
    if mode in _BLOCKED:return ''
    if contains_interpretation_instructions(metadata.get('prompt_text') or text):return ''
    if mode=='verified_passage_only':
        value='\n'.join(verified_passages(metadata))
        if value and metadata.get('temporal_scope')=='year_not_present':
            value+='\nلم تُذكر سنة سريان العرض في الصورة.'
        return value
    return metadata.get('prompt_text') or text


def readability(text,metadata=None,qa=False):
    metadata=metadata or {};text=str(text or '').strip();reasons=[]
    if metadata.get('answer_eligibility') in _BLOCKED:reasons.append(metadata['answer_eligibility'])
    if not text:reasons.append('empty_evidence')
    if contains_interpretation_instructions(text):reasons.append('source_interpretation_instructions')
    if '\ufffd' in text or re.search(r'\(cid:\d+\)|[ÃÂ]{2,}',text):reasons.append('undecoded_glyphs')
    if _CONFIRMED_BAD.search(text):reasons.append('confirmed_corrupted_fragment')
    tokens=re.findall(r'[A-Za-z\u0621-\u064a]+',text)
    if len(tokens)>=25 and sum(len(t)==1 for t in tokens)/len(tokens)>.4:reasons.append('fragmented_character_order')
    # Valid short curated answers, technical identifiers and bilingual terms survive.
    if not qa and len(tokens)<18 and re.search(r'دليل|\b(?:training|instructions|manual)\b',text,re.I):
        if not re.search(r'يرجى|يجب|يتم|تأكد|يشترط|\b(?:must|ensure|required|check)\b',text,re.I):reasons.append('heading_without_answer')
    return {'readable':not reasons,'reasons':reasons,'is_semantic_correctness_certificate':False}


def protect_answer(result):
    if not isinstance(result,dict) or result.get('type')=='clarification' or result.get('fallback_used') or result.get('smalltalk_handled'):return result
    if held_policy_instruction(result.get('answer','')):return policy_review_response(result)
    chunks=result.get('selected_chunks') or result.get('retrieved_chunks') or []
    qa=bool(result.get('selected_qa_id') or result.get('qa_id')) or any(c.get('qa_id') for c in chunks)
    quality=readability(result.get('answer',''),qa=qa)
    if any(c.get('temporal_scope')=='year_not_present' for c in chunks):
        answer=str(result.get('answer',''))
        if re.search(r'\b20\d{2}\b|ساري\s+حالياً|متاح\s+حالياً|currently\s+valid|valid\s+now',answer,re.I):
            quality={'readable':False,'reasons':['unsupported_offer_year_or_current_validity']}
    if quality['readable']:return result
    return {**result,'answer':'المحتوى المتاح لهذه النقطة غير واضح بما يكفي لتقديم إجابة موثوقة. يرجى تحديد الإجراء أو مراجعة المصدر المعتمد.',
            'type':'clarification','answer_type':'clarification','fallback_used':True,'fallback_reason':'unreadable_source_evidence',
            'sources':[],'primary_source':None,'supporting_sources':[],'extraction_quality_reasons':quality['reasons']}


def translation_preserves_unknown_year(source,translated):
    normalized=re.sub(r'[\u0610-\u061a\u064b-\u065f]','',source)
    if not re.search(r'لم\s+(?:تذكر|يذكر)\s+سنة|السنة\s+غير\s+(?:مذكورة|محددة)',normalized):return True
    negation=(r'\bno\s+(?:specific\s+)?year\b|\byear\b.{0,60}\b(?:unknown|unspecified|unstated)\b|'
              r'\byear\b.{0,30}\bnot\s+(?:provided|shown|specified|stated|mentioned|given|indicated|included|visible)\b|'
              r'\b(?:does\s+not|doesn.t)\b.{0,15}\b(?:state|mention|specify|indicate|show|give|provide)\b.{0,30}\byear\b')
    contradiction=r'\b(?:current|this)\s+year\b|\bcurrently\s+(?:valid|available|active)\b'
    return bool(re.search(negation,translated,re.I)) and not re.search(contradiction,translated,re.I)
