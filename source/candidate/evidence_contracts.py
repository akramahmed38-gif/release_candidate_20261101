"""Source-bound selection, view admission and output completeness contracts.

This module does not read originals, infer policy or prove interpretation.
The existing registry/source checker must verify current source bytes before
selection and recheck its request snapshot before emission.

Normal view admission requires an administratively authenticated external
approval registry. Matching strings/digests here verify its bindings, not the
identity or authority of a human. No approvals are created by this module.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata

SCHEMA_VERSION = "EVIDENCE_CONTRACTS_1"
HOLD_STATES = {"uncertain", "conflicting", "quarantined", "withheld", "unsafe",
               "stale", "revoked", "pending_review"}
QUALIFIER_KEYS = {"channel", "transaction", "conditions", "period", "timeframe",
                  "effective_from", "effective_to", "procedure", "trigger"}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _same(a, b):
    return _canonical(a) == _canonical(b)


def _rows(facts):
    if isinstance(facts, dict):
        return dict(facts)
    return {f["fact_id"]: f for f in facts}


def _entry(request, adapter):
    value = adapter.get(request.get("intent_id")) if isinstance(adapter, dict) else None
    if isinstance(value, str):
        value = {"topic": value}
    if not isinstance(value, dict) or not isinstance(value.get("topic"), str) or not value["topic"]:
        return None
    if request.get("topic") is not None and request["topic"] != value["topic"]:
        return None
    return value


def route_for_request(request, adapter):
    """Language-mode routing does not establish source or view eligibility."""
    entry = adapter.get(request.get('intent_id'), {})
    if not isinstance(entry, dict):
        return None
    overrides = entry.get('mode_routes', {})
    if isinstance(overrides, dict) and request.get('mode') in overrides:
        return overrides[request['mode']]
    return entry.get('route')


def _issue(code, **fields):
    return {"code": code, **fields}


def _binding_issue(fact, definition):
    fid = fact.get("fact_id")
    for field in ("service_id", "source_document", "source_sha256", "source_unit_id", "unit_text_sha256"):
        if not isinstance(fact.get(field), str) or not fact[field]:
            return _issue("source_binding_missing", fact_id=fid, field=field)
    if not fact.get("locator"):
        return _issue("source_locator_missing", fact_id=fid)
    if fact.get("view_source_sha256") != fact["source_sha256"]:
        return _issue("view_source_version_mismatch", fact_id=fid)
    sources = definition.get("sources", {})
    if fact["source_document"] not in sources or sources[fact["source_document"]] != fact["source_sha256"]:
        return _issue("source_version_mismatch", fact_id=fid)
    if "review_bindings" in definition:
        binding = definition["review_bindings"].get(fid)
        if not isinstance(binding, dict):
            return _issue("review_binding_missing", fact_id=fid)
        if any(not _same(fact.get(k), v) for k, v in binding.items()):
            return _issue("review_binding_changed", fact_id=fid)
    state = fact.get("review_state", fact.get("status"))
    if state is not None and not isinstance(state, str):
        return _issue("review_state_structure_unresolved", fact_id=fid)
    if state in HOLD_STATES:
        return _issue("evidence_held", fact_id=fid, state=state)
    return None


def _scope_issue(fact, request, entry):
    scope = fact.get("scope")
    if not isinstance(scope, dict):
        return "scope_metadata_missing"
    if request.get('mode') == 'procedure_query' and request.get('intent_id') != 'workflow':
        if scope.get('procedure_for_intent') != request.get('intent_id'):
            return 'operation_procedure_binding_missing'
        if not fact.get('atomic_group') or not isinstance(fact.get('sequence_order'), int):
            return 'ordered_operation_procedure_metadata_missing'
    channels = request.get("channels", [])
    if not isinstance(channels, list) or any(not isinstance(c, str) or not c for c in channels):
        return "request_channel_structure_unresolved"
    channel = fact.get("required_channel")
    if channel is not None and channel in request.get("excluded_channels", []):
        return "explicitly_excluded_channel"
    if channel is not None:
        if not channels:
            return "requested_channel_missing"
        if channel not in channels:
            return "channel_mismatch"
    elif channels:
        # An unspecified source channel is not proof that all channels apply.
        declared = scope.get("channel_id")
        aliases = entry.get("channel_scope_bindings", {})
        supported = [declared] if isinstance(declared, str) else []
        for c, values in aliases.items():
            if isinstance(values, list) and scope.get("channel") in values:
                supported.append(c)
        for c, contracts in entry.get("procedure_channel_bindings", {}).items():
            if isinstance(contracts,list) and fact.get("procedure_contract") in contracts:
                supported.append(c)
        if not set(channels) <= set(supported):
            return "requested_channel_not_established"
    period = request.get("period", request.get("timeframe"))
    if period is not None:
        declared = scope.get("period", scope.get("timeframe"))
        if declared is None or not _same(period, declared):
            return "period_not_established"
    conditions = request.get("conditions", [])
    if not isinstance(conditions, list):
        return "request_condition_structure_unresolved"
    declared_conditions = fact.get("conditions", scope.get("conditions", []))
    for condition in conditions:
        if isinstance(condition, str):
            if condition not in list(scope.values()) and condition not in (declared_conditions if isinstance(declared_conditions, list) else []):
                return "condition_not_established"
        elif isinstance(condition, dict):
            # A requested attribute/completeness obligation constrains the
            # selected bundle, rather than inventing a customer condition.
            # Its source-bound proof is checked after dependency expansion.
            if condition.get('type') in {'preserve_source_condition','requested_attribute'}:
                continue
            if isinstance(condition.get("predicate"), str):
                name = condition["predicate"]
                if "value" not in condition or condition["value"] is None or name not in scope or not _same(scope[name], condition["value"]):
                    if not isinstance(declared_conditions, list) or not any(_same(condition, c) for c in declared_conditions):
                        return "condition_not_established"
            else:
                fields = {k: v for k, v in condition.items() if k not in {"source", "role", "span", "evidence_span"}}
                if not fields or any(v is None or k not in scope or not _same(scope[k], v) for k, v in fields.items()):
                    return "condition_not_established"
        else:
            return "request_condition_structure_unresolved"
    procedure = request.get("procedure_scope")
    if entry["topic"] == "workflow":
        if not isinstance(procedure, str) or not procedure:
            return "procedure_scope_missing"
        targets = {procedure}
        aliases = entry.get("procedure_scope_bindings", {})
        if isinstance(aliases.get(procedure), list):
            targets.update(aliases[procedure])
        if fact.get("procedure_contract") not in targets and scope.get("procedure") not in targets:
            return "procedure_scope_not_established"
    return None


def _sort_ids(ids, declared):
    return sorted(ids, key=lambda fid: (declared[fid].get("sequence_order") or 0, fid))


def _attribute_text(value):
    value = "".join(char for char in unicodedata.normalize("NFKC", value)
                    if not unicodedata.combining(char))
    return value.casefold().translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}))


def _positive_identity_attribute(body, name):
    """Conservative proof inside one source identity assertion or typed field."""
    value = _attribute_text(body)
    subject = re.search(r'\b(?:national\s+id|identity\s+(?:card|document)|id\s+card|id)\b|بطاقه|هويه', value)
    if not subject:
        return False
    aliases = {
        "original": r'\boriginal(?:ity)?\b|(?<!\w)(?:و?اصلي(?:ه)?|اصل)(?!\w)',
        "valid": r'\bvalid(?:ity)?\b|(?<!\w)(?:و?ساري(?:ه)?|و?صالح(?:ه)?)(?!\w)',
    }
    for attribute in re.finditer(aliases[name], value):
        start = min(subject.start(), attribute.start())
        end = max(subject.end(), attribute.end())
        if end - start > 100 or re.search(r'[.;؛!?؟]', value[start:end]):
            continue
        before = value[max(0, attribute.start()-30):attribute.start()]
        if re.search(r'\b(?:not|no|without)\s+(?:an?\s+)?$|(?:و?غير|و?ليس(?:ت)?|لا|مش)\s*$', before):
            continue
        clause_start = max(value.rfind(";", 0, start), value.rfind("؛", 0, start), value.rfind(".", 0, start)) + 1
        clause_end = min([x for x in [value.find(";", end), value.find("؛", end), value.find(".", end)] if x >= 0] or [len(value)])
        clause = value[clause_start:clause_end]
        if re.search(r'\bnot\s+required\b|\bnot\s+necessary\b|غير\s+(?:مطلوب|مطلوبه|لازم|لازمه)', clause):
            continue
        return True
    return False


def requested_attribute_support(fact, topic, name):
    """Prove an attribute from current source metadata/Arabic, never English.

    This is source-scope support, not fidelity/currentness approval.  The caller
    must already enforce record/source/version bindings and view admission.
    A valid ID does not imply an original ID and an English draft cannot add
    either property to the authoritative Arabic assertion.
    """
    if not isinstance(fact, dict) or not isinstance(fact.get("scope"), dict) or not isinstance(name, str):
        return False
    if name == "fee_floor":
        return type(fact["scope"].get("minimum_fee_egp")) in {int, float}
    if name not in {"original", "valid"} or topic != "identity" or not isinstance(fact.get("selection_tags"), list) or "identity" not in fact["selection_tags"]:
        return False
    required_document = fact["scope"].get("required_document")
    if isinstance(required_document, str) and _positive_identity_attribute(required_document, name):
        return True
    arabic = fact.get("arabic")
    expected_hash = fact.get("arabic_sha256")
    return (isinstance(arabic, str) and isinstance(expected_hash, str)
            and _text_hash(arabic) == expected_hash
            and _positive_identity_attribute(arabic, name))


def select_for_request(request, facts, definition, adapter):
    """Select metadata under one exact service/topic/channel/condition scope.

    facts are current records accepted by the existing registry. definition
    retains declared records, allowing missing workflow members to be detected.
    View admission is separate; eligible here means source/scope eligible only.
    """
    supplied = _rows(facts)
    declared = _rows(definition.get("facts", []))
    gaps = []
    conflicts = []
    result = {"required_fact_ids": [], "eligible_fact_ids": [], "gaps": gaps,
              "conflicts": conflicts, "contract_version": SCHEMA_VERSION,
              "eligibility_kind": "source_scope_only_view_approval_required_separately"}
    if not isinstance(request, dict):
        gaps.append(_issue("request_structure_unresolved"))
        return result
    entry = _entry(request, adapter)
    service = request.get("service_id")
    if not isinstance(service, str) or not service:
        gaps.append(_issue("service_scope_unresolved"))
        return result
    if request.get('service_namespace')=='linguistic_domain_only':
        gaps.append(_issue('language_domain_is_not_source_service',domain=request.get('domain_id')))
        return result
    if entry is None:
        gaps.append(_issue("intent_to_topic_mapping_unresolved", intent_id=request.get("intent_id")))
        return result
    topic = entry["topic"]
    if request.get('mode') == 'procedure_query' and topic != 'workflow':
        gaps.append(_issue('operation_procedure_evidence_mapping_unresolved', intent_id=request.get('intent_id')))
        return result
    bundle_topics = entry.get("bundle_topics", [])
    if not isinstance(bundle_topics, list) or any(not isinstance(name, str) or not name for name in bundle_topics):
        gaps.append(_issue("intent_bundle_structure_unresolved"))
        return result
    facets = request.get("requested_facets", [])
    if (not isinstance(facets, list) or any(not isinstance(name, str) or not name for name in facets)
            or any(name not in {"amount_only"} for name in facets)):
        gaps.append(_issue("request_facet_structure_unresolved"))
        return result
    if request.get("generation") is not None and request["generation"] != definition.get("source_content_generation"):
        gaps.append(_issue("request_generation_mismatch"))
        return result
    root_topics = set(bundle_topics or [topic])
    roots = [f for f in declared.values() if f.get("service_id") == service
             and root_topics.intersection(f.get("selection_tags", []))]
    procedure_member_ids = request.get("procedure_member_ids", [])
    if procedure_member_ids:
        if topic != "workflow" or not isinstance(procedure_member_ids, list) or any(
                not isinstance(fact_id, str) or fact_id not in declared for fact_id in procedure_member_ids):
            gaps.append(_issue("procedure_member_projection_invalid"))
            return result
        projected = [declared[fact_id] for fact_id in procedure_member_ids]
        if any(fact.get("service_id") != service or "workflow" not in fact.get("selection_tags", [])
               or not fact.get("atomic_group") or not isinstance(fact.get("sequence_order"), int)
               for fact in projected):
            gaps.append(_issue("procedure_member_projection_scope_mismatch"))
            return result
        if len({fact.get("atomic_group") for fact in projected}) != 1:
            gaps.append(_issue("procedure_member_projection_group_mismatch"))
            return result
        roots = projected
    if "amount_only" in facets:
        if topic != "initial_deposit":
            gaps.append(_issue("requested_facet_not_applicable", name="amount_only", topic=topic))
            return result
        # The request explicitly asks only for the activation amount.  Select
        # the source assertion proving that amount, not a second assertion
        # whose distinct contribution is the balance disposition.  This is a
        # source-metadata filter; it never supplies or rewrites a value.
        roots = [f for f in roots
                 if type(f.get("scope", {}).get("minimum_initial_deposit_egp")) in {int, float}
                 and "balance_treatment" not in f.get("scope", {})]
    if not roots:
        gaps.append(_issue("no_declared_evidence_for_scope", service_id=service, topic=topic))
        return result
    selected = set()
    rejected_scope = []
    for fact in roots:
        reason = _scope_issue(fact, request, entry)
        if reason:
            rejected_scope.append((fact["fact_id"], reason))
        else:
            selected.add(fact["fact_id"])
    if not selected:
        for reason in sorted({reason for _, reason in rejected_scope}):
            gaps.append(_issue(reason))
        return result
    # Every requested channel needs its own fact, not a supported subset.
    requested_channels = set(request.get("channels", []))
    matched_channels = {declared[fid].get("required_channel") for fid in selected}
    if requested_channels and not None in matched_channels:
        for channel in sorted(requested_channels - matched_channels):
            gaps.append(_issue("requested_channel_without_evidence", channel=channel))
    workflow = topic == "workflow"
    groups = {declared[fid].get("atomic_group") for fid in selected} - {None}
    if workflow and not procedure_member_ids:
        for group in groups:
            selected.update(fid for fid, f in declared.items()
                            if f.get("service_id") == service and f.get("atomic_group") == group)
    # Dependencies from an ordered group are not automatically prerequisites
    # for a separately tagged narrow condition query (e.g. branch visit only).
    pending = list(selected)
    while pending:
        fid = pending.pop()
        fact = declared[fid]
        for dep in fact.get("dependencies", []):
            other = declared.get(dep)
            if other is None:
                gaps.append(_issue("declared_dependency_missing", fact_id=fid, dependency=dep))
                continue
            narrow_sequence_projection = (not workflow or bool(procedure_member_ids)) and fact.get("atomic_group") and other.get("atomic_group") == fact["atomic_group"]
            if narrow_sequence_projection:
                continue
            if other.get("service_id") != service:
                gaps.append(_issue("cross_service_dependency_not_authorized", fact_id=fid, dependency=dep))
                continue
            if dep not in selected:
                selected.add(dep)
                pending.append(dep)
    required = _sort_ids(selected, declared)
    eligible = set()
    for fid in required:
        current = supplied.get(fid)
        if current is None:
            gaps.append(_issue("current_fact_or_dependency_missing", fact_id=fid))
            continue
        if current.get("service_id") != service:
            gaps.append(_issue("current_fact_provider_mismatch", fact_id=fid))
            continue
        if current.get("fact_id") != fid:
            gaps.append(_issue("current_record_id_mismatch", fact_id=fid))
            continue
        binding_keys = (
            "service_id", "source_document", "source_sha256", "source_unit_id",
            "unit_text_sha256", "view_source_sha256", "revision", "scope",
            "aspect", "selection_tags", "required_channel", "dependencies",
            "atomic_group", "sequence_order", "arabic_sha256", "english_sha256",
        )
        if any(not _same(current.get(k), declared[fid].get(k)) for k in binding_keys):
            gaps.append(_issue("declared_record_version_mismatch", fact_id=fid))
            continue
        reason = _binding_issue(current, definition)
        if reason:
            gaps.append(reason)
            continue
        if _scope_issue(current, request, entry):
            gaps.append(_issue("current_fact_scope_mismatch", fact_id=fid))
            continue
        eligible.add(fid)
    # Detect competing values only within the same declared business predicate
    # and qualifier scope. Do not resolve by filename, timestamp or majority.
    competing = defaultdict(list)
    for fid in eligible:
        f = supplied[fid]
        scope = f.get("scope", {})
        key = f.get("conflict_key") or _hash([
            service, f.get("aspect"), f.get("required_channel"),
            {k: v for k, v in scope.items() if k in QUALIFIER_KEYS},
        ])
        values = {k: v for k, v in scope.items() if k not in QUALIFIER_KEYS}
        competing[key].append((fid, _hash(values)))
    for key, rows in competing.items():
        if len({value for _, value in rows}) > 1:
            ids = sorted(fid for fid, _ in rows)
            conflicts.append({"code": "competing_scoped_values", "scope_key": key, "fact_ids": ids})
            eligible.difference_update(ids)
    if workflow and not procedure_member_ids:
        for group in groups:
            members = {fid for fid in selected if declared[fid].get("atomic_group") == group}
            orders = sorted(declared[fid].get("sequence_order") for fid in members
                            if type(declared[fid].get("sequence_order")) is int)
            if len(orders) != len(members) or orders != list(range(1, len(members) + 1)):
                gaps.append(_issue("procedure_sequence_metadata_incomplete", atomic_group=group))
                eligible.difference_update(members)
            if not members <= eligible:
                gaps.append(_issue("atomic_procedure_incomplete", atomic_group=group,
                                   missing_fact_ids=sorted(members - eligible)))
                eligible.difference_update(members)
    for condition in request.get('conditions',[]):
        if not isinstance(condition,dict):continue
        kind=condition.get('type');name=condition.get('name')
        if kind=='preserve_source_condition':
            obligation=entry.get('completeness_obligations',{}).get(name)
            proven=isinstance(obligation,dict) and any(obligation.get('required_tag') in supplied[fid].get('selection_tags',[]) and all(supplied[fid].get('scope',{}).get(k)==v for k,v in obligation.get('scope',{}).items()) for fid in eligible)
            if not proven:gaps.append(_issue('source_condition_obligation_unproven',name=name));eligible.clear()
        elif kind=='requested_attribute':
            supporting = [fid for fid in eligible if requested_attribute_support(supplied[fid], topic, name)]
            if not supporting:
                gaps.append(_issue('requested_attribute_not_established',name=name));eligible.clear()
            else:
                result.setdefault('requested_attribute_evidence', []).append({'name':name,'fact_ids':_sort_ids(supporting, declared)})
    full_inventory = bool(request.get("full_inventory") or request.get("exhaustive") or
                          request.get("requires_full_inventory_assertion") or
                          entry.get("requires_full_inventory_assertion"))
    if full_inventory:
        certificates = definition.get("completeness_certificates", [])
        valid = []
        for cert in certificates:
            if cert.get("status") != "source_verified_complete" or cert.get("service_id") != service or cert.get("topic") != topic:
                continue
            if set(cert.get("fact_ids", [])) != selected or not cert.get("locator") or not cert.get("source_unit_id"):
                continue
            if definition.get("sources", {}).get(cert.get("source_document")) != cert.get("source_sha256"):
                continue
            if not _same(cert.get("channels", []), request.get("channels", [])) or not _same(cert.get("conditions", []), request.get("conditions", [])):
                continue
            if not _same(cert.get("period"), request.get("period", request.get("timeframe"))):
                continue
            valid.append(cert)
        if not valid:
            gaps.append(_issue("full_inventory_certificate_missing_or_incompatible"))
    result["required_fact_ids"] = required
    result["eligible_fact_ids"] = _sort_ids(eligible, declared)
    return result


def _date_valid(record):
    try:
        stamp = datetime.fromisoformat(record["approved_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
            return False
        if record.get("valid_until"):
            end = datetime.fromisoformat(record["valid_until"].replace("Z", "+00:00"))
            if end.tzinfo is None or end < datetime.now(timezone.utc):
                return False
        return True
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def approve_view(fact, language, approval_registry, fixture_mode=False, authorized_fixture_ids=()):
    """Admit an exact view; never manufacture approvals.

    An external registry must already be authenticated by its administrator.
    This checks trusted reference/record bindings, not human identity itself.
    Fixture admission is explicitly separate from normal runtime eligibility.
    """
    key = "english" if language in {"en", "english"} else "arabic" if language in {"ar", "arabic"} else None
    if any(not isinstance(fact.get(k), str) or not fact[k]
           for k in ("fact_id", "service_id", "source_document", "source_unit_id", "unit_text_sha256")):
        return False
    if not isinstance(fact.get("arabic"), str) or _text_hash(fact["arabic"]) != fact.get("arabic_sha256"):
        return False
    if key is None or not isinstance(fact.get(key), str) or not fact[key]:
        return False
    if _text_hash(fact[key]) != fact.get(key + "_sha256"):
        return False
    if not fact.get("source_sha256") or fact.get("view_source_sha256") != fact["source_sha256"]:
        return False
    revision = fact.get("revision")
    if type(revision) is not int or revision < 1:
        return False
    if fixture_mode:
        return (
            fact.get("fact_id") in set(authorized_fixture_ids)
            and fact.get("authorized_fixture_revision") == revision
            and not any(fact.get(k) is True for k in
                        ("normal_runtime_eligible", "business_approved", "human_fidelity_approved"))
        )
    if fact.get("normal_runtime_eligible") is not True or fact.get("test_fixture_only") is True:
        return False
    registry = approval_registry if isinstance(approval_registry, dict) else {}
    records = registry.get("records", [])
    verified = registry.get("verified_external_approvals", {})
    trusted = set(registry.get("trusted_registry_ids", []))
    required = {"currentness", "fidelity"} if key == "english" else {"currentness"}
    accepted = set()
    for record in records:
        if not isinstance(record, dict) or record.get("status") != "approved" or record.get("test_only") is True:
            continue
        kind = record.get("approval_kind")
        if kind not in required or not record.get("reviewer_id") or not _date_valid(record):
            continue
        expected_role = "authorized_bilingual_reviewer" if kind == "fidelity" else "authorized_service_owner"
        if record.get("reviewer_role") != expected_role:
            continue
        bindings = {
            "fact_id": fact.get("fact_id"), "service_id": fact.get("service_id"),
            "source_document": fact.get("source_document"), "source_sha256": fact.get("source_sha256"),
            "source_unit_id": fact.get("source_unit_id"), "unit_text_sha256": fact.get("unit_text_sha256"),
            "revision": revision, "language": "en" if key == "english" else "ar",
            "view_sha256": fact[key + "_sha256"], "scope_sha256": _hash(fact.get("scope", {})),
        }
        if any(not _same(record.get(k), v) for k, v in bindings.items()):
            continue
        ref = record.get("approval_ref")
        receipt = verified.get(ref) if isinstance(ref, str) and ref else None
        if not isinstance(receipt, dict) or receipt.get("registry_id") not in trusted or not receipt.get("verification_ref") or receipt.get("test_only") is True:
            continue
        if receipt.get("record_sha256") != _hash(record):
            continue
        accepted.add(kind)
    return required <= accepted


def completeness_review(requests, emitted_fact_ids, citations, facts, definition,
                        adapter, language="en", approval_registry=None,
                        fixture_mode=False, authorized_fixture_ids=()):
    """Check output against requested metadata obligations, not semantic truth.

    A caller must separately challenge whether requests captured the original
    question. This contract does not claim independent semantic verification.
    """
    contract = requests if isinstance(requests, dict) else None
    requests = contract.get("requests", []) if contract is not None else requests
    current = _rows(facts)
    emitted_order = list(emitted_fact_ids)
    emitted = set(emitted_order)
    required = set()
    eligible = set()
    gaps = []
    conflicts = []
    scopes = []
    if contract is not None and (contract.get("decision") == "clarify" or contract.get("unresolved_spans")):
        gaps.append(_issue("request_interpretation_unresolved"))
    for request in requests:
        result = select_for_request(request, current, definition, adapter)
        required.update(result["required_fact_ids"])
        eligible.update(result["eligible_fact_ids"])
        gaps.extend(result["gaps"])
        conflicts.extend(result["conflicts"])
        scopes.append({"request_id": request.get("request_id"), **result})
    unapproved = sorted(fid for fid in emitted if fid in current and not approve_view(
        current[fid], language, approval_registry, fixture_mode, authorized_fixture_ids))
    violations = []
    for fid in sorted(emitted - eligible):
        violations.append(_issue("emitted_fact_outside_eligible_scope", fact_id=fid))
    for fid in unapproved:
        violations.append(_issue("view_not_admitted", fact_id=fid))
    for request, review in zip(requests, scopes):
        mapped = _entry(request, adapter)
        if mapped is None or mapped["topic"] != "workflow":
            continue
        required_order = review["required_fact_ids"]
        actual_order = [fid for fid in emitted_order if fid in set(required_order)]
        if actual_order and actual_order != required_order:
            violations.append(_issue("procedure_order_or_completeness_mismatch",
                                     request_id=request.get("request_id"),
                                     expected_fact_ids=required_order,
                                     actual_fact_ids=actual_order))
    if contract is not None:
        for excluded in contract.get("excluded_requests", []):
            mapped = _entry(excluded, adapter)
            if mapped is None:
                continue
            for fid in emitted & set(current):
                f = current[fid]
                if f.get("service_id") != excluded.get("service_id") or mapped["topic"] not in f.get("selection_tags", []):
                    continue
                # A comparison-local provider exclusion cannot suppress a new,
                # independently evidenced request outside that task group.
                scoped_groups = excluded.get("exclusion_scope_groups")
                if scoped_groups is not None and any(
                    r.get("scope_group") is not None
                    and r.get("scope_group") not in scoped_groups
                    and r.get("service_id") == f.get("service_id")
                    and fid in review["eligible_fact_ids"]
                    for r, review in zip(requests, scopes)):
                    continue
                # Only an explicit amount-only funding projection may bypass
                # an excluded balance view, and only when the source scope has
                # no balance-treatment value.  Arbitrary multi-tag records are
                # not safe: their full rendering could state the excluded
                # concept even when another topic selected them.
                safe_amount_projection = any(
                    fid in other_review["eligible_fact_ids"]
                    and other_request.get("service_id") == f.get("service_id")
                    and "amount_only" in other_request.get("requested_facets", [])
                    and (_entry(other_request, adapter) or {}).get("topic") == "initial_deposit"
                    and mapped["topic"] == "balance_treatment"
                    and "balance_treatment" not in f.get("scope", {})
                    for other_request, other_review in zip(requests, scopes))
                if safe_amount_projection:
                    continue
                channels = excluded.get("channels", [])
                if not channels or f.get("required_channel") in channels:
                    # Excluding recital of a complete procedure does not
                    # exclude an independently requested narrow condition
                    # merely because its source line is also a sequence step.
                    positive_narrow = any(
                        (_entry(r, adapter) or {}).get("topic") != "workflow"
                        and r.get("service_id") == f.get("service_id")
                        and fid in review["eligible_fact_ids"]
                        for r, review in zip(requests, scopes))
                    positive_full = any(
                        (_entry(r, adapter) or {}).get("topic") == "workflow"
                        and r.get("service_id") == f.get("service_id")
                        for r in requests)
                    if mapped["topic"] == "workflow" and positive_narrow and not positive_full:
                        continue
                    violations.append(_issue("excluded_scope_emitted", fact_id=fid))
    citation_violations = []
    cited = set()
    if not isinstance(citations, list):
        citation_violations.append(_issue("citation_collection_invalid"))
        citations = []
    for citation in citations:
        if not isinstance(citation, dict):
            citation_violations.append(_issue("citation_structure_invalid"))
            continue
        fid = citation.get("fact_id")
        fact = current.get(fid)
        if fid not in emitted or fact is None:
            citation_violations.append(_issue("citation_not_for_emitted_fact", fact_id=fid))
            continue
        binding = {
            "service_id": fact["service_id"], "source_document": fact["source_document"],
            "source_sha256": fact["source_sha256"], "unit_text_sha256": fact["unit_text_sha256"],
            "locator": fact["locator"],
        }
        bad = [k for k, value in binding.items() if not _same(citation.get(k), value)]
        unit = citation.get("evidence_unit_id", citation.get("source_unit_id"))
        if unit != fact["source_unit_id"]:
            bad.append("evidence_unit_id")
        if "source_unit_id" in citation and citation["source_unit_id"] != fact["source_unit_id"]:
            bad.append("source_unit_id")
        if bad:
            citation_violations.append(_issue("citation_binding_mismatch", fact_id=fid, fields=sorted(set(bad))))
        else:
            cited.add(fid)
    for fid in sorted(emitted - cited):
        citation_violations.append(_issue("supporting_citation_missing", fact_id=fid))
    missing = sorted(required - emitted)
    unrelated = sorted(emitted - required)
    return {
        "contract_version": SCHEMA_VERSION, "request_reviews": scopes,
        "required_fact_ids": sorted(required), "eligible_fact_ids": sorted(eligible),
        "missing_fact_ids": missing, "unrelated_fact_ids": unrelated,
        "scope_violations": violations, "citation_violations": citation_violations,
        "gaps": gaps, "conflicts": conflicts, "unapproved_view_fact_ids": unapproved,
        "complete": bool(emitted) and not (missing or unrelated or violations or citation_violations or gaps or conflicts),
        "semantic_independence_claimed": False,
        "source_freshness_checker_required": True,
    }
