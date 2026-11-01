"""Role-qualified LANGUAGE proposals from authored v1/v2 annotations.

These records do not describe the current user's request. In particular, an
example's excluded or hypothetical meaning never becomes a positive intent.
Service/channel bindings and business/evaluation data are not exported.
"""
from collections import Counter
import hashlib
import json
import math
import re
import unicodedata

ROLE_NAMES = {
    "requested": "requested", "positive": "requested",
    "excluded": "excluded", "negative": "excluded",
    "context": "context", "background": "context",
    "hypothetical": "hypothetical", "user_scenario": "hypothetical",
    "contrast": "contrast", "user_claim": "user_claim",
}
COLLECTIONS = {
    "requests": "requested", "requested_requests": "requested",
    "positive_requests": "requested", "positive": "requested",
    "excluded_requests": "excluded", "negative_requests": "excluded",
    "negative": "excluded", "context_mentions_not_requests": "context",
    "context_mentions": "context", "background_mentions": "context",
    "hypotheticals": "hypothetical", "hypothetical_requests": "hypothetical",
    "user_scenarios": "hypothetical", "contrasts": "contrast",
    "contrast_requests": "contrast", "user_claims_not_evidence": "user_claim",
    "user_claims": "user_claim",
}
PLAN_METADATA = {"decision", "ambiguity", "action_authorization"}
FORBIDDEN_FIELDS = {
    "fact_id", "fact_ids", "facts", "expected_fact_ids", "required_fact_ids",
    "supported_fact_ids", "expected_business", "source_bindings",
    "business_rules", "policy_approval",
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _forbidden(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_FIELDS:
                return True
            if key == "business_answer" and item is not None:
                return True
            if key in {"business_approved", "normal_runtime_eligible", "business_truth"} and item is True:
                return True
            if _forbidden(item):
                return True
    elif isinstance(value, list):
        return any(_forbidden(item) for item in value)
    return False


def _record(row, role, collection, slot, annotation, reason=None, parent_id=None):
    source_id = annotation.get("request_id") if isinstance(annotation, dict) else None
    has_source_id = isinstance(source_id, str) and bool(source_id)
    slot_id = source_id if has_source_id else "@" + collection + ":" + str(slot + 1).zfill(4)
    intent = annotation.get("intent_id") if isinstance(annotation, dict) else None
    if not isinstance(intent, str) or not intent:
        intent = None
    label = ""
    if isinstance(annotation, str):
        label = annotation
    elif isinstance(annotation, dict):
        label = next((annotation[k] for k in ("claim", "predicate", "type", "text", "label")
                      if isinstance(annotation.get(k), str)), "")
    # Only authored language and a single role-qualified intent are searchable.
    # No source service/channel, expected fact set or answer is copied.
    body = {
        "question": row.get("question", "") if role != "unresolved" else "",
        "role": role,
        "intent_id": intent if role != "unresolved" else None,
        "annotation_label": label if role != "unresolved" else "",
    }
    provenance = {
        "case_id": row["case_id"],
        "family_id": row.get("family_id"),
        "annotation_version": row.get("annotation_version"),
        "language": row.get("language"),
        "collection": collection,
        "annotation_slot": slot,
        "source_request_id": source_id if isinstance(source_id, str) else None,
        "generated_slot_id": not has_source_id,
        "parent_request_id": parent_id,
        "source_example_sha256": _hash(row),
        "source_annotation_sha256": _hash(annotation),
    }
    return {
        "record_id": row["case_id"] + ":" + role + ":" + slot_id,
        "case_id": row["case_id"],
        "role": role,
        "polarity": "positive" if role == "requested" else "negative" if role == "excluded" else "nonassertive",
        "intent_id": body["intent_id"],
        "body_text": body["question"] + ("\n" + body["annotation_label"] if body["annotation_label"] else ""),
        "body_sha256": _hash(body),
        "annotation_provenance": provenance,
        "candidate_only": True,
        "committed": False,
        "business_evidence": False,
        "runtime_fact_eligible": False,
        "source_scope_binding_allowed": False,
        "unresolved_reason": reason,
    }


def _unresolved(row, collection, slot, annotation, reason):
    return _record(row, "unresolved", collection, slot, annotation, reason)


def _role_records(row):
    if _forbidden(row):
        return [_unresolved(row, "@example", 0, {}, "business_or_evaluation_bindings_rejected")]
    plan = row.get("expected_plan")
    if not isinstance(row.get("question"), str) or not row["question"].strip() or not isinstance(plan, dict):
        return [_unresolved(row, "@example", 0, {}, "unsupported_example_structure")]
    output = []
    for key, value in plan.items():
        if key in PLAN_METADATA:
            continue
        if key == "relations":
            if not isinstance(value, list):
                output.append(_unresolved(row, key, 0, value, "annotation_collection_not_array"))
                continue
            for slot, item in enumerate(value):
                kind = item.get("type") if isinstance(item, dict) else None
                if isinstance(kind, str) and kind.startswith(("compare", "contrast")):
                    output.append(_record(row, "contrast", key, slot, item))
                else:
                    output.append(_unresolved(row, key, slot, item, "unsupported_relation_role"))
            continue
        role = COLLECTIONS.get(key)
        if role is None and key != "annotations":
            output.append(_unresolved(row, key, 0, {}, "unknown_annotation_collection"))
            continue
        if not isinstance(value, list):
            output.append(_unresolved(row, key, 0, {}, "annotation_collection_not_array"))
            continue
        for slot, item in enumerate(value):
            if not isinstance(item, (str, dict)):
                output.append(_unresolved(row, key, slot, {}, "unsupported_annotation_structure"))
                continue
            stated = item.get("role") if isinstance(item, dict) else None
            explicit = ROLE_NAMES.get(stated) if isinstance(stated, str) else None
            if stated is not None and (explicit is None or (role is not None and explicit != role)):
                output.append(_unresolved(row, key, slot, item, "unknown_or_conflicting_annotation_role"))
                continue
            effective = role or explicit
            if effective is None:
                output.append(_unresolved(row, key, slot, item, "missing_annotation_role"))
                continue
            if effective in {"requested", "excluded"} and (not isinstance(item, dict) or not isinstance(item.get("intent_id"), str)):
                output.append(_unresolved(row, key, slot, item, "untyped_request_annotation"))
                continue
            output.append(_record(row, effective, key, slot, item))
            if isinstance(item, dict) and "conditions" in item:
                conditions = item["conditions"]
                if not isinstance(conditions, list):
                    output.append(_unresolved(row, key + ".conditions", slot, {}, "condition_collection_not_array"))
                    continue
                parent_id = item.get("request_id")
                for condition_slot, condition in enumerate(conditions):
                    path = key + "." + str(slot + 1) + ".conditions"
                    if isinstance(condition, dict) and (
                        condition.get("source") == "user_scenario" or
                        ROLE_NAMES.get(condition.get("role")) == "hypothetical"
                    ):
                        output.append(_record(row, "hypothetical", path, condition_slot, condition, parent_id=parent_id))
                    else:
                        output.append(_unresolved(row, path, condition_slot, {}, "condition_authority_or_role_unresolved"))
    ids = Counter(r["record_id"] for r in output)
    if any(count > 1 for count in ids.values()):
        return [_unresolved(row, "@example", 0, {}, "duplicate_role_request_id")]
    return output


def records_from_examples(rows):
    """Return flat role-qualified records, including explicit unresolved records.

    Equal source examples deduplicate by case ID. Conflicting duplicate IDs
    suppress all proposals for that case rather than retaining the first one.
    """
    groups = {}
    malformed = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("case_id"), str) or not row["case_id"]:
            safe = row if isinstance(row, (dict, list, str, int, float, bool, type(None))) else type(row).__name__
            placeholder = {"case_id": "@invalid-" + _hash(safe)[:16], "question": "", "expected_plan": {}}
            malformed.append(_unresolved(placeholder, "@example", 0, {}, "missing_case_id_or_nonobject_example"))
            continue
        digest = _hash(row)
        groups.setdefault(row["case_id"], {})[digest] = row
    output = list(malformed)
    for case_id in sorted(groups):
        versions = groups[case_id]
        if len(versions) != 1:
            row = {"case_id": case_id, "question": "", "expected_plan": {}}
            record = _unresolved(row, "@example", 0, {}, "duplicate_case_id_conflict")
            record["annotation_provenance"]["conflicting_source_sha256"] = sorted(versions)
            output.append(record)
        else:
            output.extend(_role_records(next(iter(versions.values()))))
    return sorted(output, key=lambda r: r["record_id"])


def _tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub("[\u0640\u064b-\u065f\u0670]", "", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))
    # Preserve Franco digits and negation. This shadow is never the user graph.
    return re.findall(r"[a-z0-9]+(?:['.-][a-z0-9]+)*|[\u0621-\u064a]+", text)


def lexical_candidates(question, records, limit=12):
    """Nominate role-qualified language records; never commit current intent.

    The score is BM25 lexical similarity, not probability or interpretation
    confidence. Example service/channel metadata is absent by construction.
    """
    if not isinstance(question, str):
        raise TypeError("question must be text")
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    usable = [r for r in records if r.get("candidate_only") is True and r.get("committed") is False
              and r.get("business_evidence") is False and isinstance(r.get("body_text"), str)
              and r.get("role") in set(ROLE_NAMES.values()) and not r.get("unresolved_reason")]
    token_rows = [_tokens(r["body_text"]) for r in usable]
    if not usable or not limit:
        return []
    df = Counter(t for row in token_rows for t in set(row))
    average = sum(map(len, token_rows)) / len(token_rows) or 1
    query = set(_tokens(question))
    scored = []
    for record, row in zip(usable, token_rows):
        counts = Counter(row)
        score = 0.0
        for token in query:
            frequency = counts[token]
            if not frequency:
                continue
            idf = math.log(1 + (len(usable) - df[token] + .5) / (df[token] + .5))
            score += idf * frequency * 2.5 / (frequency + 1.5 * (.25 + .75 * len(row) / average))
        if score > 0:
            scored.append({
                "record_id": record["record_id"], "role": record["role"],
                "intent_id": record["intent_id"], "score": score,
                "score_kind": "bm25_candidate_similarity_not_probability",
                "body_sha256": record["body_sha256"],
                "annotation_provenance": dict(record["annotation_provenance"]),
                "candidate_only": True, "committed": False,
                "business_evidence": False, "runtime_fact_eligible": False,
                "source_scope_binding_allowed": False,
            })
    return sorted(scored, key=lambda r: (-r["score"], r["record_id"]))[:limit]
