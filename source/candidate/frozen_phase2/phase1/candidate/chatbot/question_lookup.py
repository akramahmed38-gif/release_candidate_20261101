"""Model-free lookup of curated questions; conflicting wording stays ambiguous."""
from collections import defaultdict
import json
import re

from .normalization import normalize_text
from .query_language import normalize_franco


def question_key(text):
    # Keep numbers, negation, word order, dates and operators intact.
    value = normalize_text(normalize_franco(str(text or "")), for_search=True).casefold().strip(" ؟?!.\t\n")
    value = re.sub(r'(?<=[\u0621-\u064a])(?=[A-Za-z])|(?<=[A-Za-z])(?=[\u0621-\u064a])', ' ', value)
    # A polite Arabic prefix must not change the identity of an English product
    # question. Canonicalize the same brand/unit spellings on both sides.
    aliases={'fawry':'فوري','fawri':'فوري','yawmy':'يومي','youmy':'يومي','yomy':'يومي','yommy':'يومي','plus':'بلس','million':'مليون'}
    value=re.sub(r'\b(?:fawry|fawri|yawmy|youmy|yomy|yommy|plus|million)\b',lambda m:aliases[m.group()],value)
    for _ in range(4):
        simplified = re.sub(r"^(?:لو سمحت|من فضلك|ممكن اعرف|عايز اعرف|عاوز اعرف|please|can you tell me)\s+", "", value)
        if simplified == value:
            break
        value = simplified
    return value.strip(" ؟?!.")


class QuestionLookup:
    def __init__(self, rows):
        self.by_question = defaultdict(dict)
        for row in rows:
            metadata = row.get("metadata", {})
            if not metadata.get("qa_id") or not str(metadata.get("answer_text") or "").strip():
                continue
            alternates = metadata.get("alternate_questions") or []
            if isinstance(alternates, str):
                try:
                    alternates = json.loads(alternates)
                except (ValueError, TypeError):
                    alternates = []
            for text in [metadata.get("question_text", ""), *alternates]:
                key = question_key(text)
                if key:
                    identity = (metadata.get("source_path", ""), metadata["qa_id"], str(metadata["answer_text"]).strip())
                    self.by_question[key].setdefault(identity, row)

    def match(self, question):
        return list(self.by_question.get(question_key(question), {}).values())
