"""Fast, verbatim source answers; never synthesize facts to avoid model latency."""
import re

from .generation import clean_generation_context


def grounded_source_answer(retrieval, question=None):
    top = retrieval.top_chunk
    if retrieval.should_fallback or top is None or top.qa_id:
        return None
    if top.final_score < 0.62 or top.semantic_score < 0.45 or retrieval.query_coverage < 0.65 or top.overlap_count < 2:
        return None
    text = clean_generation_context(top.context_text()).strip()
    from .passage_quality import readability
    if not readability(text,{'answer_eligibility':getattr(top,'answer_eligibility','')})['readable']:
        return None
    if question:
        from .answer_relevance import requested_aspects, _tokens
        if any(not (_tokens(text) & aspect) for aspect in requested_aspects(question)):
            return None
    if re.search(r"(?im)^\s*(?:doc_type|article_id|alternate_questions)\s*:", text):
        return None
    if len(text) < 30:
        return None
    if question and getattr(top,'answer_eligibility','')!='verified_passage_only':
        from .answer_relevance import requested_aspects, condition_specificity, _tokens
        aspects = requested_aspects(question)
        sentences = re.split(r"(?<=[.!؟])\s+|\n+", text)
        candidates = []
        for index, sentence in enumerate(sentences):
            if aspects and 30 <= len(sentence) <= 650 and all(_tokens(sentence) & group for group in aspects):
                # Keep adjacent eligibility/exception sentences with the quote.
                selected = sentence
                if index + 1 < len(sentences) and re.match(r"\s*(?:بشرط|فقط|باستثناء|يشترط|provided|only|except|subject to)\b", sentences[index + 1], re.I):
                    selected += " " + sentences[index + 1]
                candidates.append(selected)
        if candidates:
            text = max(candidates, key=lambda candidate: (condition_specificity(candidate), -len(candidate)))
    # Keep source wording and complete sentences. The indexed chunks are bounded.
    if len(text) > 1400:
        end = max(text.rfind("\n", 0, 1400), text.rfind(". ", 0, 1400), text.rfind("؟", 0, 1400))
        return None
    return text
