from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from .query_language import normalize_franco

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
TOKEN_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF]+")
TASHKEEL_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u06D6-\u06ED]")
WHITESPACE_RE = re.compile(r"\s+")

COMMON_ARABIC_WORDS = {
    "في",
    "من",
    "على",
    "الي",
    "الى",
    "او",
    "اذا",
    "تم",
    "يتم",
    "عدم",
    "العميل",
    "البطاقه",
    "بطاقه",
    "بطاقات",
    "التاكد",
    "خدمه",
    "فروع",
    "فوري",
    "جهاز",
    "السستم",
    "السيستم",
}

STOPWORDS = {
    "اي",
    "ايه",
    "ايش",
    "ازاي",
    "ازاى",
    "اين",
    "التي",
    "الذي",
    "اللي",
    "اللى",
    "او",
    "الى",
    "الي",
    "اما",
    "امتى",
    "ان",
    "انا",
    "انت",
    "ايضا",
    "بقى",
    "بقي",
    "بس",
    "بعد",
    "بعض",
    "بين",
    "ثم",
    "جدا",
    "جالي",
    "جالى",
    "دا",
    "ده",
    "دي",
    "زى",
    "زي",
    "سوف",
    "في",
    "فين",
    "لو",
    "ما",
    "ماذا",
    "متى",
    "مع",
    "مين",
    "ممكن",
    "من",
    "هو",
    "هي",
    "واحد",
    "وين",
}

RAW_EGYPTIAN_SYNONYMS = {
    "ابلغ": "اخطر",
    "ابلغه": "اخطار",
    "اعمل": "اتصرف",
    "الفلوس": "نقود",
    "بطاقته": "بطاقه",
    "بطاقتى": "بطاقه",
    "بطاقه": "بطاقه",
    "بطايق": "بطاقات",
    "بشحن": "شحن",
    "جالي": "جاءني",
    "جالى": "جاءني",
    "حتة": "جزء",
    "حته": "جزء",
    "عايز": "يريد",
    "عايزه": "يريد",
    "عاوزه": "يريد",
    "فلوس": "نقود",
    "كارت": "بطاقه",
    "الكارت": "بطاقه",
    "كروت": "بطاقات",
    "كروته": "بطاقات",
    "ماكينه": "ماكينة",
    "ماكينة": "ماكينة",
    "مكنة": "ماكينة",
    "مكنه": "ماكينة",
    "مكسورة": "مكسور",
    "مكسوره": "مكسور",
    "مشروخة": "مشروخ",
    "مشروخه": "مشروخ",
    "نفذت": "انتهت",
}

DOMAIN_TERM_GROUPS = (
    ("فوري", "fawry"),
    ("بلس", "بلص", "plus"),
    ("سوبرفوري", "superfawry"),
    ("حساب", "اكونت", "أكونت", "account"),
    ("ماكينة", "ماكينه", "مكينة", "مكينه", "مكنة", "مكنه"),
    ("pos", "جهاز", "ماكينة", "مكنة"),
    ("اتقفل", "مقفول", "موقوف", "قفل", "locked"),
    ("عطل", "عطلانة", "عطلانه", "عطلت", "أعطال", "اعطال"),
)

# Shared concepts bridge English queries and Arabic learning content without
# changing amounts, eligibility rules or any other business facts.
DOMAIN_TERM_GROUPS += (
    ('مميزات','مزايا','benefits','features','advantages'),
    ('رسوم','مصاريف','fees','charges'),
    ('عمولة','commission'),
    ('شروط','متطلبات','requirements','conditions'),
    ('خطوات','steps'),
    ('سحب','withdrawal','withdrawals'),
    ('ايداع','deposit','deposits'),
    ('تحويل','transfers','transfer'),
    ('تفعيل','activation'),
    ('اشتراك','subscription'),
    ('مجاني','free'),
    ('خصم','discount'),
    ('axis','اكسس','أكسس','اكسيس'),
    ('محفظة','wallet','wallets'),
    ('بطاقة','card','cards'),
    ('رصيد','balance'),
    ('عميل','customer','client'),
    ('فرع','branch','branches'),
    ('استرداد','refund'),
    ('تقسيط','installments','instalments'),
    ('فاتورة','فواتير','invoice','invoices','bills'),
    ('خطأ','error'),
    ('معنى','meaning'),
    ('نطق','pronunciation'),
    ('تصنيف','category'),
)

PUNCT_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "—": "-",
        "–": "-",
        "…": "...",
        "،": ",",
        "؛": ";",
        "؟": "?",
    }
)


def contains_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text))


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_punctuation(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return text.translate(PUNCT_TRANSLATION)


def strip_tashkeel(text: str) -> str:
    text = TASHKEEL_RE.sub("", text)
    return text.replace("ـ", "")


def normalize_arabic_letters(text: str, for_search: bool = False) -> str:
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if for_search:
        text = text.replace("ة", "ه")
    return text


@lru_cache(maxsize=16384)
def normalize_text(text: str, for_search: bool = False) -> str:
    text = normalize_punctuation(text)
    text = strip_tashkeel(text)
    text = normalize_arabic_letters(text, for_search=for_search)
    return collapse_whitespace(text)


def _normalize_search_term(text: str) -> str:
    return normalize_text(text, for_search=True).lower()


def _build_search_synonym_map(raw_map: dict[str, str]) -> dict[str, str]:
    normalized_map: dict[str, str] = {}
    for raw_key, raw_value in raw_map.items():
        key = _normalize_search_term(raw_key)
        value = _normalize_search_term(raw_value)
        if key and value:
            normalized_map[key] = value
    return normalized_map


def _build_term_variant_map(groups: tuple[tuple[str, ...], ...]) -> dict[str, tuple[str, ...]]:
    variant_map: dict[str, tuple[str, ...]] = {}
    for raw_group in groups:
        normalized_group = tuple(
            dict.fromkeys(
                term
                for term in (_normalize_search_term(item) for item in raw_group)
                if term
            )
        )
        if len(normalized_group) < 2:
            continue
        for term in normalized_group:
            variant_map[term] = tuple(item for item in normalized_group if item != term)
    return variant_map


EGYPTIAN_SYNONYMS = _build_search_synonym_map(RAW_EGYPTIAN_SYNONYMS)
TERM_VARIANT_MAP = _build_term_variant_map(DOMAIN_TERM_GROUPS)


def _reverse_arabic_segments(token: str) -> str:
    parts = re.findall(r"[\u0600-\u06FF]+|[A-Za-z0-9]+|[^A-Za-z0-9\u0600-\u06FF]+", token)
    repaired_parts: list[str] = []
    for part in parts:
        if contains_arabic(part):
            repaired_parts.append(part[::-1])
        else:
            repaired_parts.append(part)
    return "".join(repaired_parts)


def _repair_arabic_runs(line: str) -> str:
    words = line.split()
    if not words:
        return line

    groups: list[tuple[bool, list[str]]] = []
    current_is_arabic: bool | None = None

    for word in words:
        is_arabic_word = contains_arabic(word)
        if current_is_arabic is None or is_arabic_word != current_is_arabic:
            groups.append((is_arabic_word, [word]))
            current_is_arabic = is_arabic_word
        else:
            groups[-1][1].append(word)

    repaired_words: list[str] = []
    for is_arabic_group, group_words in groups:
        if is_arabic_group:
            repaired_words.extend(_reverse_arabic_segments(word) for word in reversed(group_words))
        else:
            repaired_words.extend(group_words)
    return " ".join(repaired_words)


def _arabic_readability_score(text: str) -> int:
    normalized = normalize_text(text, for_search=True)
    tokens = TOKEN_RE.findall(normalized)
    score = 0
    for token in tokens:
        if token in COMMON_ARABIC_WORDS:
            score += 2
        if token.startswith("ال") and len(token) > 4:
            score += 1
        if token.endswith(("ه", "ات", "ون", "ين")):
            score += 1
    return score


def repair_pdf_arabic_text(text: str) -> str:
    lines = [collapse_whitespace(line) for line in text.splitlines() if collapse_whitespace(line)]
    if not lines:
        return ""

    repaired_lines: list[str] = []
    for line in lines:
        if not contains_arabic(line):
            repaired_lines.append(line)
            continue
        repaired_candidate = _repair_arabic_runs(line)
        if _arabic_readability_score(repaired_candidate) > _arabic_readability_score(line):
            repaired_lines.append(repaired_candidate)
        else:
            repaired_lines.append(line)
    return "\n".join(repaired_lines)


def _arabic_prefix_variants(token: str, max_depth: int = 2) -> list[str]:
    prefixes = ("و", "ف", "ب", "ك", "ل")
    variants: list[str] = []
    queue: list[tuple[str, int]] = [(token, 0)]
    seen = {token}

    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth or len(current) <= 4:
            continue

        next_candidates: list[str] = []
        if current.startswith("لل") and len(current) > 4:
            next_candidates.append(f"ال{current[2:]}")
        for prefix in prefixes:
            if current.startswith(prefix) and len(current) > 4:
                next_candidates.append(current[1:])

        for candidate in next_candidates:
            if candidate in seen or len(candidate) <= 2:
                continue
            seen.add(candidate)
            variants.append(candidate)
            queue.append((candidate, depth + 1))

    return variants


def expand_token(token: str) -> list[str]:
    normalized_token = _normalize_search_term(token)
    if not normalized_token:
        return []

    variants: list[str] = []
    queue = [normalized_token]
    seen: set[str] = set()

    while queue:
        current = queue.pop(0)
        if not current or current in seen:
            continue
        seen.add(current)
        variants.append(current)

        if current.startswith("ال") and len(current) > 4:
            queue.append(current[2:])
        if contains_arabic(current) and len(current) > 3:
            queue.extend(_arabic_prefix_variants(current))

        synonym = EGYPTIAN_SYNONYMS.get(current)
        if synonym:
            queue.append(synonym)

        queue.extend(TERM_VARIANT_MAP.get(current, ()))

    return variants


def tokenize_for_search(text: str) -> list[str]:
    # Callers receive a copy so changes cannot poison another user's tokens.
    return list(_cached_search_tokens(text))


@lru_cache(maxsize=8192)
def _cached_search_tokens(text: str) -> tuple[str, ...]:
    normalized = normalize_text(normalize_franco(text), for_search=True).lower()
    tokens: list[str] = []
    for raw_token in TOKEN_RE.findall(normalized):
        for token in expand_token(raw_token):
            if len(token) <= 1:
                continue
            if token in STOPWORDS:
                continue
            tokens.append(token)
    return tuple(dict.fromkeys(tokens))


def keyword_overlap(query_tokens: list[str], doc_tokens: list[str]) -> tuple[int, float]:
    if not query_tokens or not doc_tokens:
        return 0, 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    overlap_count = len(query_set & doc_set)
    return overlap_count, overlap_count / max(len(query_set), 1)
