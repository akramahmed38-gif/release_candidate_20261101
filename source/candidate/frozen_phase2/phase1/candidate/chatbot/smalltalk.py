from __future__ import annotations

from typing import Optional

from .normalization import TOKEN_RE, normalize_text, tokenize_for_search

GREETING_PATTERNS = (
    "ازيك",
    "عامل ايه",
    "عاملة ايه",
    "عامله ايه",
    "صباح الخير",
    "صباح الفل",
    "مساء الخير",
    "مساء الفل",
    "هاي",
    "هلا",
    "أهلا",
    "اهلا",
    "السلام عليكم",
    "hi",
    "hello",
    "hey",
)

IDENTITY_PATTERNS = (
    "اسمك ايه",
    "مين انت",
    "انت مين",
    "what's your name",
    "who are you",
)

GREETING_RESPONSE = "أهلًا بيك! أقدر أساعدك إزاي النهاردة؟"
IDENTITY_RESPONSE = "أنا مساعد دعم فوري، وبساعدك بالإجابة من المواد التدريبية المتاحة."

SMALLTALK_PATTERNS = {
    "greeting": GREETING_PATTERNS,
    "identity": IDENTITY_PATTERNS,
}

SMALLTALK_RESPONSES = {
    "greeting": GREETING_RESPONSE,
    "identity": IDENTITY_RESPONSE,
}


def _normalize_phrase(text: str) -> str:
    return normalize_text(str(text or ""), for_search=True).lower().strip()


def _raw_tokens(text: str) -> tuple[str, ...]:
    normalized_text = _normalize_phrase(text)
    if not normalized_text:
        return ()
    return tuple(TOKEN_RE.findall(normalized_text))


def _compiled_patterns() -> dict[str, tuple[dict[str, object], ...]]:
    compiled: dict[str, list[dict[str, object]]] = {}
    for smalltalk_type, phrases in SMALLTALK_PATTERNS.items():
        compiled[smalltalk_type] = []
        for phrase in phrases:
            normalized_phrase = _normalize_phrase(phrase)
            if not normalized_phrase:
                continue
            compiled[smalltalk_type].append(
                {
                    "normalized_phrase": normalized_phrase,
                    "raw_tokens": set(_raw_tokens(phrase)),
                    "search_tokens": set(tokenize_for_search(phrase)),
                }
            )
    return {key: tuple(value) for key, value in compiled.items()}


COMPILED_SMALLTALK_PATTERNS = _compiled_patterns()


def _matches_phrase(
    normalized_question: str,
    raw_question_tokens: set[str],
    search_question_tokens: set[str],
    pattern: dict[str, object],
) -> bool:
    normalized_phrase = str(pattern.get("normalized_phrase") or "")
    raw_phrase_tokens = set(pattern.get("raw_tokens") or set())
    search_phrase_tokens = set(pattern.get("search_tokens") or set())

    if not normalized_phrase:
        return False
    if normalized_question == normalized_phrase:
        return True
    # A greeting inside a business question must not replace its answer.
    # Raw tokens also prevent English substring matches inside product words.
    fillers = {"يا", "فيرو", "fero", "bot", "لو", "سمحت", "من", "فضلك", "please"}
    if raw_phrase_tokens and raw_phrase_tokens.issubset(raw_question_tokens):
        return (raw_question_tokens - raw_phrase_tokens).issubset(fillers)
    return False


def detect_smalltalk_type(question: str) -> str | None:
    normalized_question = _normalize_phrase(question)
    if not normalized_question:
        return None

    raw_question_tokens = set(TOKEN_RE.findall(normalized_question))
    search_question_tokens = set(tokenize_for_search(question))

    for smalltalk_type, patterns in COMPILED_SMALLTALK_PATTERNS.items():
        for pattern in patterns:
            if _matches_phrase(
                normalized_question,
                raw_question_tokens,
                search_question_tokens,
                pattern,
            ):
                return smalltalk_type
    return None


def smalltalk_response_for_type(smalltalk_type: str | None) -> Optional[str]:
    if not smalltalk_type:
        return None
    return SMALLTALK_RESPONSES.get(smalltalk_type)


def check_smalltalk(question: str) -> Optional[str]:
    return smalltalk_response_for_type(detect_smalltalk_type(question))
