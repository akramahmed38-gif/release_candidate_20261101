"""Conservative per-page PDF/OCR selection; neither layer is assumed correct."""
from collections import Counter
import re
from .normalization import repair_pdf_arabic_text
from .passage_quality import readability


def numbers(text):
    return Counter(re.findall(r'\d+(?:[.,]\d+)*(?:\s*[%٪])?',text.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))))


def embedded_quality(text):
    text=repair_pdf_arabic_text(text)
    good=readability(text,qa=True)['readable'] and len(text.strip())>=20
    if re.search(r'\(cid:|\ufffd',text) or re.search(r'(?:[A-Za-z]\s+){8,}',text):good=False
    arabic=bool(re.search(r'[\u0621-\u064a]',text))
    table_risk=('\t' in text or '|' in text or (text.count('\n')>=2 and sum(numbers(text).values())>=3 and
                bool(re.search(r'fees?|limits?|رسوم|الحد',text,re.I))))
    return {'text':text,'usable_candidate':good,'comparison_required':arabic or not good or table_risk,'table_risk':table_risk}


def select_page_text(embedded,ocr,ocr_result=None):
    result=ocr_result or {};layer=embedded_quality(embedded)
    tokens=lambda s:set(re.findall(r'[A-Za-z\u0621-\u064a]{2,}',s.casefold()))
    left,right=tokens(layer['text']),tokens(ocr)
    overlap=len(left&right)/max(1,min(len(left),len(right)))
    numeric_agreement=numbers(layer['text'])==numbers(ocr)
    layout_uncertain=layer['table_risk'] or 'numeric_table_requires_relationship_review' in result.get('review_reasons',[])
    if layer['usable_candidate'] and (not layer['comparison_required'] or (overlap>=.65 and numeric_agreement)):
        return {'text':layer['text'],'method':'pdf_text_with_quality_checks','quality':'review_required' if layout_uncertain else 'candidate_text',
                'agreement':overlap,'numeric_agreement':numeric_agreement,'semantic_verified':False}
    if ocr.strip() and readability(ocr,qa=True)['readable']:
        conflict=layout_uncertain or (layer['usable_candidate'] and (not numeric_agreement or overlap<.65))
        return {'text':ocr,'method':'easyocr_full_page','quality':'review_required' if conflict else result.get('quality','unverified'),
                'agreement':overlap,'numeric_agreement':numeric_agreement,'semantic_verified':False}
    # Keep failed evidence for inspection, but never advertise it as answer-ready.
    return {'text':ocr or layer['text'],'method':'uncertain_pdf_ocr','quality':'review_required',
            'agreement':overlap,'numeric_agreement':numeric_agreement,'semantic_verified':False}
