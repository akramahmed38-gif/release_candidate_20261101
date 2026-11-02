"""Keep topic similarity from substituting for the requested aspect of a question."""
import re
from .normalization import tokenize_for_search, normalize_text

_ASPECTS = (
    ("مميزات", "مزايا", "ميزة", "فوائد", "features", "benefits", "advantages"),
    ("رسوم", "مصاريف", "عمولة", "fees", "charges", "commission"),
    ("شروط", "متطلبات", "requirements", "conditions"),
    ("خطوات", "steps"),
    ("خصم", "خصومات", "discount", "discounts"),
    ("سحب", "withdrawal", "withdrawals"),
)


def _tokens(text):
    return {word.removeprefix("ال") for word in tokenize_for_search(str(text or ""))}


def requested_aspects(question):
    question_tokens = _tokens(question)
    return [_tokens(" ".join(group)) for group in _ASPECTS if question_tokens & _tokens(" ".join(group))]


def supported_aspect(question, evidence):
    """Require the requested detail and product words, not broad topic similarity."""
    requested = requested_aspects(question)
    if not requested:
        return False
    generic = _tokens("محفظة بطاقة حساب خدمة عميل منتج bank wallet card account customer service product products what how much is are the for its هو هي ما كم هذا هذه")
    aspects = set().union(*requested)
    anchors = _tokens(question) - generic - aspects
    evidence_tokens = _tokens(evidence)
    return bool(anchors) and anchors <= evidence_tokens and all(evidence_tokens & group for group in requested)


def condition_specificity(text):
    """Prefer source passages that retain eligibility/limit qualifiers."""
    text = normalize_text(text, for_search=True).lower()
    patterns = (r"\b(?:ل?اول|first|initial)\b", r"شهري|\bشهر\b|\bmonth(?:ly)?\b",
                r"\b(?:فقط|only)\b", r"باستثناء|\bexcept\b", r"بشرط|يشترط|\bprovided\b",
                r"حد ادني|حد اقصي|\bminimum\b|\bmaximum\b")
    return sum(bool(re.search(pattern, text)) for pattern in patterns)


def align_answer_aspect(question, retrieval, minimum_score):
    if retrieval.should_fallback or retrieval.top_chunk is None:
        return
    requested = requested_aspects(question)
    if not requested:
        return
    top = retrieval.top_chunk
    source = top.source_path or top.source_name
    matching = []
    for chunk in (retrieval.ranked_chunks or retrieval.chunks):
        if chunk.final_score < minimum_score:
            continue
        evidence = " ".join([chunk.question_text or "", chunk.answer_text or "", *(chunk.alternate_questions or [])])
        if not evidence.strip() and not chunk.qa_id:
            evidence = chunk.context_text()
        tokens = _tokens(evidence)
        if (chunk.source_path or chunk.source_name) != source and not supported_aspect(question, evidence):
            continue
        if all(tokens & aspect for aspect in requested):
            matching.append(chunk)
    if not matching:
        retrieval.fallback_reason = "requested_aspect_not_supported"
        return
    # When the question asks about a particular detail, a short summary must
    # not displace the same detail's eligibility or temporal conditions.
    best = max(matching, key=lambda chunk: (
        condition_specificity(chunk.answer_text or chunk.context_text()) if requested else 0,
        chunk.final_score))
    retrieval.chunks = [best] + [chunk for chunk in retrieval.chunks if chunk.chunk_id != best.chunk_id]
