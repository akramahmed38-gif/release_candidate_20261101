"""Semantic-preserving language normalization before unchanged numeric checks.

No numeric literal, percentage, code, currency, negation or period is removed
or changed. Written signature cardinality becomes an additional obligation.
"""
import re

def normalize_validation_language(source,answer):
    original=str(source);translated=str(answer)
    normalized=original
    changes=[]
    if re.search(r'توقيع.{0,40}ثلاثي',original):
        normalized=re.sub(r'ثلاثي(?:اً|ًا|ا|ة|ه)?', '3 أجزاء اسم',normalized)
        changes.append('source_written_signature_quantity_three_recognized')
        # The same cardinality in an English adjective must retain its unit.
        translated=re.sub(r'\btripartite\b','3-part',translated,flags=re.I)
    translated,count=re.subn(r'\bdeposit(?:ing|ed|s)\b','deposit',translated,flags=re.I)
    if count:changes.append('english_deposit_inflection_lemmatized')
    return normalized,translated,changes
