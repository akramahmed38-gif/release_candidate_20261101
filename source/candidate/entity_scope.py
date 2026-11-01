"""Typed current-task service exclusions, never source-policy exceptions."""
import re
from linguistic_spans import shadow,tokens,forms

def task_group(question,position):
    return len(list(re.finditer(r'[;؛!?؟]|(?<!\d)\.(?!\d)',question[:position])))


def entity_nonrestriction(raw, entity_spans):
    """Not-only entity reference, without any new business predicate."""
    if not entity_spans:
        return False
    normalized, coords = shadow(raw)
    match = re.match(r'^\s*(?:not\s+only|مش\s+بس|ليس\s+فقط)(?=\s|$)', normalized, re.I)
    if not match:
        return False
    chars = list(raw)
    start, end = coords[match.start()], coords[match.end()-1]+1
    chars[start:end] = ' '*(end-start)
    for a,b in entity_spans:
        chars[a:b] = ' '*(b-a)
    return not tokens(''.join(chars))

def entity_omission(raw,entity_spans,comparison=False):
    if not entity_spans:return False
    normalized,coords=shadow(raw)
    if re.match(r'^\s*(?:not\s+only|مش\s+بس|ليس\s+فقط)',normalized,re.I):return False
    match=re.match(r'^\s*(?:و|ف)?(excluding|exclude|except|not|without|استبعد|باستثناء|بدون|دون|عدا|ماعدا|مش|ليس)(?=\s|$)',normalized,re.I)
    if not match:return False
    if match.group(1).casefold() not in {'excluding','exclude','استبعد','باستثناء'} and not comparison:return False
    chars=list(raw)
    marker_start=coords[match.start()];marker_end=coords[match.end()-1]+1
    chars[marker_start:marker_end]=' '*(marker_end-marker_start)
    for a,b in entity_spans:chars[a:b]=' '*(b-a)
    grammar=set(tokens('from the this current comparison only provider service wallet remittance من عن المقارنة الخدمة الحوالة'))
    return all(forms(word)&grammar for word in tokens(''.join(chars)))
