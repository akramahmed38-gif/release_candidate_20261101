from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
import threading
from time import monotonic
from typing import Callable, Sequence

from .follow_up_resolution import ResolvedQuestion
from .normalization import collapse_whitespace, normalize_text, tokenize_for_search

FOLLOW_UP_PREFIXES = tuple(
    normalize_text(value, for_search=True).lower()
    for value in (
        "طب",
        "طيب",
        "طب ولو",
        "ولو",
        "وبالنسبة",
        "بالنسبة",
        "كمان",
        "وكمان",
        "what about",
        "and",
        "also",
        "then",
        "so",
        "ok",
        "okay",
    )
)

ELLIPTICAL_STARTERS = {
    normalize_text(value, for_search=True).lower()
    for value in (
        "ايه",
        "ما",
        "ماذا",
        "كم",
        "امتى",
        "متى",
        "ازاي",
        "كيف",
        "فين",
        "اين",
        "هل",
        "ليه",
        "لماذا",
        "what",
        "when",
        "where",
        "how",
        "why",
        "which",
    )
}

QUESTION_WORDING_PREFIXES = tuple(
    normalize_text(value, for_search=True).lower()
    for value in (
        "ما",
        "اي",
        "ايه",
        "هل",
        "ازاي",
        "فين",
        "امتى",
        "اشرحلي",
        "كلمني عن",
    )
)

REFERENCE_MARKERS = tuple(
    normalize_text(value, for_search=True).lower()
    for value in (
        "هو",
        "هي",
        "هيه",
        "هما",
        "هم",
        "فيه",
        "فيها",
        "عليه",
        "عليها",
        "منه",
        "منها",
        "بتاعه",
        "بتاعها",
        "ده",
        "دي",
        "دا",
        "this",
        "that",
        "it",
        "its",
        "they",
        "them",
        "their",
    )
)

WORD_RE = re.compile(r"[A-Za-z0-9\u0600-\u06FF]+")
QUESTION_MARKS = "؟?"
GENERIC_TOPIC_WORDS = {
    normalize_text(value, for_search=True).lower()
    for value in (
        "ما",
        "هو",
        "هي",
        "ايه",
        "إيه",
        "يعني",
        "شرح",
        "اشرح",
        "اشرحلي",
        "اشرحلى",
        "خدمة",
        "الخدمة",
        "تأمين",
        "التامين",
        "التأمين",
        "وثيقة",
        "وثيقه",
        "برنامج",
        "البرنامج",
        "باقات",
        "الباقات",
        "تفاصيل",
        "التفاصيل",
        "شروط",
        "شرط",
        "الشروط",
        "إلغاء",
        "الغاء",
        "الالغاء",
        "الإلغاء",
        "اشتراك",
        "الاشتراك",
        "الغي",
        "الغي",
        "المستندات",
        "مستندات",
        "المطلوبة",
        "المطلوب",
        "مطلوبه",
        "مطلوب",
        "مدة",
        "المدة",
        "توصل",
        "وثيقه",
        "وثيقة",
        "اكتر",
        "اكثر",
        "متاح",
        "متاحة",
        "متاحه",
        "الولادة",
        "ولادة",
        "لكل",
        "الناس",
        "ناس",
        "هل",
        "أقدر",
        "اقدر",
        "أعمل",
        "اعمل",
        "ينفع",
        "في",
        "على",
        "من",
        "عن",
        "الى",
        "إلى",
        "و",
    )
}

SINGLE_WORD_TOPIC_ALLOWLIST = {
    normalize_text(value, for_search=True).lower(): value
    for value in (
        "معاشي",
        "AXIS PAY",
    )
}

QA_ID_TOPIC_LABELS: tuple[tuple[str, str], ...] = (
    ("FAWRY_INSURANCE_MEDICAL_", "صحتك فوري"),
    ("FAWRY_INSURANCE_ACCIDENT_", "قرشك الأبيض"),
    ("FAWRY_INSURANCE_HOME_", "الدار أمان"),
    ("FAWRY_INSURANCE_BUSINESS_", "باب رزقك"),
    ("FAWRY_YAWMY_", "فوري يومي"),
    ("YELLOW_CARD_", "الكارت الأصفر"),
    ("AXIS_PAY_", "AXIS PAY"),
    ("AZIMUT_", "أزيموت"),
    ("QNB_WALLET_", "QNB Wallet"),
)

GENERIC_SOURCE_TOPIC_STEMS = {
    normalize_text(value, for_search=True).lower()
    for value in (
        "insurance",
        "insurance art",
        "quality",
        "quality art",
        "operation",
        "operations",
        "operation art",
        "pos",
        "pos art",
        "faq",
        "guide",
    )
}

KNOWN_SOURCE_TOPIC_LABELS = {
    "maashy training": "معاشي",
    "maashy training art": "معاشي",
    "azimut": "أزيموت",
    "qnb wallet": "QNB Wallet",
    "fawry youmy": "فوري يومي",
    "yellow card": "الكارت الأصفر",
    "axis pay": "AXIS PAY",
}

TOPIC_ALIASES: dict[str, tuple[str, ...]] = {
    "صحتك فوري": ("صحتك فوري", "صحتك فورى"),
    "قرشك الأبيض": ("قرشك الأبيض", "قرشك الابيض"),
    "الدار أمان": ("الدار أمان", "الدار امان"),
    "باب رزقك": ("باب رزقك",),
    "معاشي": ("معاشي", "وثيقة معاشي", "maashy"),
    "فوري يومي": ("فوري يومي", "فوري يومى", "fawry yawmy"),
    "الكارت الأصفر": (
        "الكارت الأصفر",
        "الكارت الاصفر",
        "البطاقة الصفراء",
        "yellow card",
    ),
    "AXIS PAY": ("axis pay", "\u0627\u0643\u0633\u0633 \u0628\u0627\u064a", "\u0623\u0643\u0633\u0633 \u0628\u0627\u064a"),
    "أزيموت": ("أزيموت", "ازيموت", "azimut"),
}

NORMALIZED_TOPIC_ALIASES: dict[str, str] = {
    normalize_text(alias, for_search=True).lower(): canonical
    for canonical, aliases in TOPIC_ALIASES.items()
    for alias in aliases
}


_conversation_owner = ContextVar("chatbot_conversation_owner", default="")


@contextmanager
def conversation_owner(identity: str):
    token = _conversation_owner.set(hashlib.sha256(identity.strip().casefold().encode()).hexdigest())
    try:
        yield
    finally:
        _conversation_owner.reset(token)


def conversation_store_key(conversation_id: str | None, session_id: str | None) -> str | None:
    owner = _conversation_owner.get()
    prefix = f"user:{owner}:" if owner else ""
    conversation_value = str(conversation_id or "").strip()
    if conversation_value:
        return f"{prefix}conversation:{conversation_value}"

    session_value = str(session_id or "").strip()
    if session_value:
        return f"{prefix}session:{session_value}"
    return None


def _timestamp_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _normalize_for_detection(text: str) -> str:
    from .query_language import normalize_franco
    return normalize_text(normalize_franco(text), for_search=True).lower().strip()


def _match_known_topic_alias(text: str) -> str | None:
    normalized_text = _normalize_for_detection(text)
    for alias, canonical in sorted(
        NORMALIZED_TOPIC_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if alias and alias in normalized_text:
            return canonical
    return None


def detect_topic_alias(text: str) -> str | None:
    return _match_known_topic_alias(text)


def starts_with_question_wording(text: str) -> bool:
    normalized_text = _normalize_for_detection(collapse_whitespace(text))
    if not normalized_text:
        return False

    for prefix in QUESTION_WORDING_PREFIXES:
        if normalized_text == prefix or normalized_text.startswith(f"{prefix} "):
            return True
    return False


def _normalized_word_variants(word: str) -> tuple[str, ...]:
    normalized = str(word or "").strip()
    if not normalized:
        return ()

    variants = [normalized]
    if normalized.startswith("و") and len(normalized) > 1:
        variants.append(normalized[1:])
    return tuple(dict.fromkeys(variants))


def _word_matches_term_set(word: str, terms: set[str] | tuple[str, ...]) -> bool:
    term_set = set(terms)
    return any(variant in term_set for variant in _normalized_word_variants(word))


def _topic_label_from_qa_id(qa_id: str | None) -> str | None:
    normalized_qa_id = str(qa_id or "").strip().upper()
    if not normalized_qa_id:
        return None

    for prefix, topic_label in QA_ID_TOPIC_LABELS:
        if normalized_qa_id.startswith(prefix):
            return topic_label
    return None


def _topic_label_from_source_name(source_name: str | None) -> str | None:
    source_value = str(source_name or "").strip()
    if not source_value:
        return None

    stem = source_value.rsplit(".", 1)[0].replace("_", " ").strip()
    if not stem:
        return None

    normalized_stem = _normalize_for_detection(stem)
    if normalized_stem in GENERIC_SOURCE_TOPIC_STEMS:
        return None
    if normalized_stem in KNOWN_SOURCE_TOPIC_LABELS:
        return KNOWN_SOURCE_TOPIC_LABELS[normalized_stem]
    return collapse_whitespace(stem)


def _topic_label_from_grounded_question(question_text: str | None) -> str | None:
    cleaned_question = collapse_whitespace(str(question_text or "").strip())
    if not cleaned_question:
        return None

    detected_topic = detect_topic_alias(cleaned_question)
    if detected_topic is not None:
        return detected_topic

    extracted_topic = extract_topic_label(cleaned_question)
    if extracted_topic is not None:
        return extracted_topic

    match = re.match(
        r"^(?:ما\s+هي|ما\s+هو|اي\s+هوه|ايه|اشرحلي|كلمني\s+عن)\s+(.+?)(?:[؟?.!]|$)",
        cleaned_question,
        re.IGNORECASE,
    )
    if match is None:
        return None

    candidate = collapse_whitespace(match.group(1))
    for prefix in ("خدمة ", "الخدمة ", "تأمين ", "التأمين "):
        if candidate.startswith(prefix):
            candidate = collapse_whitespace(candidate[len(prefix) :])
    if not candidate:
        return None
    return candidate


def _resolve_exchange_topic_label(
    *,
    topic_label: str | None,
    qa_id: str | None,
    question_text: str | None,
    source_name: str | None,
    resolved_question: str,
    user_question: str,
) -> str | None:
    current_topic = detect_topic_alias(user_question)
    if current_topic:
        return current_topic
    explicit_topic_label = collapse_whitespace(str(topic_label or "").strip())
    if explicit_topic_label:
        return explicit_topic_label

    for candidate in (
        # Current explicit identity outranks a retrieved source. A mistaken
        # first retrieval must not replace the user's subject in later turns.
        detect_topic_alias(user_question),
        detect_topic_alias(resolved_question),
        _topic_label_from_qa_id(qa_id),
        _topic_label_from_grounded_question(question_text),
        _topic_label_from_source_name(source_name),
        detect_topic_alias(resolved_question),
        extract_topic_label(resolved_question),
        detect_topic_alias(user_question),
        extract_topic_label(user_question),
    ):
        if candidate:
            return collapse_whitespace(candidate)
    return None


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str
    message_id: str | None = None
    request_id: str | None = None
    answer_type: str | None = None
    qa_id: str | None = None
    source_name: str | None = None
    resolved_question: str | None = None
    question_text: str | None = None
    topic_label: str | None = None

    def topic_text(self) -> str:
        return str(self.question_text or self.resolved_question or self.content or "").strip()

    def resolved_topic_label(self) -> str | None:
        return self.topic_label or extract_topic_label(self.question_text or self.content or self.resolved_question or "")

    def topic_tokens(self, max_tokens: int = 8) -> tuple[str, ...]:
        tokens = tokenize_for_search(self.topic_text())
        return tuple(tokens[: max(1, int(max_tokens or 1))])

    def to_dict(self) -> dict[str, str | None]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "message_id": self.message_id,
            "request_id": self.request_id,
            "answer_type": self.answer_type,
            "qa_id": self.qa_id,
            "source_name": self.source_name,
            "resolved_question": self.resolved_question,
            "question_text": self.question_text,
            "topic_label": self.topic_label,
        }


@dataclass
class ConversationSnapshot:
    store_key: str
    conversation_id: str | None
    session_id: str | None
    created_at: str
    updated_at: str
    turns: list[ConversationTurn] = field(default_factory=list)
    business_context: dict | None = None

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def latest_topical_user_turn(self) -> ConversationTurn | None:
        for turn in reversed(self.turns):
            if turn.role != "user":
                continue
            if turn.answer_type in {"smalltalk", "clarification", "error"}:
                continue
            if turn.topic_text():
                return turn
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "store_key": self.store_key,
            "conversation_id": self.conversation_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "turns": [turn.to_dict() for turn in self.turns],
        }


@dataclass(frozen=True)
class FollowUpResolution:
    resolved_question: str
    used_history: bool
    follow_up_detected: bool
    reason: str | None
    store_key: str | None
    turn_count: int
    anchor_question: str | None = None
    anchor_tokens: tuple[str, ...] = ()
    topic_label: str | None = None
    llm_used: bool = False
    llm_resolution_time_ms: float = 0.0
    llm_failed_reason: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None

    def to_debug_dict(self) -> dict[str, object]:
        return {
            "conversation_history_used": self.used_history,
            "follow_up_detected": self.follow_up_detected,
            "follow_up_reason": self.reason,
            "resolved_question_for_retrieval": self.resolved_question,
            "conversation_history_turn_count": self.turn_count,
            "conversation_history_store_key": self.store_key,
            "conversation_history_anchor_question": self.anchor_question,
            "conversation_history_anchor_tokens": list(self.anchor_tokens),
            "conversation_history_topic_label": self.topic_label,
            "follow_up_llm_used": self.llm_used,
            "follow_up_llm_resolution_ms": self.llm_resolution_time_ms,
            "follow_up_llm_failed_reason": self.llm_failed_reason,
        }


class ConversationStore:
    def __init__(self, *, max_turns: int = 12, ttl_minutes: int = 120) -> None:
        self.max_turns = max(2, int(max_turns or 12))
        self.ttl_minutes = max(1, int(ttl_minutes or 120))
        self._lock = threading.Lock()
        self._states: dict[str, ConversationSnapshot] = {}
        self._last_cleanup = 0.0

    def _cleanup_expired_locked(self) -> None:
        tick = monotonic()
        if tick - self._last_cleanup < 30:
            return
        self._last_cleanup = tick
        now = datetime.now()
        expiry_cutoff = now - timedelta(minutes=self.ttl_minutes)
        expired_keys: list[str] = []
        for key, snapshot in self._states.items():
            updated_at = _parse_timestamp(snapshot.updated_at)
            if updated_at is None or updated_at <= expiry_cutoff:
                expired_keys.append(key)
        for key in expired_keys:
            self._states.pop(key, None)

    def get_business_context(self, conversation_id, session_id):
        snapshot = self.get_snapshot(conversation_id, session_id)
        return deepcopy(snapshot.business_context) if snapshot else None

    def set_business_context(self, conversation_id, session_id, value):
        key = conversation_store_key(conversation_id, session_id)
        if not key:
            return
        with self._lock:
            self._cleanup_expired_locked()
            now = _timestamp_now()
            state = self._states.get(key)
            if state is None:
                state = ConversationSnapshot(key, conversation_id, session_id, now, now)
                self._states[key] = state
            state.business_context = deepcopy(value)
            state.updated_at = now

    def get_snapshot(
        self,
        conversation_id: str | None,
        session_id: str | None,
    ) -> ConversationSnapshot | None:
        key = conversation_store_key(conversation_id, session_id)
        if not key:
            return None

        with self._lock:
            self._cleanup_expired_locked()
            snapshot = self._states.get(key)
            if snapshot is not None:
                updated = _parse_timestamp(snapshot.updated_at)
                if updated is None or updated <= datetime.now() - timedelta(minutes=self.ttl_minutes):
                    self._states.pop(key, None)
                    snapshot = None
            return deepcopy(snapshot) if snapshot is not None else None

    def clear(self, conversation_id: str | None, session_id: str | None) -> None:
        key = conversation_store_key(conversation_id, session_id)
        if not key:
            return
        with self._lock:
            self._states.pop(key, None)

    def save_exchange(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        request_id: str | None,
        user_question: str,
        resolved_question: str,
        assistant_answer: str,
        answer_type: str | None,
        message_id: str | None = None,
        qa_id: str | None = None,
        source_name: str | None = None,
        question_text: str | None = None,
        topic_label: str | None = None,
        timestamp: str | None = None,
    ) -> ConversationSnapshot | None:
        key = conversation_store_key(conversation_id, session_id)
        if not key:
            return None

        exchange_timestamp = timestamp or _timestamp_now()
        topic_label = _resolve_exchange_topic_label(
            topic_label=topic_label,
            qa_id=qa_id,
            question_text=question_text,
            source_name=source_name,
            resolved_question=resolved_question,
            user_question=user_question,
        )
        user_turn = ConversationTurn(
            role="user",
            content=user_question.strip(),
            timestamp=exchange_timestamp,
            message_id=message_id,
            request_id=request_id,
            answer_type=answer_type,
            qa_id=qa_id,
            source_name=source_name,
            resolved_question=resolved_question.strip() or user_question.strip(),
            question_text=question_text.strip() if question_text else None,
            topic_label=topic_label,
        )
        assistant_turn = ConversationTurn(
            role="assistant",
            content=assistant_answer.strip(),
            timestamp=exchange_timestamp,
            message_id=message_id,
            request_id=request_id,
            answer_type=answer_type,
            qa_id=qa_id,
            source_name=source_name,
            question_text=question_text.strip() if question_text else None,
            topic_label=topic_label,
        )

        with self._lock:
            self._cleanup_expired_locked()
            snapshot = self._states.get(key)
            if snapshot is not None:
                updated = _parse_timestamp(snapshot.updated_at)
                if updated is None or updated <= datetime.now() - timedelta(minutes=self.ttl_minutes):
                    snapshot = None
            if snapshot is None:
                snapshot = ConversationSnapshot(
                    store_key=key,
                    conversation_id=str(conversation_id or "").strip() or None,
                    session_id=str(session_id or "").strip() or None,
                    created_at=exchange_timestamp,
                    updated_at=exchange_timestamp,
                    turns=[],
                )
            snapshot.turns.extend([user_turn, assistant_turn])
            if len(snapshot.turns) > self.max_turns:
                snapshot.turns = snapshot.turns[-self.max_turns :]
            snapshot.updated_at = exchange_timestamp
            self._states[key] = snapshot
            return deepcopy(snapshot)


def _collect_significant_words(text: str) -> list[str]:
    significant_words: list[str] = []
    for normalized_word in tokenize_for_search(collapse_whitespace(text)):
        if not normalized_word:
            continue
        if normalized_word.isdigit():
            continue
        if len(normalized_word) <= 2:
            continue
        if _word_matches_term_set(normalized_word, GENERIC_TOPIC_WORDS):
            continue
        if _word_matches_term_set(normalized_word, set(REFERENCE_MARKERS)):
            continue
        if _word_matches_term_set(normalized_word, ELLIPTICAL_STARTERS):
            continue
        significant_words.append(normalized_word)
    return significant_words


def extract_topic_label(text: str) -> str | None:
    raw_text = collapse_whitespace(text.strip())
    if not raw_text:
        return None

    known_topic = _match_known_topic_alias(raw_text)
    if known_topic:
        return known_topic

    significant_words = _collect_significant_words(raw_text)
    if not significant_words:
        return None

    if len(significant_words) >= 2:
        return collapse_whitespace(" ".join(significant_words[-2:]))

    single_word = collapse_whitespace(significant_words[-1])
    normalized_single_word = _normalize_for_detection(single_word)
    if normalized_single_word in SINGLE_WORD_TOPIC_ALLOWLIST:
        return single_word
    return None


def _contextual_follow_up(question: str) -> tuple[str | None, str | None]:
    text = _normalize_for_detection(question).strip(" ؟?.!")
    if re.search(r"\d", text) and re.match(r"^(?:و\s*)?(?:مش|موش|مش كان|مش المفروض|يعني|مش هو)\b", text):
        return "numeric_recheck", None
    aspect = re.fullmatch(
        r"(?:و\s*)?(?:(?:طب|طيب)\s+)?(?:(?:ما هي|ما هو|ايه|ما|كم|كام)\s+)?(?:ال)?"
        r"(مميزات|شروط|رسوم|خطوات|حدود|حد|مصاريف|عموله|عمولة|مده|مدة)(?:ه|ها)?", text,
    )
    if aspect:
        return "aspect_follow_up", aspect.group(1)
    if re.fullmatch(r"(?:و\s*)?(?:ليه|ازاي|يعني ايه|ممكن توضح|وضح اكتر|اشرح اكتر|مش فاهم|كمل|بعدين|طب وبعدين)", text):
        return "explanation_follow_up", None
    if re.match(r"^(?:لا|لأ|قصدي|اقصد|مش قصدي)\s", text):
        return "correction_follow_up", None
    if len(text.split())<=12 and re.match(r'^(?:و?بالنسب[ةه]\s+(?:ل|لل)|what\s+about\b|and\s+(?:the\s+)?(?:stamp|signature|manager)\b)',text,re.I):
        return "reference_follow_up", None
    words = text.split()
    if len(words) <= 12 and (bool(words and words[0] in {"هو", "هي", "وهو", "وهي"}) or any(word in {"ده", "دي", "دا", "كده", "فيه", "فيها", "عليه", "عليها", "بتاعه", "بتاعها", "بينهم"} for word in words)):
        return "reference_follow_up", None
    return None, None


def resolve_follow_up_question(
    question: str,
    snapshot: ConversationSnapshot | None,
    *,
    max_topic_tokens: int = 8,
    max_recent_turns: int = 6,
    llm_resolver: Callable[[str, str | None, Sequence[ConversationTurn]], ResolvedQuestion] | None = None,
) -> FollowUpResolution:
    from .query_language import normalize_conversation_query
    cleaned_question = collapse_whitespace(normalize_conversation_query(question).strip())
    follow_up_kind, follow_up_aspect = _contextual_follow_up(cleaned_question)
    if not cleaned_question or snapshot is None:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="no_history",
            store_key=snapshot.store_key if snapshot is not None else None,
            turn_count=snapshot.turn_count if snapshot is not None else 0,
            topic_label=None,
            needs_clarification=bool(cleaned_question and follow_up_kind),
            clarification_question="تقصد أي خدمة أو منتج؟" if follow_up_kind else None,
        )

    anchor_turn = snapshot.latest_topical_user_turn()
    if anchor_turn is None:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="no_anchor_turn",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            topic_label=None,
        )

    anchor_question = anchor_turn.topic_text()
    anchor_tokens = anchor_turn.topic_tokens(max_topic_tokens)
    anchor_topic_label = anchor_turn.resolved_topic_label()
    if not anchor_question or not anchor_tokens:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="empty_anchor_topic",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question or None,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
        )

    normalized_question = _normalize_for_detection(cleaned_question)
    if not normalized_question:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="empty_question",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
        )

    current_tokens = tokenize_for_search(cleaned_question)
    if not current_tokens:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="empty_query_tokens",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
        )

    current_topic_label = _match_known_topic_alias(cleaned_question)
    if current_topic_label is not None:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="current_question_has_explicit_topic",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=current_topic_label,
        )

    if not anchor_topic_label:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="missing_topic_label",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
            needs_clarification=bool(follow_up_kind),
            clarification_question="تقصد أي خدمة أو منتج في سؤالك؟" if follow_up_kind else None,
        )

    if follow_up_kind:
        anchor_text = _normalize_for_detection(anchor_turn.content)
        mentioned_topics = {canonical for alias, canonical in NORMALIZED_TOPIC_ALIASES.items() if alias and alias in anchor_text}
        if len(mentioned_topics) > 1:
            return FollowUpResolution(
                resolved_question=cleaned_question, used_history=False, follow_up_detected=True,
                reason="ambiguous_previous_topics", store_key=snapshot.store_key,
                turn_count=snapshot.turn_count, needs_clarification=True,
                clarification_question="تقصد أي خدمة تحديداً: " + " أم ".join(sorted(mentioned_topics)) + "؟",
            )
        if follow_up_aspect:
            resolved = f"ما هي {follow_up_aspect} {anchor_topic_label}؟"
        elif follow_up_kind == "numeric_recheck":
            # Recheck the grounded question; the user's proposed amount is not evidence.
            resolved = anchor_turn.question_text or anchor_question
        else:
            resolved = f"{anchor_topic_label}: {cleaned_question}"
        return FollowUpResolution(
            resolved_question=resolved, used_history=True, follow_up_detected=True,
            reason=follow_up_kind, store_key=snapshot.store_key, turn_count=snapshot.turn_count,
            anchor_question=anchor_question, anchor_tokens=anchor_tokens, topic_label=anchor_topic_label,
        )

    if llm_resolver is None:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="llm_resolver_unavailable",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
        )

    recent_turns = list(snapshot.turns[-max(1, int(max_recent_turns or 6)) :])
    llm_result = llm_resolver(cleaned_question, anchor_topic_label, recent_turns)
    malformed_reasons = {
        "cjk_characters_detected",
        "duplicate_words",
        "empty_payload",
        "missing_active_topic",
        "multiple_question_marks",
        "standalone_mutated",
        "too_long",
        "unchanged_rewrite",
        "unexpected_characters",
    }
    if llm_result.failed_reason:
        follow_up_reason = (
            "follow_up_llm_resolution_malformed"
            if llm_result.failed_reason in malformed_reasons
            else "follow_up_llm_resolution_failed"
        )
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason=follow_up_reason,
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
            llm_used=llm_result.used_llm,
            llm_resolution_time_ms=llm_result.latency_ms,
            llm_failed_reason=llm_result.failed_reason,
        )

    if not llm_result.is_follow_up:
        return FollowUpResolution(
            resolved_question=cleaned_question,
            used_history=False,
            follow_up_detected=False,
            reason="llm_kept_standalone",
            store_key=snapshot.store_key,
            turn_count=snapshot.turn_count,
            anchor_question=anchor_question,
            anchor_tokens=anchor_tokens,
            topic_label=anchor_topic_label,
            llm_used=llm_result.used_llm,
            llm_resolution_time_ms=llm_result.latency_ms,
            llm_failed_reason=llm_result.failed_reason,
        )

    return FollowUpResolution(
        resolved_question=collapse_whitespace(llm_result.resolved_question or cleaned_question),
        used_history=True,
        follow_up_detected=True,
        reason="llm_resolved_follow_up",
        store_key=snapshot.store_key,
        turn_count=snapshot.turn_count,
        anchor_question=anchor_question,
        anchor_tokens=anchor_tokens,
        topic_label=anchor_topic_label,
        llm_used=llm_result.used_llm,
        llm_resolution_time_ms=llm_result.latency_ms,
        llm_failed_reason=llm_result.failed_reason,
    )
