"""Approved name spellings for presentation, never a source of business rules."""
import re

VERSION='approved-presentation-names-v1'
_NAMES=(
    (r'فور[يى]\s*بلس|\bFawry\s*Plus\b','Fawry Plus',r'\bFawry[ -]*Plus\b'),
    (r'(?:إنستا|انستا|إنستـا)\s*با[يى]|\bInsta\s*Pay\b','InstaPay',r'\bInsta[ -]*Pay\b'),
    (r'أكسس|اكسس|أكسيس|اكسيس|\bAXIS\b','AXIS',r'\bAXIS\b'),
    (r'أزيموت|ازيموت|\bAzimut\b','Azimut',r'\bAzimut\b'),
)


def required_names(source):
    return [(canonical,english) for alias,canonical,english in _NAMES
            if re.search(alias,source,re.I)]


def prepare_translation_source(source):
    """Keep proper names as names while leaving all facts and numbers intact."""
    for alias,canonical,_ in _NAMES:
        source=re.sub(alias,lambda _:canonical,source,flags=re.I)
    return source


def names_preserved(source,translated):
    return all(re.search(pattern,translated,re.I) for _,pattern in required_names(source))
