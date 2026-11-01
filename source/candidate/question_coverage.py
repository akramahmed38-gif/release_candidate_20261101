"""Original-question surface demands, independent of planner commitments.

This side-effect-free audit never calls CurrentQueryPlanner.plan/predicate and
never reads example request graphs or evaluation expectations. It shares authored
linguistic vocabulary/span utilities and the existing evidence selector, so it is
not independent semantic entailment or a proof of universal question coverage.
"""
from pathlib import Path
from functools import lru_cache
import json
import re
import unicodedata
from linguistic_spans import (spans, tokens, shadow, forms,
                              qualified_catalog_entities, filter_predicate_entity_mentions, nominal_scalar_focus,
                              nominal_scope_omission, nominal_catalog_heads,
                              exclusive_temporal_scopes, temporal_scope_bindings, temporal_condition,
                              nonrestrictive_scalar_focus, temporal_context_fragment)
from evidence_contracts import select_for_request, requested_attribute_support
from procedure_projection import project_procedure_members,projection_covers_span
from dialogue_scope import additive_provider_reference,antecedent_scope
from entity_scope import entity_omission,entity_nonrestriction
from response_binding import binding_preservation_directive
from linguistic_spans import catalog_nominal_proofs,response_layout_directive
from linguistic_spans import response_scope_omission,fronted_process_contexts,principal_minimum_proofs,bind_dimension_channel_references
from linguistic_spans import transaction_reference_spans,valued_record_fields
from linguistic_spans import quoted_channel_reference,quote_envelope_fragment

ROOT = Path(__file__).resolve().parent
TARIFFS = {"deposit_tariff", "withdrawal_tariff"}
NONCORE_LIVE_INTENTS = {"complaint_status", "complaint_resolution_confirmation", "refund_status",
                        "transaction_status", "stock_availability", "inventory_count"}
NONCORE_INTENTS = NONCORE_LIVE_INTENTS | {
    "complaint_create", "refund_eligibility", "refund", "transaction_cancel", "product_return",
    "reprint", "callback", "response_draft", "repeat_payment", "transfer", "cash_reconciliation", "closure", "balance_limit",
}
IDENTITY_ATTRIBUTES = {
    "original": ["original", "originality", "اصل", "اصلي"],
    "valid": ["valid", "validity", "ساري", "سارية"],
}


@lru_cache(maxsize=1)
def _resources():
    def read(name):
        return json.loads((ROOT / "resources" / name).read_text(encoding="utf-8"))
    features = read("features.json")
    additions = read("recovery_features.json")
    for key, values in additions.items():
        features[key] = list(dict.fromkeys(features.get(key, []) + values))
    return features, read("channels.json"), read("adapter.json"), read("entity_roles.json")


@lru_cache(maxsize=1)
def _channel_parents():
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8")).get("channel_parents", {})


@lru_cache(maxsize=1)
def _catalog_intent_ids():
    rows = json.loads((ROOT / 'resources/intents.json').read_text(encoding='utf-8'))['intents']
    return tuple(row['intent_id'] for row in rows
                 if row['intent_id'] not in {'other_or_unknown', 'permission', 'explanation'})

@lru_cache(maxsize=1)
def _nominal_catalog_rows():
    return json.loads((ROOT/'resources/intents.json').read_text(encoding='utf-8'))['intents']


def _raw_product_context_entity(raw, hit, hits, roles, rules):
    """Apply catalog context rules locally; never discard a whole entity role.

    This is raw-span interpretation, independent of planner decisions and fact
    availability. A separately named operational profile remains a subject.
    """
    start, end, service = hit
    separators = [match for match in re.finditer(r'[;؛,،?!؟]|(?<!\d)\.(?!\d)', raw)
                  if not any(a <= match.start() < b for a, b, _ in hits)]
    left = max([0] + [match.end() for match in separators if match.end() <= start])
    right = min([len(raw)] + [match.start() for match in separators if match.start() >= end])
    products = [row for row in hits if left <= row[0] < right
                and roles.get(row[2], 'service') == 'service']
    if not products:
        return False
    for rule in rules:
        alias = any(shadow(raw[start:end])[0].strip() == shadow(value)[0].strip()
                    for value in rule.get('contextual_aliases', []))
        if (service in rule.get('candidates', []) and alias
                and not _hits(raw[left:right], rule.get('independent_qualifiers', []))):
            return True
        if roles.get(service) in rule.get('context_entity_roles', []):
            # Only an immediate grammatical platform complement is context.
            # Another independently requested clause is not covered by it.
            for _, stop in _hits(raw[left:start], rule.get('context_prepositions', [])):
                if set(tokens(raw[left + stop:start])) <= {'the', 'app', 'application', 'system'}:
                    return True
    return False


def _mark(raw, a, b, role):
    return {"start": a, "end": b, "text": raw[a:b], "role": role}


def _hits(raw, phrases):
    return sorted({(a, b) for phrase in phrases for a, b in spans(raw, phrase)})


def _entities(raw, definition, roles, features=None):
    rules_path = ROOT / "resources" / "entity_disambiguation.json"
    rules = json.loads(rules_path.read_text(encoding="utf-8"))
    hits = qualified_catalog_entities(raw, definition.get("service_profiles", {}), roles, rules)
    hits, _ = filter_predicate_entity_mentions(raw, hits, features or _resources()[0])
    chosen = [(h["start"], h["end"], h["service_id"]) for h in hits]
    # Qualified language is catalog data, never a vote by answer availability.
    # Limit each challenge to its actual clause so another service's qualifier
    # cannot resolve a bare acronym elsewhere in a multi-service question.
    for bounds in {(a, b) for a, b, _ in chosen}:
        owners = {s for a, b, s in chosen if (a, b) == bounds}
        if len(owners) < 2:
            continue
        a, b = bounds
        left = max([0] + [m.end() for m in re.finditer(r"[;؛,،?؟]", raw[:a])])
        following = re.search(r"[;؛,،?؟]", raw[b:])
        right = b + following.start() if following else len(raw)
        # An atomic brand's own words are not an external family qualifier.
        # Otherwise a longer full name can resolve to a shorter profile merely
        # because only that profile happened to list one name constituent.
        clause = raw[left:a] + ' '*(b-a) + raw[b:right]
        words = {}
        for sid in owners:
            profile = definition["service_profiles"][sid]
            words[sid] = {word for phrase in profile.get("aliases", []) + [profile.get("name", "")]
                          for word in tokens(phrase) if len(word) > 2}
        common = set.intersection(*words.values()) if words else set()
        scores = {}
        for sid in owners:
            qualifiers = [word for word in words[sid] - common]
            for rule in rules:
                if sid in rule.get("candidates", []):
                    qualifiers += rule.get("qualifiers", {}).get(sid, [])
            scores[sid] = sum(bool(spans(clause, term)) for term in set(qualifiers))
        best = max(scores.values(), default=0)
        selected = [sid for sid in owners if best and scores[sid] == best]
        if len(selected) == 1:
            chosen = [(x, y, sid) for x, y, sid in chosen
                      if (x, y) != bounds or sid == selected[0]]
    ambiguities = []
    for bounds in {(a, b) for a, b, _ in chosen}:
        ids = {s for a, b, s in chosen if (a, b) == bounds}
        if len(ids) > 1:
            ambiguities.append({"code": "raw_entity_ambiguous",
                                "span": _mark(raw, *bounds, "service"),
                                "alternatives": sorted(ids)})
    return chosen, ambiguities


def _unsupported_named_subjects(raw, entities):
    """Catalog language qualifiers identify foreign names, never fact scopes."""
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
    aliases = catalog.get("qualifiers", {}).get("unsupported_named_service", [])
    points = _hits(raw, [alias for alias in aliases if isinstance(alias, str)])
    return [_mark(raw, a, b, "unsupported_named_provider") for a, b in points
            if not any(start <= a and b <= end for start, end, _ in entities)]


def _channels(raw, table):
    matches = []
    for row in table:
        if row["channel_id"] == "other_unspecified":
            continue
        phrases = sum(row["aliases"].values(), [])
        matches.extend((a, b, row["channel_id"]) for a, b in _hits(raw, phrases))
    chosen = []
    for a, b, cid in sorted(set(matches), key=lambda x: (-(x[1] - x[0]), x[0], x[2])):
        if not any(a >= x and b <= y for x, y, _ in chosen):
            chosen.append((a, b, cid))
    return chosen


def _prior(prior_context, definition):
    if not isinstance(prior_context, dict) or prior_context.get("same_session") is False or prior_context.get("expired") is True:
        return {}, []
    prior = prior_context
    known = set(definition.get("service_profiles", {}))
    services = [s for s in prior.get("services", []) if s in known]
    return prior, list(dict.fromkeys(services))


def _raw_code_compound_context(masked, hits):
    """A directly adjacent workflow noun can modify a code head."""
    contexts = []
    targets = list(hits.get("code", []))
    pending = list(hits.get("workflow", []))
    while pending:
        found = [point for point in pending
                 if any(point[1] <= start and not masked[point[1]:start].strip()
                        for start, _ in targets)]
        if not found:
            break
        contexts.extend(found)
        targets.extend(found)
        pending = [point for point in pending if point not in found]
    return contexts


def _raw_record_references(text):
    """Literal letter-prefixed IDs need digits and an explicit record object."""
    objects = {"complaint": ["complaint", "ticket", "شكوى", "shakwa"],
               "transaction": ["transaction", "payment", "عملية", "معاملة", "سداد", "daf3a"],
               "refund": ["refund", "استرداد", "esterdad"]}
    anchors = [(key, a, b) for key, aliases in objects.items() for a, b in _hits(text, aliases)]
    result = []
    for match in re.finditer(r'(?<![\w-])[A-Za-z]{1,12}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-])', text):
        if not anchors or not any(char.isdigit() for char in match.group()):
            continue
        nearest = min(anchors, key=lambda row: min(abs(row[2]-match.start()), abs(row[1]-match.end())))
        result.append({"kind": "record_identifier", "object_family": nearest[0], "verified": False,
                       "span": _mark(text, match.start(), match.end(), "record_reference")})
    return result


def _raw_intents(text, feature_hits):
    has = lambda k: bool(feature_hits.get(k))
    def evidence(*keys):
        return sorted({p for key in keys for p in feature_hits.get(key, [])})
    intents = {}
    def add(name, *keys):
        proof = evidence(*keys)
        if proof:
            intents[name] = proof
    image = has("image")
    if image:
        add("image_permission", "image", "permission")
    code = has("code")
    if code:
        add("transaction_code", "code")
    fee = has("fee")
    initial = has("initial") or has("activation")
    minimum_funding = bool(_hits(text, [
        "minimum", "least", "اقل", "ادني", "مبدئي", "اولي", "مبلغ", "a2al", "awel",
    ])) and initial
    explicit_charge = bool(_hits(text, [
        "fee", "charge", "subscription cost", "رسوم", "مصاريف", "rozoom", "rosoom",
    ]))
    activation_price = bool(_hits(text, ["بكام", "cost", "price"])) and has("activation")
    if initial:
        add("initial_funding", "initial", "activation")
    subscription = bool(_hits(text, ["subscription", "اشتراك", "eshterak"]))
    subscription_context = subscription and any(has(k) for k in ["image", "identity", "documents", "phone_owner", "existing_wallet"])
    if has("opening") and ((subscription and not subscription_context) or fee or bool(re.search(r"\bfree\b|مجاني|ببلاش", text, re.I))) and not has("workflow"):
        add("opening_fee", "opening", "fee")
    # A fee-versus-activation-funding question needs the cost distinction,
    # not merely the credited-deposit amount. The source view stays unchanged.
    activation_charge = bool(re.search(
        r"\b(?:activation|activate|activating)\s+(?:fee|charge|cost|price)\b"
        r"|\b(?:fee|charge|cost|price)\s+(?:for|of|to)?\s*(?:activation|activate|activating)\b",
        text, re.I))
    if initial and (activation_charge or (activation_price and not minimum_funding)):
        add("opening_fee", "fee", "activation", "initial")
    if has("balance_disposition") and (has("balance") or has("initial") or has("deposit")):
        add("balance_treatment", "balance_disposition", "balance")
    if has("deposit") and not initial and not has("balance_disposition") and not code and not has("workflow") and not image:
        add("deposit_tariff", "deposit", "fee")
    minimum_transaction = bool(_hits(text, [
        "minimum withdrawal amount", "minimum cash-out amount", "least withdrawal amount",
        "اقل مبلغ سحب", "الحد الادني لمبلغ السحب", "minimum transaction amount",
    ]))
    principal_proofs=[] if code or has('workflow') or image else principal_minimum_proofs(text,feature_hits.get('withdrawal',[]))
    if has("withdrawal") and not code and not has("workflow") and not image:
        if minimum_transaction and not explicit_charge:
            # A fee floor is not evidence for a minimum transaction principal.
            add("withdrawal_minimum", "withdrawal")
        else:
            add("withdrawal_tariff", "withdrawal", "fee")
    if principal_proofs:
        if not any(not any(proof['span'][0]<=point[0] and point[1]<=proof['span'][1] for proof in principal_proofs)
                   for point in feature_hits.get('withdrawal',[])):
            intents.pop('withdrawal_tariff',None)
        intents['withdrawal_minimum']=sorted({point for proof in principal_proofs for point in [proof['bound'],proof['amount'],proof['operation']]})
    identity_is_request = not image or has("requirements") or bool(
        re.search(r"\b(?:validity|originality|requirements?|check|expired|unexpired|valid|invalid|copy)\b"
                  r"|صلاحية|متطلبات|شروط|منتهية|منتهي|سارية|ساري|أصل|اصل|صورة", text, re.I))
    if has("identity") and identity_is_request:
        add("identity", "identity")
    ownership = bool(re.search(
        r"\b(?:ownership|owner|owns|owned|registered|whose|name|b\s+esm|sa7eb)\b|باسم|ملكية|ملكيه|مسجل|صاحب|esm", text, re.I))
    if has("phone_owner") and (ownership or has("requirements")):
        add("phone_ownership", "phone_owner")
    if re.search(r"\bwallet\s+tanya\b", text, re.I):
        feature_hits["existing_wallet"] = sorted(set(feature_hits.get("existing_wallet", [])
                                                      + _hits(text, ["wallet tanya"])))
    if has("existing_wallet"):
        add("existing_wallet", "existing_wallet")
    if has("documents") and not image:
        add("documents", "documents")
    if (has("requirements") and has("opening") and not explicit_charge
            and not any(has(key) for key in ("identity", "phone_owner", "existing_wallet"))):
        add("eligibility", "requirements", "opening")
    if has("workflow") and not image:
        add("workflow", "workflow")
    if (has("branch") or (has("visit") and has("branch_condition"))) and (has("branch_condition") or has("visit")) and not has("withdrawal") and not has("deposit"):
        add("branch_condition", "branch", "branch_condition", "visit")
    purpose=bool(re.search(
        r"\b(?:for|during|to)\s+(?:the\s+)?(?:activation|activate|activating)\b"
        r"|(?<!\w)(?:ل(?:تفعيل|لتفعيل)|عند\s+(?:تفعيل|التفعيل))",shadow(text)[0],re.I))
    monetary=explicit_charge or bool(_hits(text,[
        "deposit","funding","amount","money","balance","cash","EGP","إيداع","ايداع","تمويل","مبلغ","فلوس","رصيد","جنيه"]))
    if purpose and set(intents)&{"identity","phone_ownership","existing_wallet","documents","image_permission"} and not monetary:
        intents.pop("initial_funding",None)
        feature_hits["activation_purpose_context"]=feature_hits.get("activation",[])
    if "branch_condition" in intents and "workflow" in intents:
        reference_heads=_hits(text,["according to","as per","حسب","وفق","وفقا ل","ضمن"])
        workflow_points=feature_hits.get("workflow",[])
        contextual=[point for point in workflow_points if any(
            right <= point[0] and not tokens(text[right:point[0]]) for left,right in reference_heads)]
        if workflow_points and len(contextual)==len(workflow_points):
            intents.pop("workflow",None)
            feature_hits["workflow_purpose_context"]=contextual
    return intents


def _raw_ongoing_balance_policy(masked):
    """A bounded continuing balance obligation is a policy, not activation."""
    if _hits(masked, ["stock", "inventory", "warehouse", "item", "product", "مخزون", "المخزن", "بضاعة"]):
        return []
    objects = _hits(masked, ["balance", "رصيد", "raseed"])
    bounds = _hits(masked, ["minimum", "maximum", "least", "lowest", "highest", "ceiling", "min", "max",
                            "الحد الأدنى", "حد ادنى", "الحد الأقصى", "حد اقصى", "أقل", "أكبر"])
    continuing = _hits(masked, ["ongoing", "maintain", "maintenance", "always", "permanent", "continuing",
                                "after activation", "مستمر", "دائم", "دايما", "بعد التفعيل"])
    return sorted(set(objects + bounds + continuing)) if objects and bounds and continuing else []


def _raw_activation_principal(masked, hits):
    """An amount governed by funding/putting money is principal, not a fee."""
    if not (hits.get("initial") or hits.get("activation")):
        return False
    charge_heads = _hits(masked, ["fee", "charge", "cost", "price", "subscription", "رسوم", "عمولة", "مصاريف", "تكلفة", "اشتراك",
                                  "بيتاخد", "بتتاخد", "بيتخصم", "بيخصم", "بيكلف", "بتكلف"])
    if charge_heads:
        return False
    dimensions = _hits(masked, ["how much", "what amount", "minimum", "least", "كام", "كم", "قد ايه", "مبلغ"])
    additions, _ = _raw_money_addition(masked)
    funding = _hits(masked, ["put", "deposit", "fund", "funding amount", "principal", "يحط", "حط", "أحط", "احط", "هحط", "بحط", "تحط", "نحط",
                             "يودع", "أودع", "اودع", "هودع", "مبلغ التفعيل"])
    return bool(dimensions and (funding or additions))


def _raw_money_addition(masked):
    """Enumerate raw addition/action-object pairs independently of planning.

    This deliberately does not import semantic_frames or consume planner
    goals. A financial object must be governed by the verb in this clause.
    """
    normalized, coordinates = shadow(masked)
    arabic_verbs = {"زود" + ending for ending in ["", "ت", "تي", "نا", "تم", "تو", "وا", "ي", "ون"]}
    persons = ["ا", "ت", "ي", "ن"]
    for prefix in persons + ["ب", "ه", "ح"] + [tense + person for tense in ["ب", "ه", "ح"] for person in persons]:
        arabic_verbs.update(prefix + "زود" + ending for ending in ["", "ي", "وا", "ون"])
    arabic_verbs.update(verb + suffix for verb in list(arabic_verbs)
                        for suffix in ["ها", "ه", "هم", "هن", "ك", "كم", "نا"])
    verbs = []
    objects = []
    for word in re.finditer(r"[a-z]+(?:-[a-z]+)*|[\u0621-\u064a]+", normalized):
        value = word.group()
        bounds = (coordinates[word.start()], coordinates[word.end() - 1] + 1)
        arabic_base = value[1:] if value[:1] in {"و", "ف"} else value
        if arabic_base in arabic_verbs | {"تزويد", "تزود", "تعبئه", "تعبية"} or value in {
                "add", "adds", "adding", "added", "increase", "increases", "increasing", "increased",
                "top-up", "top-ups", "topped-up", "topping-up"}:
            verbs.append(bounds)
        if value in {"money", "cash", "fund", "funds", "balance"} or re.fullmatch(
                r'(?:ب)?(?:ال)?(?:فلوس|اموال|نقود|مال|رصيد|محفظه|محفظة|حساب)(?:ي|ك|ه|ها|نا|كم|هم|هن)?', value):
            objects.append(bounds)
    verbs.extend(_hits(masked, ["top up", "tops up", "topped up", "topping up"]))
    links = []
    permitted = {"the", "some", "more", "extra", "additional", "my", "your", "his", "her", "our", "their",
                 "customer's", "a", "bit", "of", "wallet", "account", "شويه", "كمان", "اكتر", "زياده", "بعض",
                 "المزيد", "من", "محفظه", "محفظة", "حساب"}
    for left, right in objects:
        preceding = [(a, b) for a, b in verbs if b <= left and left - b <= 50]
        for start, end in preceding:
            connector = masked[end:left]
            if not re.search(r'[.;!?؟؛,،\n]', connector) and all(term in permitted for term in tokens(connector)):
                links.extend([(start, end), (left, right)])
    return sorted(set(verbs)), sorted(set(links))


def _raw_nominal_price_questions(masked):
    """Raw interrogative-plus-price-head grammar, independent of operations."""
    questions = _hits(masked, ["what", "which", "how much", "ايه", "كام", "بكام", "قد ايه"])
    prices = _hits(masked, ["charge", "cost", "fee", "tariff", "رسوم", "عمولة", "تكلفة", "مصاريف"])
    allowed = {"is", "are", "the", "a", "my", "your", "its", "this", "that", "it", "هو", "هي"}
    rows = []
    for left, right in questions:
        for start, end in prices:
            if right <= start and not re.search(r'[.;!?؟؛]', masked[right:start]):
                if all(word in allowed for word in tokens(masked[right:start])):
                    rows.append({"head": (start, end), "question": [(left, right)]})
    return rows


def _raw_charge_dimension(masked, operation):
    """Find raw finite charge/price heads after an explicit operation."""
    result = []
    for start, end in _hits(masked, [
            "بيتاخد", "بتتاخد", "بيتخصم", "بيخصم", "بيكلف", "بتكلف", "charge", "charged", "cost"]):
        anchors = [right for _, right in operation if right <= start]
        if not anchors or re.search(r'[.;!?؟؛]', masked[max(anchors):start]):
            continue
        remainder = re.split(r'[.;!?؟؛]', masked[end:], maxsplit=1)[0]
        questions = _hits(remainder, ["كام", "بكام", "قد ايه", "how much", "what percentage", "which rate", "ايه النسبة"])
        if questions:
            result.append({"head": (start, end),
                           "question": [(end + a, end + b) for a, b in questions]})
    for row in _raw_nominal_price_questions(masked):
        query_start = min(start for start, _ in row["question"])
        anchors = [end for _, end in operation if end <= query_start]
        if anchors and not re.search(r'[.;!?؟؛]', masked[max(anchors):query_start]):
            result.append(row)
    return result


def _raw_objectless_addition(masked, verbs, features):
    """Keep a new action/fee dimension pending its independently typed object."""
    if any(_hits(masked, features.get(key, [])) for key in ["initial", "activation", "workflow", "image", "code"]):
        return []
    other_objects = _hits(masked, ["stock", "inventory", "item", "product", "fee", "charge", "amount",
                                  "مخزون", "رسوم", "مبلغ", "بضاعة", "كمية"])
    pending = []
    for verb in verbs:
        dimensions = _raw_charge_dimension(masked, [verb])
        if not dimensions:
            continue
        first_charge = min(row["head"][0] for row in dimensions)
        if any(start < first_charge for start, _ in other_objects):
            continue
        pending.append({"action": verb,
                        "fee_question": sorted({point for row in dimensions for point in [row["head"]] + row["question"]})})
    return pending


def _retained_balance_demand(masked):
    """Independent raw relation enumeration; never calls the planner helper."""
    verbs = _hits(masked, ["keep", "kept", "retain", "retained", "remain", "stay", "يبقى", "تبقى", "يفضل", "بتفضل", "يستقر", "تستقر", "يحتفظ", "تحتفظ", "محفوظ", "محتفظ", "byefdal", "yefdal"])
    balances = _hits(masked, ["balance", "رصيد", "raseed"])
    funded_subject = _hits(masked, ["funding", "deposit", "activation", "إيداع", "ايداع", "تفعيل", "تمويل", "eda3", "taf3eel"])
    other_objects = _hits(masked, ["payment", "transaction", "refund", "stock", "inventory", "item", "product", "مخزون", "المخزن", "الصنف", "المنتج", "عملية", "معاملة", "استرداد"])
    if other_objects and not funded_subject:
        return []
    # A typed amount referent can ask the same disposition without repeating
    # the word "balance": "whether either sum remains available afterward".
    # Require both the funded-amount noun and a post-operation availability
    # predicate so a generic availability question cannot become policy.
    disposition = []
    for match in re.finditer(
            r"\b(?:sum|amount|deposit|funding|money)\b[^.;!?]{0,45}\b(?:remain|stay)s?\b[^.;!?]{0,35}\b(?:available|credited|there|afterward|afterwards)\b",
            masked, re.I):
        disposition.append((match.start(), match.end()))
    if disposition:
        return disposition
    filler = {"the", "a", "my", "your", "our", "their", "his", "her", "customer", "customer's", "customers",
              "wallet", "account", "it", "that", "amount", "money", "funding", "in", "into", "within", "في", "داخل", "ضمن", "العميل", "المبلغ", "الفلوس", "به", "بها", "الحساب", "حساب", "محفظه", "المحفظه"}
    found = []
    for start, end in verbs:
        for a, b in balances:
            if not end <= a <= end + 75 or re.search(r'[.;!?؟؛,،]', masked[end:a]):
                continue
            middle = tokens(masked[end:a])
            destination = bool(set(middle) & {"in", "into", "within", "في", "داخل", "ضمن"})
            destination |= tokens(masked[a:b]) in [["بالرصيد"], ["برصيد"]]
            if destination and all(word in filler for word in middle):
                found.extend([(start, end), (a, b)])
    return sorted(set(found))


def _raw_negative_operation_marks(text):
    """Enumerate known verbs inside discontinuous Arabic/Franco negation."""
    normalized, coordinates = shadow(text)
    roots = {"create": ["عمل", "قدم", "سجل", "فتح"], "cancel": ["وقف", "لغي"],
             "transfer": ["حول"], "closure": ["قفل", "غلق"], "return": ["رجع"], "reprint": ["طبع"]}
    finite = {key: {prefix + root + suffix for root in values
                    for prefix in ["", "ا", "ت", "ي", "ن", "ب", "با", "بت", "بي", "بن", "ه", "ها", "هت", "هي", "هن"]
                    for suffix in ["", "ي", "وا", "ت", "نا"]} for key, values in roots.items()}
    franco = {"transfer": {"7awel", "t7awel"}, "cancel": {"elghy", "telghy", "wa2af", "twa2af"},
              "create": {"a3mel", "e3mel", "t3mel", "ye3mel", "efta7", "tefta7", "sagel", "tsagel", "a2adem", "t2adem"}}
    result = []
    for word in re.finditer(r'[\u0621-\u064a]+|[a-z0-9]+', normalized):
        value = word.group()
        stems = []
        if re.fullmatch(r'ma[a-z0-9]{3,}sh', value):
            stems.append(value[2:-2])
        elif value.endswith("ش"):
            stem = value[:-1]
            previous = tokens(normalized[:word.start()])
            if previous and previous[-1] == "ما":
                stems.append(stem)
            if stem.startswith("ما"):
                stems.append(stem[2:])
            elif stem.startswith("م"):
                stems.append(stem[1:])
        for key in roots:
            if any(stem in finite[key] or stem in franco.get(key, set()) for stem in stems):
                result.append((key, (coordinates[word.start()], coordinates[word.end()-1]+1)))
    return result


def _noncore_meanings(text, object_context=(), masked=None, interrogative=False):
    """Independently enumerate clear non-policy asks from lexical components.

    These meanings have no newly authorized evidence.  Their recognition lets
    the audit distinguish a missing live record/source from an unknown intent;
    it cannot make them complete or authorize execution.  This code does not
    call the runtime planner or its semantic-frame module.
    """
    vocab = {
        "complaint": ["complaint", "ticket", "شكوى", "شكوتي", "shakwa", "shakwety"],
        "refund": ["refund", "استرداد", "الاسترداد", "esterdad"],
        "transaction": ["transaction", "payment", "عملية", "معاملة", "سداد", "الدفع", "3amaleya", "daf3a"],
        "item": ["item", "product", "goods", "الصنف", "منتج", "سلعة", "بضاعة", "senf", "montag"],
        "stock": ["stock", "inventory", "warehouse", "المخزن", "مخزون", "المستودع"],
        "receipt": ["receipt", "slip", "coupon", "إيصال", "كوبون", "wesl"],
        "cash_drawer": ["cash drawer", "till", "درج الصراف", "خزينة", "نقدية"],
        "state": ["status", "state", "progress", "update", "pending", "arrived", "reached", "already", "where", "حالة", "وصل", "وصلت", "فين", "لفين", "معلقة", "نجحت", "wesel", "weslet"],
        "resolution": ["resolved", "fixed", "resolution", "اتحلت", "حلت", "et7alet"],
        "closure_state": ["closed", "marked closed", "اتقفلت", "أغلقت", "اغلقت"],
        "issue": ["issue", "problem", "مشكلة", "moshkela"],
        "eligibility": ["eligibility", "eligible", "qualify", "qualifying", "conditions", "policy", "allowed", "rules", "شروط", "استحقاق", "أهلية", "سياسة", "قواعد", "ينفع", "shoroot"],
        "cancel": ["cancel", "cancelled", "canceled", "void", "stop", "ألغي", "الغي", "إلغاء", "وقف", "elghy", "wa2af"],
        "action": ["perform", "execute", "now", "immediately", "حالاً", "دلوقتي", "اعمل", "نفذ", "5ally"],
        "return": ["return", "returning", "مرتجع", "إرجاع", "ارجع", "أرجع", "araga3", "mortaga3"],
        "reprint": ["reprint", "reprinting", "duplicate", "اطبع", "أطبع", "طباعة", "atba3"],
        "draft": ["draft", "phrase", "what should I tell", "help me reply", "صياغة", "صغ", "صيغلي", "أرد عليه", "أقول للعميل", "a2ool", "seghly", "ard 3aleh"],
        "callback": ["callback", "call me", "contact me", "كلموني", "يكلمني", "معاودة الاتصال", "yekalemny", "kallemony", "yerenn 3alaya"],
        "create": ["create", "raise", "lodge", "log", "open", "أقدم", "اقدم", "تقديم", "سجل", "فتح", "a2adem", "efta7"],
        "count": ["count", "stocktake", "quantity", "units", "عدد", "جرد", "كمية", "نعد", "gard"],
        "available": ["available", "availability", "in stock", "موجود", "توافر", "متاح", "mawgood"],
        "repeat": ["second", "again", "repeat", "duplicate", "تاني", "ثاني", "مرة أخرى", "tany"],
        "transfer": ["transfer", "حول", "تحويل", "تحول", "7awel", "t7awel"],
        "closure": ["close", "closing", "closure", "إغلاق", "اغلاق", "إقفال", "اقفال", "اقفل", "قفل"],
        "wallet_object": ["wallet", "account", "محفظة", "حساب", "ma7faza", "ma7fazet"],
        "balance_object": ["balance", "رصيد", "raseed"],
    }
    raw = list(text)
    for quoted in re.finditer(r'"[^"\n]+"|“[^”\n]+”|«[^»\n]+»', text):
        raw[quoted.start():quoted.end()] = " " * (quoted.end() - quoted.start())
    raw = "".join(raw)
    h = {key: _hits(raw, terms) for key, terms in vocab.items()}
    if masked is not None:
        for key in ["closure", "wallet_object", "balance_object"]:
            h[key] = _hits(masked, vocab[key])
    normalized, coordinates = shadow(raw)
    for word in re.finditer(r'[\u0621-\u064a]+', normalized):
        if re.fullmatch(r'(?:ال)?حالت(?:ها|ه|هم|هن|ك|كم|نا|ي)', word.group()):
            h["state"].append((coordinates[word.start()], coordinates[word.end()-1]+1))
    negative_operations = set()
    for key, point in _raw_negative_operation_marks(raw):
        h[key].append(point)
        negative_operations.add(key)
    if h["reprint"]:
        h["receipt"] = sorted(set(h["receipt"] + _hits(raw, ["وصل"])))
    explicit_objects = {key for key in ["complaint", "refund", "transaction", "item", "stock", "receipt", "cash_drawer"] if h[key]}
    active_objects = explicit_objects or set(object_context)
    goals = {}
    def present(key):
        return bool(h.get(key))
    def object_present(key):
        return key in active_objects
    def add(intent, *keys):
        proof = sorted({point for key in keys for point in h.get(key, [])})
        if proof:
            goals[intent] = proof
    def dimension_for(obj, dimension):
        if not h[dimension] or not object_present(obj):
            return False
        objects = [(key, (a+b)/2) for key in explicit_objects for a,b in h[key]]
        if not objects:
            return len(active_objects) == 1
        for a,b in h[dimension]:
            distances = [(abs((a+b)/2-center), key) for key,center in objects]
            best = min(d for d,_ in distances)
            if {key for d,key in distances if d == best} == {obj}:
                return True
        return False
    metalinguistic_reference = bool(re.search(
        r"\b(?:which|what)\b[^?]{0,80}\b(?:requirement|rule|intent|meaning)\b[^?]{0,80}\b(?:phrase|instruction|words?)\b"
        r"|\bwhat\s+does\b[^?]{0,80}\b(?:phrase|instruction)\b[^?]{0,40}\bmean\b",
        raw, re.I))
    drafting = present("draft") and not metalinguistic_reference
    words = tokens(raw)
    finite_question = bool(words and words[0] in {"is", "are", "was", "were", "has", "have", "had", "does", "do", "did", "هل"})
    finite_question |= bool(_hits(raw, ["whether"]))
    if drafting:
        add("response_draft", "draft")
    elif object_present("complaint"):
        if present("resolution") and (present("issue") or present("state") or finite_question or interrogative or "?" in text or "؟" in text):
            add("complaint_resolution_confirmation", "complaint", "resolution", "issue", "closure_state")
        elif dimension_for("complaint", "state"):
            add("complaint_status", "complaint", "state")
        elif present("closure_state") and (finite_question or interrogative):
            add("complaint_status", "complaint", "closure_state")
        elif present("create"):
            add("complaint_create", "complaint", "create")
    if object_present("refund") and not drafting:
        if dimension_for("refund", "state"):
            add("refund_status", "refund", "state")
        elif dimension_for("refund", "eligibility"):
            add("refund_eligibility", "refund", "eligibility")
        elif present("action"):
            add("refund", "refund", "action")
    if object_present("transaction") and not drafting:
        if dimension_for("transaction", "state"):
            add("transaction_status", "transaction", "state")
        elif present("cancel"):
            add("transaction_cancel", "transaction", "cancel")
        elif present("repeat"):
            add("repeat_payment", "transaction", "repeat")
    physical = object_present("item") or object_present("stock")
    if physical and present("count"):
        add("inventory_count", "item", "stock", "count")
    elif physical and present("available"):
        add("stock_availability", "item", "stock", "available")
    if object_present("item") and present("return"):
        add("product_return", "item", "return")
    if object_present("receipt") and present("reprint"):
        add("reprint", "receipt", "reprint")
    if present("callback") and not drafting:
        add("callback", "callback")
    if present("transfer") and (present("action") or "transfer" in negative_operations) and not drafting:
        add("transfer", "transfer", "action")
    if present("closure") and present("wallet_object"):
        add("closure", "closure", "wallet_object")
    scope_exclusion = _hits(raw, ["not asking", "not about", "leave out", "exclude", "مش عايز", "مش عاوز",
                                  "mesh basa2al", "msh basa2al", "mesh 3ayez", "لا أسأل", "لا اريد", "لا أريد"])
    if present("balance_object") and present("wallet_object") and scope_exclusion and not _raw_ongoing_balance_policy(raw):
        add("balance_treatment", "balance_object", "wallet_object")
    if object_present("cash_drawer") and _hits(raw, ["reconcile", "count", "value", "amount", "قيمة", "مطابقة", "أطابق"]):
        add("cash_reconciliation", "cash_drawer", "count")
    contextual = bool(_hits(raw, ["was requested", "is closed", "بقى closed", "according to the customer", "customer said", "customer says"])) and not goals
    if explicit_objects and not goals and _hits(raw, ["for", "about", "a", "the", "في", "بالنسبة", "اثناء", "أثناء"]):
        contextual = True
    return goals, explicit_objects or set(object_context), contextual


def _fact_rows(facts):
    return facts if isinstance(facts, dict) else {f["fact_id"]: f for f in facts}


def _condition_period(text):
    # Literal declared qualifiers only; missing source metadata cannot become
    # a universal rule. We do not infer converse/exception policy.
    periods = []
    for label, pattern in [
        ("monthly", r"\bmonthly\b|\beach month\b|شهري|كل شهر"),
        ("daily", r"\bdaily\b|\beach day\b|يومي|كل يوم"),
        ("yearly", r"\byearly\b|\bannually\b|سنوي|كل سنة"),
    ]:
        if re.search(pattern, text, re.I):
            periods.append(label)
    return periods[0] if len(periods) == 1 else None, len(periods) > 1


def _service_list_fragment(masked, features):
    """Only defer a product-name list, never an unknown product predicate."""
    chars = list(masked)
    for a, b in _hits(masked, features.get("comparison", []) + features.get("followup", [])):
        chars[a:b] = " " * (b-a)
    for a, b in _hits("".join(chars), ["for", "regarding", "about", "في", "بخصوص", "بالنسبة"]):
        chars[a:b] = " " * (b-a)
    functional = {"the", "for", "of", "with", "about", "wallet", "service", "please", "and", "or",
                  "separately", "individually", "respectively", "each", "both",
                  "aktob", "ekteb", "shart", "gamb", "next", "beside",
                  "محفظه", "خدمه", "في", "عن", "بخصوص", "بالنسبه", "ماذا", "اكتب", "شرط", "جنب"}
    return not any(not (forms(word) & functional) for word in tokens("".join(chars)))


def _raw_routine_object_spans(masked, operations):
    """Objects governed by a financial operation, without erasing modifiers."""
    nouns = _hits(masked, ["money", "cash", "funds", "wallet", "account", "فلوس", "أموال", "نقود", "محفظة", "حساب"])
    grammatical = {"the", "a", "an", "my", "your", "his", "her", "our", "their", "some", "more", "new",
                   "into", "in", "to", "of", "في", "داخل", "من", "بعض"}
    governed = []
    for start, end in nouns:
        for _, right in operations:
            if right <= start <= right + 50 and not re.search(r'[.;!?؟؛,،]', masked[right:start]):
                if set(tokens(masked[right:start])) <= grammatical:
                    governed.append((start, end))
                    break
    return sorted(set(governed))


def _conditions(text, masked=None, features=None, bound_addition=()):
    # An explicit hypothetical/customer constraint is not silently universal.
    # Keep it literal; the evidence contract must establish the exact scope.
    marker = re.search(r"\b(?:if|unless|provided|only when|when|law)\b|(?<!\w)و?(?:لو|اذا|إذا|بشرط)(?!\w)", text, re.I)
    if not marker:
        return []
    # In eligibility wording, clause-initial "law/لو" can mean "whether":
    # whether a number already has another wallet. It is the requested
    # predicate itself, not an extra customer condition.
    if features is not None and re.match(r"^\s*(?:(?:w\s+)?law\b|و?لو\b)", shadow(text)[0], re.I):
        if _hits(masked if masked is not None else text,
                 features.get("existing_wallet", []) + ["wallet tanya", "محفظة أخرى", "محفظه تانيه"]):
            return []
    if re.search(r"(?:^|\s)(?:ما|وما)\s*$", text[:marker.start()]):
        # Arabic embedded interrogative: "whether ...", not a customer-case
        # eligibility restriction. Any actual later if/unless clause still
        # has its own literal constraint and remains subject to evidence.
        later = _conditions(text[marker.end():], None, None)
        return later
    # A positive operation scenario describes this very service/transaction,
    # rather than imposing an extra eligibility rule. Unknown words, numerical
    # constraints and negation remain literal restrictions requiring evidence.
    if masked is not None and features is not None:
        tail = list(masked[marker.start():])
        _, addition = _raw_money_addition("".join(tail))
        bound_points = [(a-marker.start(), b-marker.start()) for a, b in bound_addition if a >= marker.start()]
        operation_spans = addition + bound_points + [point for key in ["deposit", "withdrawal", "opening", "activation", "initial"]
                                      for point in _hits("".join(tail), features.get(key, []))]
        # A finite charge question after the operation is the consequence of
        # the scenario. Trim only that bounded question; restrictions before
        # it still have to pass the literal antecedent check below.
        for consequence in _raw_charge_dimension("".join(tail), operation_spans):
            start = min([consequence["head"][0]] + [a for a, _ in consequence["question"]])
            words = tokens("".join(tail)[start:])
            fee_question = {"بيتاخد", "بتتاخد", "بيتخصم", "بيخصم", "بيكلف", "بتكلف",
                            "كام", "بكام", "قد", "ايه", "الرسوم", "رسوم", "العموله", "عموله",
                            "المصاريف", "مصاريف", "التكلفه", "تكلفه",
                            "charge", "charges", "charged", "cost", "costs", "fee", "fees", "tariff", "tariffs", "how", "much", "what",
                            "percentage", "which", "rate", "is", "the", "it"}
            if set(words) <= fee_question:
                tail[start:] = " " * (len(tail) - start)
                break
        for a, b in _raw_routine_object_spans("".join(tail), operation_spans):
            tail[a:b] = " " * (b-a)
        for a, b in addition:
            tail[a:b] = " " * (b-a)
        for a, b in bound_points:
            tail[a:b] = " " * (b-a)
        for key in ["deposit", "withdrawal", "opening", "activation", "initial", "fee"]:
            for a, b in _hits("".join(tail), features.get(key, [])):
                tail[a:b] = " " * (b-a)
        residual = tokens("".join(tail))
        functional = {"if", "when", "provided", "i", "we", "a", "the", "customer",
                      "client", "will", "would", "want", "to", "do", "at", "from",
                      "via", "through", "into", "in", "of", "for", "my", "with",
                      "لو", "ولو", "اذا", "واذا", "عميل", "العميل", "في", "من", "عن", "طريق",
                      "خلال", "انا", "هي", "هو", "عايز", "هحط", "law", "fe",
                      "men", "el", "3ameel", "3ayez", "wallet", "محفظه", "المحفظه",
                      "machine", "counter", "branch", "route", "instead", "rather", "than", "or", "either",
                      "ماكينه", "فرع", "شباك", "بدل", "و", "ولو"}
        if bound_points:
            functional.update({"بعدها", "بعدين", "بعد", "كده", "later", "afterwards", "then", "after", "that", "more"})
        operation = bool(addition or bound_points) or any(_hits(masked, features.get(k, [])) for k in
                                         ["deposit", "withdrawal", "opening", "activation", "initial"])
        if operation and all(word in functional for word in residual):
            return []
    return [text[marker.start():].strip(" .?!؟")]


def _excluded_scope(text, hits, features):
    if response_scope_omission(text):return True
    # "No other wallet" is the polarity of a requested requirement, not an
    # instruction to hide the existing-wallet topic. Likewise a prohibited
    # image is still a permission question.
    if nominal_scope_omission(text, hits.get("fee", [])):
        return True
    explicit = _hits(text, ["not asking", "do not explain", "don't explain", "do not assess", "don't assess",
                           "do not discuss", "don't discuss", "do not mention", "don't mention", "omit",
                           "do not put", "don't put", "do not treat", "don't treat", "ماتحطليش", "ما تحطليش",
                           "do not perform", "do not transfer", "do not cancel",
                           "leave out", "excluding", "exclude", "استبعد",
                           "لا اريد", "لا احتاج", "دون شرح", "دون إعادة", "دون اعادة",
                           "من غير إعادة", "من غير اعادة", "without repeating", "do not repeat",
                           "مش عايز",
                           "mesh matlooba", "msh matlooba", "not needed", "not required",
                           "مش مطلوبة", "مش مطلوب", "غير مطلوبة", "غير مطلوب",
                           "سيبها دلوقتي", "مالناش دعوة", "ملناش دعوة", "malnaash da3wa", "malnash da3wa",
                           "بدون كلام عن", "من غير كلام عن", "without discussing", "rather than",
                           "ولا تذكر", "ما تدخلش", "ما تدخلش", "دون أي"])
    normalized = shadow(text)[0]
    negative_form = re.search(r'(?<!\w)ma[a-z0-9]{3,}sh(?!\w)|(?<!\w)ما\s+[\u0621-\u064a]{3,}ش(?!\w)|(?<!\w)(?:ما|م)[\u0621-\u064a]{3,}ش(?!\w)', normalized)
    if _hits(text, features.get("additive_negation", [])) and not (explicit or negative_form):
        return False
    if not explicit and not negative_form and (hits.get("existing_wallet") or hits.get("image")):
        return False
    if explicit or _hits(text, features.get("exclusion_tail", [])) or re.search(r"\bleave\b.*\bout\b", text, re.I):
        return True
    if re.search(r"^\s*no\b.*\b(?:is|are)\s+(?:needed|required)\b", text, re.I):
        return True
    if re.search(r"^\s*no\s+(?:full\s+)?(?:walkthrough|procedure|steps?)\b", text, re.I):
        return True
    if _raw_negative_operation_marks(text) or negative_form:
        return True
    return bool(_hits(text, features.get("exclude", []) + ["ليس", "don't", "never"]) or re.search(
        r"\b(?:not|mesh|msh|mish)\b|(?<!\w)مش(?!\w)|استبعد|excluding|exclude|^\s*لا(?:\s|$)",
        text, re.I))


def _intent_excluded(text, proof, clause_excluded):
    """Bind an exclusion tail to predicates at/after its operator only."""
    if not clause_excluded:
        return False
    cues = _hits(text, [
        "not asking", "not about", "do not explain", "don't explain", "not needed",
        "not required", "without repeating", "do not repeat", "rather than", "مش عايز",
        "do not put", "don't put", "do not treat", "don't treat", "ماتحطليش", "ما تحطليش",
        "mesh matlooba", "msh matlooba", "مش مطلوبة", "مش مطلوب", "غير مطلوبة", "غير مطلوب",
        "دون شرح", "دون إعادة", "دون اعادة", "من غير إعادة", "من غير اعادة",
    ])
    if not cues:
        return True
    boundary = min(start for start, _ in cues)
    meaningful = [(start, end) for start, end in proof if end > start]
    # A postfix necessity denial scopes the immediately preceding predicate:
    # "steps are not needed" / "el steps mesh matlooba". It must not reach
    # across another substantive noun ("workflow, subscription not needed").
    postfix = _hits(text, [
        "not needed", "not required", "mesh matlooba", "msh matlooba",
        "مش مطلوبة", "مش مطلوب", "غير مطلوبة", "غير مطلوب",
    ])
    grammar = {"is", "are", "be", "it", "they", "here", "el", "ال", "هي", "هو"}
    if any(end <= cue and not re.search(r'[.;!?؟؛,،]', text[end:cue])
           and set(tokens(text[end:cue])) <= grammar
           for _, end in meaningful for cue, _ in postfix):
        return True
    return not meaningful or any(end > boundary for _, end in meaningful)


def _workflow_scope(text, service, definition, adapter, features):
    if _hits(text, features.get("full_kyc", [])):
        return "full_procedure"
    if _hits(text, ["app", "navigation", "MyFawry", "تطبيق"]):
        return "app_navigation"
    if _hits(text, ["full", "complete", "entire", "whole", "end-to-end", "كامل", "كافة", "كل"]):
        return "full_procedure"
    records = [f for f in definition.get("facts", [])
               if f.get("service_id") == service and "workflow" in f.get("selection_tags", [])]
    contracts = {f.get("procedure_contract", f.get("scope", {}).get("procedure"))
                 for f in records} - {None}
    if len(contracts) != 1:
        return None
    contract = next(iter(contracts))
    mappings = adapter.get("workflow", {}).get("procedure_scope_bindings", {})
    return next((name for name, values in mappings.items() if contract in values), contract)


def _navigation_channel(scope, service, definition, adapter):
    """Use a canonical app channel only when the source metadata binds it."""
    if scope != "app_navigation":
        return []
    entry = adapter.get("workflow", {})
    mapping = entry.get("channel_scope_bindings", {}).get("myfawry_app", [])
    records = [f for f in definition.get("facts", []) if f.get("service_id") == service
               and "workflow" in f.get("selection_tags", [])]
    if records and all(f.get("scope", {}).get("channel_id") == "myfawry_app"
                       or f.get("scope", {}).get("channel") in mapping for f in records):
        return ["myfawry_app"]
    return []


def _history_intents(prior, services, adapter):
    by_service = prior.get("requests_by_service", {})
    values = [intent for service in services for intent in by_service.get(service, [])]
    if not values:
        records = prior.get("request_references", prior.get("requests", prior.get("language_requests", [])))
        values = [r.get("intent_id") for r in records if isinstance(r, dict)
                  and r.get("intent_id") and r.get("service_id") in services]
    if not values and len(prior.get("services", [])) == 1:
        values = prior.get("requested_topics", prior.get("intents", prior.get("topics", [])))
    return list(dict.fromkeys(i for value in values for i in
                             ([value] if value in adapter else
                              [key for key, entry in adapter.items()
                               if isinstance(entry, dict) and entry.get("topic") == value])))


def _history_channels(prior, service_id=None, intent_id=None):
    channels = []
    records = prior.get("request_references", prior.get("requests", prior.get("language_requests", [])))
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        if service_id and record.get("service_id") != service_id:
            continue
        if intent_id and record.get("intent_id") != intent_id:
            continue
        channels.extend(record.get("channels", []))
    return list(dict.fromkeys(channels))


def _resolve_catalog_ambiguity(local_ambiguity, goals, definition, adapter, last_services=()):
    """Resolve an alias collision only from an explicit typed antecedent.

    Available facts are deliberately not a disambiguation signal: choosing
    the one provider that happens to have evidence would turn coverage into
    interpretation and could silently answer the wrong service.
    """
    candidate_sets = [set(issue.get("alternatives", [])) for issue in local_ambiguity
                      if issue.get("alternatives")]
    candidates = set.intersection(*candidate_sets) if candidate_sets else set()
    if not candidates:
        return []
    # Observed topic coverage is not a declaration that every other family
    # cannot have that operation. Only a valid antecedent resolves this alias.
    consistent = [service_id for service_id in last_services if service_id in candidates]
    return list(dict.fromkeys(consistent)) if len(set(consistent)) == 1 else []


def _prior_generic_channel_spans(text, local_spans, prior, service_ids, intent_ids, definition=None, adapter=None):
    """Resolve a generic replaced channel only from one typed antecedent."""
    prior_channels = []
    for service_id in service_ids or [None]:
        for intent_id in intent_ids or [None]:
            prior_channels.extend(_history_channels(prior, service_id, intent_id))
    prior_channels = list(dict.fromkeys(prior_channels))
    if len(prior_channels) != 1:
        return local_spans
    channel = prior_channels[0]
    other=_hits(text,["the other channel","other channel","channel el tany","el channel el tany",
                      "القناة التانية","القناة الأخرى"])
    if other and definition is not None and adapter is not None:
        pairs={(service_id,intent_id) for service_id in service_ids or [None]
               for intent_id in intent_ids or [None] if service_id and intent_id}
        alternatives=set()
        if len(pairs)==1:
            service_id,intent_id=next(iter(pairs));topic=adapter.get(intent_id,{}).get("topic")
            alternatives={f.get("required_channel") for f in definition.get("facts",[])
                          if f.get("service_id")==service_id and topic in f.get("selection_tags",[])
                          and f.get("required_channel") and f.get("required_channel")!=channel}
        if len(alternatives)==1:
            return sorted(set(local_spans+[(a,b,next(iter(alternatives))) for a,b in other]))
    patterns = (["machine", "the machine", "الماكينة", "ماكينة"] if channel == "atm" else
                ["branch", "counter", "the branch", "the counter", "الفرع", "الشباك"]
                if _channel_parents().get(channel) == "branch" else [])
    additions = [(a, b, channel) for a, b in _hits(text, patterns)
                 if not any(x <= a and b <= y for x, y, _ in local_spans)]
    return sorted(set(local_spans + additions))


def _scalar_fragment(masked):
    """Recognize only detached quantity modifiers, not arbitrary operations.

    These fragments cannot create a financial predicate. They are accepted
    only when an independent financial demand exists in the same soft clause
    group. Full fact/source/numerical completeness remains mandatory.
    """
    if not re.search(r"\b(?:percentage|percent|rate|minimum|maximum|amount|fee\s+floor|minimum\s+(?:fee|charge|commission))\b|نسبة|نسبه|الحد الأدنى|الحد الادنى|الحد الأقصى|الحد الاقصى|أقل عمولة|اقل عمولة", masked, re.I):
        return False
    remainder = re.sub(
        r"\b(?:what|which|is|are|the|a|an|of|to|for|in|apply|applies|including|include|tell|state|list|show|give|me|please|want|with|along|there|both|each|percentage|percent|rate|minimum|maximum|amount|fee|fees|charge|charges|commission|floor|belong|belongs|sheet|field|its|their|funding)\b|نسبة|نسبه|الحد الأدنى|الحد الادنى|الحد الأقصى|الحد الاقصى|رسوم|عمولة|العمولة|للرسوم|ما|هي|هو|وما|شاملة|شامله|عايز|معاها|هناك|تمويل|خانة|الشيت",
        " ", masked, flags=re.I)
    return not re.search(r"\w", remainder)


def _financial_modifier(masked, features):
    """A quantity/price tail needs a separate established monetary subject."""
    chars = list(masked)
    proof = _hits(masked, features.get("fee", []) + [
        "amount", "minimum", "maximum", "percentage", "rate", "كم", "كام", "المبلغ",
    ])
    if not proof:
        return False
    for a, b in proof:
        chars[a:b] = " " * (b-a)
    functional = {"what", "which", "how", "much", "the", "is", "are", "at", "in",
                  "of", "for", "each", "one", "route", "way", "both", "every", "and",
                  "including", "its", "their", "does", "do", "it", "this", "that", "there", "with", "along", "want",
                  "apply", "applies", "give", "state", "show",
                  "ما", "ايه", "كم", "كام", "في", "كل", "هناك", "معاها", "عايز",
                  "واحد", "طريق", "قد", "هو", "هي", "هل", "وما", "بكام", "حد", "الحد",
                  "دول", "صح", "صحيح", "correct", "true", "those",
                  "el", "fe", "kol", "wa7ed", "taree2", "channel", "kam", "a2al", "nesbet", "3ayez"}
    return not any(not (forms(word) & functional) for word in tokens("".join(chars)))


def _grammatical_subject_head(masked, features):
    chars = list(masked)
    for phrases in features.values():
        for a, b in _hits("".join(chars), phrases):
            chars[a:b] = " " * (b-a)
    functional = {"what", "which", "are", "is", "the", "a", "an", "how", "much",
                  "for", "of", "to", "please", "tell", "me", "give", "explain",
                  "ما", "هي", "هو", "كم", "كام", "قارن", "اشرح", "اريد"}
    return not any(not (forms(word) & functional) for word in tokens("".join(chars)))


def _unknown_named_subject(text, features, protected_spans=()):
    """Return only syntactically provider-like unknown names.

    Capitalization alone is not provider evidence.  A sentence-initial task
    word, field acronym, or source-authored navigation label must not become a
    foreign service.  We challenge an unknown token only when local grammar
    supplies a product predicate, possessive, provider noun, or coordinated
    provider-name shape.  Catalog-qualified foreign providers still use
    ``_unsupported_named_subjects``.
    """
    known = {word for phrases in features.values() for phrase in phrases for word in tokens(phrase)}
    discourse_words = {
        "what", "which", "how", "why", "when", "where", "is", "are", "does", "do",
        "can", "may", "could", "would", "should", "please", "explain", "compare", "give",
        "tell", "state", "take", "walk", "for", "during", "while", "and", "the", "i",
        "also", "additionally", "furthermore", "next", "then", "someone", "somebody",
        "customer", "employee", "applicant", "keep", "limit", "before", "after", "replace",
        "ana", "enta", "enti", "ehna",
    }
    task_artifacts = {
        "memo", "note", "ticket", "card", "form", "sheet", "worksheet", "record", "file",
        "row", "field", "audit", "review", "handover", "report", "desk",
    }
    domain_dimensions = {"egp", "atm", "id", "kyc"}
    known |= discourse_words | task_artifacts | domain_dimensions
    predicate_phrases = [phrase for key in [
        "opening", "initial", "activation", "deposit", "withdrawal", "identity",
        "phone_owner", "existing_wallet", "image", "code", "workflow", "documents",
    ] for phrase in features.get(key, [])]
    protected_spans = list(protected_spans)
    result = []
    for match in re.finditer(r"\b[A-Z][A-Za-z0-9]{2,}(?:['’]s)?\b", text):
        if any(a <= match.start() and match.end() <= b for a, b in protected_spans):
            continue
        value = tokens(match.group())[0].removesuffix("'s")
        if forms(value) & known:
            continue
        # Franco discontinuous negation (ma...sh / mat...sh) is a scope
        # operator, not a capitalized provider name at sentence start.
        if re.fullmatch(r"ma[a-z0-9]{3,}sh", value, re.I):
            continue
        tail = re.split(r"[.;!?\n]", text[match.end():], maxsplit=1)[0][:80]
        product_noun = re.match(r"\s*(?:pay|wallet|service|account|provider)\b", tail, re.I)
        possessive = bool(re.search(r"['’]s$", match.group()))
        predicate = bool(_hits(tail, predicate_phrases))
        coordinated_name = bool(re.match(r"\s*(?:and|or|w)\s+[A-Z]", tail))
        if product_noun or possessive or predicate or coordinated_name:
            result.append(match.group())
    return result


def _task_envelope_fragment(text, goals=(), local_services=()):
    """Recognize bounded report/task framing without hiding a policy ask."""
    value = shadow(text)[0].strip(" .,:;!?\n")
    source = text.strip(" .,:;،؛!?؟\n")
    if not value:
        return None
    english_artifact = bool(re.search(
        r"\b(?:memos?|notes?|tickets?|cards?|forms?|sheets?|worksheets?|records?|handovers?|audits?|reviews?|files?|rows?)\b",
        value, re.I))
    arabic_artifact = bool(re.search(
        r"(?:تذكرة|مذكرة|ملاحظة|كارت|نموذج|ورقة|شيت|محضر|مراجعة|تدقيق|تسليم|ملف|خانة|صف)",
        source, re.I))
    identity_card = bool(re.search(r"بطاقة[^.،؛!?؟]{0,24}(?:الهوية|الرقم\s+القومي|رقم\s+قومي)", source, re.I))
    arabic_card_artifact = bool(re.search(r"بطاقة", source)) and not identity_card
    reporting_artifact = english_artifact or arabic_artifact or arabic_card_artifact
    attributed = reporting_artifact and bool(re.search(
        r"\b(?:says?|states?|contains?|shows?|lists?|labels?|puts?|makes?|wrote|claimed)\b",
        value, re.I) or re.search(
        r"(?:كتب|قال|ذكر|ورد|يقول|يوضح|يحتوي|مكتوب|حاطط|حط)", source, re.I))
    direct_request = bool(re.search(
        r"\b(?:what|which|how|tell|give|list|state|explain|compare|confirm|verify|correct|populate|write)\b",
        value, re.I) or re.search(
        r"(?:ايه|إيه|ماذا|كيف|عايز|محتاج|اكتب|اذكر|اشرح|قارن|تحقق|صحح|املأ)",
        source, re.I))
    if attributed and not direct_request:
        return "reported_task_claim"
    discourse = bool(re.fullmatch(
        r"(?:before\s+(?:we|i)\s+(?:move\s+on|finish|continue|close\s+(?:the\s+)?shift)"
        r"|change\s+of\s+route"
        r"|(?:قبل\s+ما\s+)?(?:اقفل|أقفل)\s+(?:الشيفت|الوردية))",
        value, re.I))
    if discourse:
        return "task_transition"
    if not goals and re.fullmatch(r"for\s+(?:an?\s+)?(?:tariff|fee|record|field)\s+correction", value, re.I):
        return "task_transition"
    layout = bool(re.search(
        r"\b(?:field|fields|point|points|item|items|control|controls|decision|decisions|row|rows|blank|labelled|labeled|cell|cells)\b",
        value, re.I) or re.search(
        r"(?:خانة|خانات|نقطة|نقط|بند|بنود|قرار|قرارين|حقل|حقول)", source, re.I))
    task = bool(re.search(
        r"\b(?:audit|review|cross[- ]?check|handover|end[- ]of[- ]day|shift|reconciling|correction)\b",
        value, re.I) or re.search(
        r"(?:مراجعة|تدقيق|تسليم|نهاية\s+اليوم|الشيفت|الوردية)", source, re.I))
    strong_layout_envelope = task and (layout or reporting_artifact) or reporting_artifact and layout
    if strong_layout_envelope and (not goals or not local_services):
        return "task_envelope"
    return None


def _claim_verification_requested(question, quoted_bounds, features):
    """Allow a quote's predicates (never asserted values) to be verified."""
    if not quoted_bounds or not _hits(question, [
            "verify the claim", "verify those claims", "check the claim", "check those claims",
            "verify both assertions", "verify both claims", "check both assertions", "check both claims",
            "correct the claim", "correct that line", "تحقق من الادعاء", "تحقق من هذين الادعاءين",
            "راجع الادعاء", "صحح الادعاء", "صحح الادعاءين", "صحح الادعاءين فقط"]):
        return False
    outside = list(question)
    for a, b in quoted_bounds:
        outside[a:b] = " " * (b-a)
    for clause in re.split(r"[;،,?؟.]", "".join(outside)):
        hits = {key: _hits(clause, phrases) for key, phrases in features.items()}
        if _excluded_scope(clause, hits, features):
            continue
        if _raw_intents(clause, hits):
            return False
    return True


def _procedure_navigation_signatures(definition):
    """Return labels from ordered, source-bound procedure metadata only."""
    rows = []
    for fact in definition.get("facts", []):
        if not (fact.get("atomic_group") and fact.get("sequence_order") is not None
                and fact.get("procedure_contract") and "workflow" in fact.get("selection_tags", [])):
            continue
        labels = []
        english = fact.get("english", "")
        for match in re.finditer(r"\b(?:[A-Z][A-Za-z0-9]*)(?:\s+[A-Z][A-Za-z0-9]*)+\b", english):
            words = match.group().split()
            labels.extend(" ".join(words[index:]) for index in range(max(0, len(words)-2), len(words)-1))
            labels.append(match.group())
        labels.extend(match.group() for match in re.finditer(r"\b[A-Za-z]*[a-z][A-Z][A-Za-z]*\b", english))
        for view in [fact.get("arabic", ""), english]:
            if isinstance(view, str) and view.strip():
                labels.append(view.strip(" ."))
        for label in labels:
            if label:
                rows.append({"service_id": fact.get("service_id"),
                             "procedure_contract": fact.get("procedure_contract"),
                             "label": label})
    return rows


def _navigation_label_hits(text, definition, channel_table=()):
    # A shared delivery channel (for example Fawry Plus) can appear inside a
    # procedure step, but it is not proof that the question asks for that
    # procedure's service.  Only non-channel navigation labels can carry the
    # source-bound procedure identity.
    channel_labels = {
        " ".join(tokens(alias))
        for row in channel_table
        for aliases in row.get("aliases", {}).values()
        for alias in aliases
    }
    rows = []
    for entry in _procedure_navigation_signatures(definition):
        if " ".join(tokens(entry["label"])) in channel_labels:
            continue
        for a, b in _hits(text, [entry["label"]]):
            rows.append((a, b, entry["service_id"], entry["procedure_contract"]))
    return sorted(set(rows))


def _numeric_response_layout(clause):
    """True only for an explicit number/value-field response constraint."""
    explicit = _hits(clause, [
        "numeric-only field", "number-only field", "numbers only", "numeric values only",
        "two numeric fields", "two number fields", "خانتين رقميتين", "قيمتين رقميتين",
        "الأرقام فقط", "الارقام فقط",
    ])
    counted = _hits(clause, ["two different numbers", "رقمين مختلفين", "رقمان مختلفان"])
    task = _hits(clause, [
        "review", "audit", "sheet", "worksheet", "record", "fields",
        "مراجعة", "تدقيق", "شيت", "ورقة", "خانات", "حقول",
    ])
    return bool(explicit or counted and task)


def _requested_facets(clause, intent, entity_spans=()):
    """Return facets stated by this demand's clause, never the whole query."""
    if intent != "initial_funding":
        return []
    value = shadow(clause)[0]
    positive_balance = bool(_hits(clause, [
        "remain in balance", "stays in balance", "balance treatment",
        "يفضل في الرصيد", "يبقى في الرصيد", "يستقر في الرصيد", "customer balance",
    ])) and not bool(_hits(clause, [
        "do not state whether", "don't state whether", "without the balance", "not the balance",
        "لا تذكر هل", "دون ذكر الرصيد", "مش محتاج الرصيد",
    ]))
    if positive_balance:
        return []
    focus_on_entity=any(right<=start and not tokens(clause[right:start])
                        for start,end in _hits(clause,["only","just","فقط","بس","فحسب","bas"])
                        for left,right in entity_spans)
    amount_only = bool(nominal_scalar_focus(clause,entity_spans) or (not focus_on_entity and re.search(
        r"\b(?:only|just)\s+(?:need|want|give|state|populate|fill|write)?\s*(?:the\s+)?(?:activation\s+)?(?:amount|sum|field)\b"
        r"|\bpopulate\s+only\s+that\s+field\b"
        r"|(?:فقط|بس)\s+(?:المبلغ|القيمة|الخانة)|(?:المبلغ|القيمة)\s+(?:فقط|بس)", value, re.I)))
    # A bounded numeric response layout is also an explicit rendering
    # restriction.  It differs from an ordinary scalar question ("how much"):
    # the user has asked for number/value fields rather than the source's full
    # funding bundle.  Keep this clause-local so another provider can still ask
    # for balance disposition in the same turn.
    numeric_layout = _numeric_response_layout(clause)
    balance_excluded = bool(re.search(
        r"\b(?:do\s+not|don't|without)\b[^.;!?]{0,80}\b(?:remain|available|balance)\b"
        r"|(?:لا|مش|دون|من\s+غير)[^.؛؟!?]{0,80}(?:الرصيد|يظل|يبقى|يفضل)", value, re.I))
    return ["amount_only"] if amount_only or numeric_layout or balance_excluded else []


def _dependency_closure(seed_ids, facts):
    closure = set(seed_ids)
    pending = list(seed_ids)
    while pending:
        fact_id = pending.pop()
        for dependency in facts.get(fact_id, {}).get("dependencies", []):
            if dependency in facts and dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    return closure


def _select_for_raw_request(demand, facts, definition, adapter):
    """Apply independently observed answer facets to source selection."""
    selection = select_for_request(demand, facts, definition, adapter)
    if "amount_only" not in demand.get("requested_facets", []):
        return selection
    amount = [fact_id for fact_id in selection.get("eligible_fact_ids", [])
              if facts.get(fact_id, {}).get("scope", {}).get("minimum_initial_deposit_egp") is not None
              and facts.get(fact_id, {}).get("scope", {}).get("balance_treatment") is None]
    if not amount:
        # The facet cannot narrow a legacy bundle unless a source-bound fact
        # identifies the scalar. Preserve the eligible bundle rather than
        # inventing which member carries the amount.
        unscoped = {**demand, "requested_facets": []}
        return select_for_request(unscoped, facts, definition, adapter)
    # Prefer independently useful roots over a dependent restatement of the
    # same scalar.  The closure preserves any actual prerequisite.
    depended_on = {dependency for fact_id in amount
                   for dependency in facts.get(fact_id, {}).get("dependencies", [])}
    roots = [fact_id for fact_id in amount if fact_id in depended_on] or [
        fact_id for fact_id in amount if not facts.get(fact_id, {}).get("dependencies")]
    chosen = roots or amount
    closure = _dependency_closure(chosen, facts)
    return {**selection,
            "required_fact_ids": sorted(closure),
            "eligible_fact_ids": sorted(closure),
            "gaps": list(selection.get("gaps", []))}


def _service_context_fragment(masked, local_services):
    """Recognize a bounded provider-setting preamble, never a business ask."""
    if not local_services:
        return False
    normalized = shadow(masked)[0].strip(" .,:;،؛")
    return bool(re.fullmatch(
        r"(?:while|when|during)\s+(?:i\s+am\s+|i'm\s+)?(?:checking|reviewing|handling)\s+(?:an?\s+|the\s+)?(?:application|case|request)"
        r"|(?:in|for)\s+(?:the\s+)?(?:case|application|request)\s+(?:of|for)?"
        r"|(?:في\s+حاله|في\s+حالة|اثناء\s+مراجعه|أثناء\s+مراجعة|خلال\s+مراجعه|خلال\s+مراجعة)",
        normalized, re.I))


def _response_scope_fragment(text):
    """Bound explicit response-layout limits without erasing policy verbs."""
    if (_hits(text, ["وهسألك", "وهنسألك", "هسألك", "I'll ask", "I will ask"])
            and _hits(text, ["بعدها", "بعدين", "next", "afterwards"])):
        return True
    if _hits(text, [
            "ما تدخلش", "متدخلش", "دون أي", "من غير أي",
            "ما تخلطهاش", "متخلطهاش", "ما تخلطش", "متخلطش",
            "ولا تذكر", "ما تقولش باقي", "متقولش باقي",
            "mat2olsh ba2y", "mat2olsh ba2i", "ma t2olsh ba2y",
            "no phone ownership rules", "no atm withdrawal fees please"]):
        return True
    normalized = shadow(text)[0].strip(" .,:;،؛")
    patterns = [
        r"(?:please\s+)?limit\s+(?:the\s+)?(?:reply|answer|response)\s+to\s+(?:those|these|the\s+above|the\s+requested)\b",
        r"(?:please\s+)?identify\s+(?:any|the)\s+(?:part|parts?)\s+that\b.*\b(?:reference|references|source|sources)\b",
        r"(?:keep|restrict)\s+(?:the\s+)?(?:reply|answer|response|this)\s+to\b",
        r"(?:give|provide|write|need|want)\s+(?:me\s+)?(?:one|two|three|\d+)\s+(?:answer|answers|field|fields)\s+for\s+each\b",
        r"(?:give|state|write|record)\b[^.;!?]{0,45}\b(?:cost|fee|charge)\b[^.;!?]{0,35}\b(?:route|channel|path)\b",
        r"(?:state|write|record)\b[^.;!?]{0,60}\b(?:if|when)\s+(?:the\s+)?(?:source|reference)\s+(?:supports?|proves?|establishes?)\b",
        r"(?:do\s+not|don't)\s+(?:discuss|mention|include|mix\s+in)\b",
        r"\bomit\b[^.;!?]{0,80}\b(?:ownership|identity|fee|charge|funding|opening|workflow|steps?|documents?)\b",
        r"\bwithout\s+(?:any\s+)?(?:amounts?|fees?|charges?|funding|opening|workflow|steps?|documents?)\b",
        r"(?:the\s+)?rule\s+for\s+each\s+(?:one|item)\b|\brule\s+le\s+kol\s+wa7da\b",
        r"(?:i\s+)?(?:want|need)\s+(?:only|just)\s+that\s+rule\b|(?:answer|state|give)\s+(?:only|just)\s+that\s+rule\b",
        r"(?:3ayez|3aw ez|3awz)\s+(?:el\s+)?rule\s+da\s+bas\b|\brule\s+da\s+bas\b",
        r"(?:ولا\s+تذكر|ما\s*تدخلش|متدخلش|دون\s+أي|من\s+غير\s+أي)\b",
        r"(?:i(?:'ll|\s+will)\s+ask|we(?:'ll|\s+will)\s+ask)\b[^.;!?]{0,80}\b(?:next|after(?:ward)?s?)\b",
        r"(?:وهسألك|وهنسألك|هسألك)\b[^.؛؟!?]{0,80}\b(?:بعدها|بعدين)\b",
        r"(?:الرجاء\s+)?(?:حصر|اقصر|اقتصر)\s+(?:الرد|الاجابه|الإجابة)\s+(?:على|في)\b",
        r"(?:عايز|محتاج|اكتب|اديني|إديني)\s+لكل\s+واحد[هة]?\s+(?:إجابة|اجابة|إجابتين|اجابتين|خانة|خانتين|نقطة|نقطتين)",
        r"(?:اسجل|أسجل|اكتب)[^.؛؟!?]{0,45}(?:تكلفة|تكلفه|عمولة|عموله|رسوم)[^.؛؟!?]{0,40}(?:المسار|الطريق|القناة|الجديد)",
        r"(?:اكتب|اذكر)[^.؛؟!?]{0,55}(?:لو|إذا|اذا)\s+(?:المرجع|المصدر)\s+(?:يثبت|بيثبت|يؤكد|بيؤكد|يدعم)",
        r"(?:القاعدة|قاعده|قاعدة)\s+لكل\s+واحد[هة]",
    ]
    return any(re.search(pattern, normalized, re.I) for pattern in patterns)


def _predicate_scope_restatement(text, goals):
    """A post-answer scope label references, but does not duplicate, a ask."""
    if not goals:
        return False
    normalized = shadow(text)[0].strip(" .,:;،؛")
    comparison = bool(re.search(r"^(?:compare|comparison|مقارنه|مقارنة)\b", normalized, re.I))
    limited = bool(re.search(r"\b(?:only|just)\b|(?:^|\s)(?:بس|فقط)(?:\s|$)", normalized, re.I))
    interrogative = bool(re.search(r"\b(?:what|which|how|كم|كام|ايه|ماذا|ما)\b|[?؟]", normalized, re.I))
    return comparison and limited and not interrogative


def _reported_claim_fragment(text):
    """A quoted assertion under review is context, not a requested rule."""
    has_quote = bool(re.search(r'"[^"\n]+"|“[^”\n]+”|«[^»\n]+»', text))
    speaker = bool(re.search(
        r"\b(?:someone|somebody|customer|employee)\s+(?:wrote|said|claimed|stated)\b"
        r"|(?:كتب|قال|ذكر|ادعى)\s+(?:شخص|ا?ل?عميل|ا?ل?موظف)"
        r"|(?:الشخص|العميل|الموظف|شخص|عميل|موظف)\s+(?:كتب|قال|ذكر|ادعى)",
        text, re.I))
    return has_quote and speaker


def _reported_claim_preamble(text):
    normalized = shadow(text)[0].strip(" .,:;،؛")
    return bool(re.fullmatch(
        r"(?:someone|somebody|customer|employee)\s+(?:wrote|said|claimed|stated)"
        r"|(?:كتب|قال|ذكر|ادعى)\s+(?:شخص|ا?ل?عميل|ا?ل?موظف)"
        r"|(?:الشخص|العميل|الموظف|شخص|عميل|موظف)\s+(?:كتب|قال|ذكر|ادعى)",
        normalized, re.I))


def _excluded_quantity_fragment(text):
    """A negated alternative metric narrows an existing request.

    It is response scope only; it cannot propose or satisfy the positive
    tariff/funding request by itself.
    """
    if not _hits(text, ["not", "mesh", "msh", "mish", "مش", "ليس", "لا أقصد", "لا اقصد"]):
        return False
    return bool(_hits(text, [
        "minimum funding", "minimum deposit", "activation funding", "first funding",
        "حد أدنى للإيداع", "حد ادنى للايداع", "تمويل التفعيل", "إيداع التفعيل", "ايداع التفعيل",
    ]))


def _excluded_generic_fee_fragment(text, hits):
    """Treat an explicitly rejected, untyped fee category as response scope."""
    return bool(hits.get("fee") and _hits(text, [
        "not asking", "not about", "mesh basa2al", "mesh bas2al", "msh basa2al", "msh bas2al", "مش بسأل",
        "لا أسأل", "لا اسأل",
    ]))


def _channel_contrast(text, channel_spans, continuation=""):
    """Return positive and explicitly replaced channel IDs in one clause.

    The operator changes only channel scope. It cannot create an operation or
    service, and a lone negative channel continues through the normal raw
    exclusion path.
    """
    if len(channel_spans) < 2:
        return [channel for _, _, channel in channel_spans], []
    operators = _hits(text, ["instead of", "rather than", "بدل", "بدلا من", "بدلاً من"])
    negations = _hits(text, ["not", "mesh", "msh", "mish", "مش", "ليس"])
    for start, end in sorted(operators + negations):
        before = [(a, b, channel) for a, b, channel in channel_spans if b <= start]
        after = [(a, b, channel) for a, b, channel in channel_spans if a >= end]
        if (start, end) in operators:
            if not before or not after:
                continue
            # A replacement word can introduce two hypothetical alternatives
            # rather than switch the requested channel. An explicit plural
            # price reference ("each route", "both channels", "كل واحد")
            # asks for both sides. Without that independent plural reference,
            # the replacement continues to exclude the old channel.
            plural_alternatives = _hits((text + continuation)[end:], [
                "each one", "each route", "each channel", "each option",
                "both routes", "both channels", "both options", "for each",
                "kol wa7ed", "kol taree2", "kol channel", "el etneen",
                "كل واحد", "كل طريق", "كل قناة", "كل وسيلة",
                "الاثنين", "الاتنين", "الاثنان", "في الحالتين",
            ])
            if plural_alternatives:
                return (list(dict.fromkeys(channel for _, _, channel in channel_spans)), [])
            positive, excluded = before, after
        else:
            if before and after:
                positive, excluded = before, after
            elif len(after) >= 2:
                first, later = after[0], after[1:]
                bridge = text[first[1]:later[0][0]]
                if not _hits(bridge, ["but", "rather", "instead", "لكن", "بس", "إنما", "انما"]):
                    continue
                positive, excluded = later, [first]
            else:
                continue
        return (list(dict.fromkeys(channel for _, _, channel in positive)),
                list(dict.fromkeys(channel for _, _, channel in excluded)))
    return [channel for _, _, channel in channel_spans], []


def _independent_fulfillment(demands, emitted, actual, facts, definition, adapter):
    """Verify fulfilled typed slots without trusting planner completeness.

    This can reconcile a redundant planner/raw status disagreement only when
    every positive raw demand independently selects current source-bound facts,
    those exact facts were emitted in a matching typed slot, and their full
    provenance citations match the registered records. It never supplies a
    fact, resolves an unknown predicate, or turns an evidence gap into success.
    """
    requested = [d for d in demands if d.get("role") == "requested"
                 and not d.get("unsupported_named_provider")]
    slots = actual.get("slots")
    citations = actual.get("citations")
    if not requested or not isinstance(slots, list) or not isinstance(citations, list):
        return {"verified": False, "reason": "typed_slots_or_citations_unavailable", "mappings": []}
    citation_by_fact = {row.get("fact_id"): row for row in citations if isinstance(row, dict)}
    mappings = []
    independently_allowed = set()
    for demand in requested:
        if not demand.get("service_id") or demand.get("service_id") in {"unspecified_service"}:
            return {"verified": False, "reason": "raw_service_not_exact", "mappings": mappings}
        selection = _select_for_raw_request(demand, facts, definition, adapter)
        if selection.get("gaps") or selection.get("conflicts"):
            return {"verified": False, "reason": "independent_selection_has_gap", "mappings": mappings}
        required_ids = set(selection.get("required_fact_ids", []))
        eligible_ids = set(selection.get("eligible_fact_ids", []))
        if not required_ids or not required_ids <= emitted:
            return {"verified": False, "reason": "independent_required_facts_not_emitted", "mappings": mappings}
        independently_allowed.update(eligible_ids)
        matching = [slot for slot in slots if isinstance(slot, dict)
                    and slot.get("service_id") == demand["service_id"]
                    and slot.get("topic") == demand.get("topic")
                    and required_ids <= set(slot.get("supported_fact_ids", []))]
        if not matching:
            # A conservative planner can render an exact immutable assertion
            # through a sibling source slot while missing the narrower topic
            # label.  The independent audit may still certify fulfillment
            # only when every required registered view is present verbatim in
            # the final answer and its source-bound citation is checked below.
            # This cannot rescue a missing fact or a paraphrased claim.
            view = "english" if actual.get("reply_language") == "en" else "arabic"
            answer = actual.get("answer", "")
            if all(isinstance(facts.get(fact_id, {}).get(view), str)
                   and facts[fact_id][view] in answer for fact_id in required_ids):
                matching = [{"service_id": demand["service_id"],
                             "topic": demand.get("topic"),
                             "supported_fact_ids": sorted(required_ids),
                             "independent_exact_view_projection": True}]
        if not matching:
            return {"verified": False, "reason": "typed_fulfilled_slot_missing", "mappings": mappings}
        for fact_id in required_ids:
            fact = facts.get(fact_id)
            citation = citation_by_fact.get(fact_id)
            if not fact or not citation:
                return {"verified": False, "reason": "source_bound_citation_missing", "mappings": mappings}
            expected = {
                "service_id": fact.get("service_id"),
                "source_document": fact.get("source_document"),
                "source_sha256": fact.get("source_sha256"),
                "unit_text_sha256": fact.get("unit_text_sha256"),
                "locator": fact.get("locator"),
            }
            observed = {key: citation.get(key) for key in expected}
            if observed != expected or citation.get("evidence_unit_id") != fact.get("source_unit_id"):
                return {"verified": False, "reason": "source_bound_citation_mismatch", "mappings": mappings}
        mappings.append({"request_id": demand["request_id"], "service_id": demand["service_id"],
                         "intent_id": demand["intent_id"], "topic": demand.get("topic"),
                         "channels": list(demand.get("channels", [])),
                         "required_fact_ids": sorted(required_ids)})
    if not emitted <= independently_allowed:
        return {"verified": False, "reason": "emitted_fact_outside_independent_scope", "mappings": mappings}
    return {"verified": True, "reason": "all_raw_demands_exactly_source_bound", "mappings": mappings}


def _process_context_fragment(text, goals, hits, question, features):
    if not set(goals) <= {"workflow"}:
        return False
    normalized = shadow(text)[0].lstrip()
    context_heads = features.get("context_start", []) + [
        "for", "during", "while", "if", "provided", "اثناء", "أثناء", "في", "ضمن", "إذا", "اذا", "لو"]
    prefix = [span for span in _hits(normalized, context_heads) if span[0] == 0]
    prefix.extend(span for span in _hits(text, context_heads) if span[0] == 0)
    process = hits.get("registration_context") or hits.get("workflow") or _hits(text, [
        "process", "registration", "workflow", "route", "مسار", "تسجيل", "اجراءات",
    ])
    explicit_request = _hits(text, ["steps", "how", "explain", "خطوات", "اشرح", "تسلسل"])
    navigation_head = _hits(text, ["navigation", "app route", "خطوات التطبيق"])
    temporal = bool(_hits(normalized, ["during", "while", "اثناء", "وقت", "wa2t"]))
    later_question = _hits(question, features.get("image", []) + features.get("permission", [])
                           + features.get("branch_condition", []) + features.get("documents", [])
                           + ["branch visit", "visit condition", "required to visit", "must visit", "must they visit",
                              "زيارة الفرع", "الزيارة", "نلزمه بالزيارة", "التوجّه إلى فرع", "التوجه الى فرع"])
    return bool(prefix and process and not explicit_request and later_question
                and (not navigation_head or temporal))


def _correction_preamble(question, a, b, features):
    """Bare 'no' is discourse repair only before an explicit new meaning.

    This never erases 'not ATM', a prohibition, or an unresolved standalone
    negative. The correction cue and operation must occur in the next clause.
    """
    word = shadow(question[a:b])[0].strip(" \t\r\n.,،;؛!?؟")
    if word not in {"no", "nope", "nah", "la", "la2", "laa", "لا", "لاا"}:
        return None
    cursor = b
    while cursor < len(question) and question[cursor] in " \t\r\n,،;؛":
        cursor += 1
    next_break = re.search(r"[,،;؛?؟]", question[cursor:])
    stop = cursor + next_break.start() if next_break else len(question)
    following = question[cursor:stop]
    cues = [span for span in _hits(following, features.get("correction", [])) if span[0] == 0]
    if not cues:
        return None
    hits = {key: _hits(following, phrases) for key, phrases in features.items()}
    if not _raw_intents(following, hits):
        return None
    x, y = cues[0]
    return {"kind": "correction_preamble", "span": _mark(question, a, b, "context_only"),
            "correction_operator": _mark(question, cursor+x, cursor+y, "correction_operator")}


def _layout_modifier(masked):
    words = tokens(masked)
    if not words:
        return None
    separation = _hits(masked, ["separately", "individually", "respectively", "على حدة"])
    references = _hits(masked, ["other", "remaining", "باقي"])
    listed = _hits(masked, ["item", "items", "queries", "parts", "dimensions", "اجزاء"])
    tariffs = _hits(masked, ["tariff", "tariffs"])
    presentation = _hits(masked, ["state", "list", "give", "present", "show", "answer"])
    allowed = {"the", "other", "remaining", "item", "items", "queries", "parts", "dimensions",
               "and", "each", "both", "please", "separately", "individually", "respectively",
               "state", "list", "give", "present", "show", "answer", "tariff", "tariffs",
               "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
               "على", "حده", "باقي", "اجزاء"}
    if any(not word.isdigit() and not (forms(word) & allowed) for word in words):
        return None
    quantified = any(word.isdigit() or word in {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "both"}
                     for word in words)
    if tariffs and presentation and quantified:
        return "tariff_reference"
    return "separate_scopes" if separation else "list_reference" if references and listed else None


def _raw_substitution_constraint(text, goals, demands, services, excluded):
    """A prohibited replacement relates requested scopes; it excludes neither."""
    actions = _hits(text, ["replace", "substitute", "swap", "mix", "confuse"])
    normalized, positions = shadow(text)
    stems = {prefix + root for prefix in ["", "ا", "ت", "ي", "ن"] for root in ["بدل", "ستبدل", "خلط"]}
    for word in re.finditer(r'[\u0621-\u064a]+', normalized):
        value = word.group()
        bases = [value]
        if value.endswith("ش"):
            bases.append(value[:-1])
            bases.extend(value[len(prefix):-1] for prefix in ["ما", "م"] if value.startswith(prefix))
        if any(base in stems for base in bases):
            actions.append((positions[word.start()], positions[word.end()-1]+1))
    if not actions or not excluded:
        return False, None
    subjects = {(service, ()) for service in services}
    if not subjects:
        subjects = {(d["service_id"], tuple(d.get("unsupported_named_provider", [])))
                    for d in demands if d["role"] == "requested"}
    parents = [d for d in demands if d["role"] == "requested" and d["intent_id"] in goals
               and (d["service_id"], tuple(d.get("unsupported_named_provider", []))) in subjects]
    connectors = _hits(text, ["with", "for", "by", "instead of"])
    points = sorted({point for proof in goals.values() for point in proof})
    clitic_connector = any(tokens(text[a:b]) and tokens(text[a:b])[0].startswith("ب") for a, b in points)
    if len(subjects) == 1 and len(goals) >= 2 and set(goals) <= {d["intent_id"] for d in parents} and (connectors or clitic_connector):
        return True, {"kind": "predicate_separation", "intent_ids": sorted(goals),
                      "bound_request_ids": [d["request_id"] for d in parents],
                      "operator_spans": actions + connectors}
    return True, None


def _raw_past_event_context(text, interrogative=False):
    """A narrated event does not request the policy named by its object noun."""
    words = tokens(text)
    question_starts = {"what", "which", "where", "how", "why", "when", "has", "have", "had", "is", "are", "was", "were", "did", "does", "do", "هل", "ليه", "ازاي"}
    requests = _hits(text, ["explain", "show", "tell", "give", "need", "want", "اشرح", "عايز", "محتاج", "اريد"])
    hypothetical = _hits(text, ["if", "unless", "لو", "اذا", "بشرط"])
    events = _hits(text, ["came out", "took", "was printed", "was sent", "was requested", "did not print", "failed to print", "خرج", "طلع"])
    return bool(events and not (interrogative or requests or hypothetical or words and words[0] in question_starts))


def _raw_unknown_negative_predicate(text):
    """A familiar object noun cannot hide an unfamiliar negated action."""
    words = tokens(text)
    known = {"explain", "describe", "discuss", "mention", "include", "show", "give", "list", "state", "provide", "ask",
             "perform", "execute", "transfer", "cancel", "refund", "create", "make", "open", "close", "print", "reprint",
             "assess", "verify", "validate", "review", "evaluate", "check", "confirm", "treat", "classify",
             "pay", "add", "increase", "deposit", "withdraw", "put", "call", "promise", "want", "need"}
    for index, word in enumerate(words):
        next_index = index + 2 if words[index:index+2] == ["do", "not"] else index + 1 if word in {"don't", "never"} else None
        if next_index is not None and next_index < len(words) and not (forms(words[next_index]) & known):
            return True
    normalized, positions = shadow(text)
    known_marks = {point for _, point in _raw_negative_operation_marks(text)}
    directives = {prefix + root + suffix for prefix in ["", "ا", "ت", "ي", "ن"]
                  for root in ["شرح", "ذكر", "كلم", "قول", "سال"] for suffix in ["", "ي", "وا"]}
    for word in re.finditer(r'[\u0621-\u064a]{3,}ش', normalized):
        value = word.group()
        prior = tokens(normalized[:word.start()])
        negative = bool(prior and prior[-1] == "ما") or value.startswith(("ما", "م"))
        if not negative or (positions[word.start()], positions[word.end()-1]+1) in known_marks:
            continue
        stems = [value[:-1]] + [value[len(prefix):-1] for prefix in ["ما", "م"] if value.startswith(prefix)]
        if not any(stem in directives for stem in stems):
            return True
    return False


def _identity_modifier(masked):
    for attribute, aliases in IDENTITY_ATTRIBUTES.items():
        proof = _hits(masked, aliases)
        if not proof:
            continue
        chars = list(masked)
        for a, b in proof:
            chars[a:b] = " " * (b-a)
        functional = {"the", "and", "be", "it", "itself", "must", "check", "required", "is", "are"}
        if all(forms(word) & functional for word in tokens("".join(chars))):
            return attribute, aliases
    return None


def _attribute_in_evidence(attribute, fact):
    # Raw demand detection stays independent. Only source attribute proof is
    # shared with source-scope selection; English drafts cannot supply proof.
    return requested_attribute_support(fact, "identity", attribute)


def _services_for_intent(intent, proof, entities, services, hits, demands, group, text):
    """Independent provider-operation attachment from current lexical spans."""
    heads_by_intent = {
        "deposit_tariff": ["deposit"], "withdrawal_tariff": ["withdrawal"],
        "opening_fee": ["opening"], "initial_funding": ["initial", "activation"],
        "balance_treatment": ["balance_disposition"], "identity": ["identity"],
        "phone_ownership": ["phone_owner"], "existing_wallet": ["existing_wallet"],
        "transaction_code": ["code"], "workflow": ["workflow"],
    }
    if not entities:
        prior = [d for d in demands if d["role"] == "requested" and d["intent_id"] == intent
                 and d["group"] == group and d["service_id"] is not None]
        plural = _hits(text, ["both", "each", "كل", "الاتنين", "مين فيهم"])
        return list(dict.fromkeys(d["service_id"] for d in prior)) if prior and not plural else services
    owners = list(dict.fromkeys(s for _, _, s in entities))
    if len(owners) < 2:
        return services
    all_heads = sorted({p for keys in heads_by_intent.values() for k in keys for p in hits.get(k, [])})
    first_end, last_start = min(y for _, y, _ in entities), max(x for x, _, _ in entities)
    # Adjacent provider lists share their predicates; interleaved operation
    # heads bind separately instead of creating a provider×operation product.
    if not any(first_end <= a < last_start for a, _ in all_heads):
        return owners
    heads = [p for key in heads_by_intent.get(intent, []) for p in hits.get(key, [])] or proof
    chosen = []
    for a, b in heads:
        distances = {sid: min(max(0, a-y, x-b) for x, y, s in entities if s == sid) for sid in owners}
        best = min(distances.values())
        chosen.extend(sid for sid, distance in distances.items() if distance == best)
    return list(dict.fromkeys(chosen)) or services


def _raw_distributive_subject_reference(text):
    """Independent grammatical proof for a plural provider referent.

    The audit deliberately duplicates this small detector instead of trusting
    the planner contract.  It can only distribute over explicit providers in
    the raw current question.
    """
    value = shadow(text)[0]
    pair = [
        r'\b(?:either|neither|both)\s+(?:provider|providers|service|services|wallet|wallets)\b',
        r'\b(?:either|neither|both)\s+of\s+(?:the\s+)?(?:providers|services|wallets)\b',
        r'(?<!\w)(?:كلا|كلتا)\s+(?:الخدمتين|المحفظتين|المقدمين)(?!\w)',
        r'(?<!\w)(?:أي|اي|لاي)\s+من\s+(?:الخدمتين|المحفظتين|مقدمي\s+الخدمة)(?!\w)',
        r'(?<!\w)(?:ولا\s+واحد|الاتنين|الاثنين)\s+من\s+(?:الخدمتين|المحفظتين|مقدمي\s+الخدمة)(?!\w)',
        r'\b(?:either|neither|both|wala\s+wa7ed|el\s+etneen)\s+(?:provider|providers|service|services|wallet|wallets)\b',
        r'\b(?:either|neither|both)\s+(?:sum|amount|deposit|funding)\b',
    ]
    broad = [
        r'\b(?:each|every|all)\s+(?:provider|providers|service|services|wallet|wallets)\b',
        r'(?<!\w)(?:كل|جميع)\s+(?:خدمة|الخدمات|محفظة|المحافظ|مقدم\s+خدمة|مقدمي\s+الخدمة)(?!\w)',
        r'\b(?:kol|gamee3)\s+(?:provider|providers|service|services|wallet|wallets)\b',
    ]
    if any(re.search(pattern, value, re.I) for pattern in pair):
        return "pair"
    if any(re.search(pattern, value, re.I) for pattern in broad):
        return "all"
    return None


def audit_question(question, actual, facts, definition, prior_context=None):
    features, channel_table, adapter, roles = _resources()
    if not isinstance(question, str):
        raise TypeError("question must be raw text")
    facts = _fact_rows(facts)
    emitted = set(actual.get("supported_fact_ids", []))
    entity_hits, issues = _entities(question, definition, roles, features)
    ambiguous_bounds = {(x["span"]["start"], x["span"]["end"]) for x in issues}
    all_entities = entity_hits
    quoted_bounds = [(match.start(), match.end()) for match in
                     re.finditer(r'"[^"\n]+"|“[^”\n]+”|«[^»\n]+»', question)]
    claim_verification = _claim_verification_requested(question, quoted_bounds, features)
    temporal_scopes = exclusive_temporal_scopes(question, excluded_spans=(
        [] if claim_verification else quoted_bounds))
    unsupported_subjects = _unsupported_named_subjects(question, all_entities)
    entity_hits = [(a, b, sid) for a, b, sid in entity_hits if (a, b) not in ambiguous_bounds]
    entity_hits = [(a, b, sid) for a, b, sid in entity_hits if not any(
        q['event_span']['start'] <= a and b <= q['event_span']['end'] for q in temporal_scopes)]
    unsupported_subjects = [row for row in unsupported_subjects if not any(
        q['event_span']['start'] <= row['start'] and row['end'] <= q['event_span']['end'] for q in temporal_scopes)]
    context_rules = json.loads((ROOT / 'resources/entity_disambiguation.json').read_text(encoding='utf-8'))
    entity_hits = [hit for hit in entity_hits
                   if not _raw_product_context_entity(question, hit, entity_hits, roles, context_rules)]
    masked = list(question)
    for a, b, _ in all_entities:
        masked[a:b] = " " * (b - a)
    for subject in unsupported_subjects:
        masked[subject["start"]:subject["end"]] = " " * (subject["end"] - subject["start"])
    masked = "".join(masked)
    raw_channel_hits = [(a, b, channel) for a, b, channel in _channels(question, channel_table)
                        if not any(x <= a and y >= b for x, y, _ in all_entities)]
    # Bare Arabic "الصراف" can mean an ATM or a cashier/operator.  A compound
    # such as "ماكينة الصراف" remains catalog-proven ATM language; the bare
    # noun must be clarified rather than guessed from the available fact.
    ambiguous_channel_bounds = {(a, b) for a, b, channel in raw_channel_hits
                                if channel == "atm" and re.fullmatch(r"\s*الصراف\s*", question[a:b])}
    for match in re.finditer(r"(?<!\w)الصراف(?!\w)", question):
        prefix = question[max(0, match.start()-12):match.start()]
        suffix = question[match.end():match.end()+12]
        if re.search(r"(?:ماكينة|جهاز|درج)\s*$", prefix) or re.match(r"\s*(?:الالي|الآلي)", suffix):
            continue
        # A reflexive channel reference may inherit one explicit current-turn
        # antecedent.  This does not make bare "الصراف" an ATM alias: without
        # "نفسه/نفسها" and exactly one preceding typed channel it remains
        # ambiguous between an ATM and a human teller/cashier.
        if re.match(r"\s*(?:نفسه|نفسها|ذاته|ذاتها)(?!\w)", suffix):
            prior_hits = [row for row in raw_channel_hits
                          if row[1] <= match.start()
                          and not re.search(r"[.;؛!?؟]", question[row[1]:match.start()])]
            prior_channels = {channel for _, _, channel in prior_hits}
            if len(prior_channels) == 1:
                raw_channel_hits.append((match.start(), match.end(), prior_channels.pop()))
                continue
        if not any(a <= match.start() and match.end() <= b for a, b, _ in raw_channel_hits):
            ambiguous_channel_bounds.add((match.start(), match.end()))
    channel_hits = [(a, b, channel) for a, b, channel in raw_channel_hits
                    if (a, b) not in ambiguous_channel_bounds]
    prior, prior_services = _prior(prior_context, definition)
    comparative_reference = bool(re.search(r"\bwhich one\b|\bboth\b|مين فيهم|الاتنين|الاثنين", question, re.I))
    if comparative_reference:
        prior_services = [s for s in prior.get("comparison_services", prior_services)
                          if s in definition.get("service_profiles", {})]
    inherited_intents = _history_intents(prior, prior_services, adapter)
    cuts = {0, len(question)}
    reported_task_bounds = []
    sentence_start = 0
    for boundary in list(re.finditer(r"[.!?؟](?:\s|$)", question)) + [None]:
        sentence_end = boundary.start() if boundary is not None else len(question)
        sentence = question[sentence_start:sentence_end]
        sentence_services = list(dict.fromkeys(
            service for start, _, service in entity_hits
            if sentence_start <= start < sentence_end))
        if _task_envelope_fragment(sentence, (), sentence_services) == "reported_task_claim":
            reported_task_bounds.append((sentence_start, sentence_end))
        sentence_start = boundary.end() if boundary is not None else len(question)
    for start, end in quoted_bounds:
        cuts.update((start, end))
    separators = list(re.finditer(
        r"[;؛,،?؟]|\.(?=\s|$)|\band\b|\balongside\b|\bas well as\b|\bbut also\b|(?<!\w)و(?!\w)", question, re.I))
    contrasts = [match for match in re.finditer(r'\b(?:versus|vs)\b', question, re.I)
                 if not any(start <= match.start() < end for start, end, _ in all_entities)
                 and not any(start <= match.start() < end for start, end in quoted_bounds)]
    boundaries = [match for match in separators
                  if not any(start <= match.start() < end for start, end, _ in all_entities)]
    def raw_operand_has_predicate(start, end):
        text, local_mask = question[start:end], masked[start:end]
        hits = {key: _hits(local_mask, values) for key, values in features.items()}
        return bool(_raw_intents(text, hits)
                    or nominal_catalog_heads(local_mask, _catalog_intent_ids())
                    or _noncore_meanings(text, (), local_mask)[0])
    for index, contrast in enumerate(contrasts):
        left = max([0] + [match.end() for match in boundaries if match.end() <= contrast.start()]
                   + ([contrasts[index-1].end()] if index else []))
        right = min([len(question)] + [match.start() for match in boundaries if match.start() >= contrast.end()]
                    + ([contrasts[index+1].start()] if index+1 < len(contrasts) else []))
        if all(any(start <= a < end for a, b, sid in entity_hits)
               and raw_operand_has_predicate(start, end)
               for start, end in [(left, contrast.start()), (contrast.end(), right)]):
            separators.append(contrast)
    # Split a colon only when its prefix is a bounded task/report envelope.
    # Colons in ordinary provider questions retain the existing grammar.
    for colon in re.finditer(r":", question):
        left = max([0] + [match.end() for match in re.finditer(r"[.;؛!?؟]", question[:colon.start()])])
        prefix = question[left:colon.start()]
        prefix_services = list(dict.fromkeys(service for a, b, service in entity_hits
                                              if left <= a < colon.start()))
        if _task_envelope_fragment(prefix, (), prefix_services):
            separators.append(colon)
    separators.sort(key=lambda match: (match.start(), match.end()))
    separators = [separator for separator in separators
                  if not any(start <= separator.start() < end for start, end, _ in all_entities)
                  and not any(start < separator.start() < end for start, end in quoted_bounds)]
    # A bare conjunction between adjacent catalog entities is a provider list,
    # not a clause boundary.  An operation between the names keeps the split.
    provider_connectors = set()
    channel_connectors = set()
    operation_keys = ["opening", "initial", "activation", "deposit", "withdrawal", "identity",
                      "phone_owner", "existing_wallet", "image", "code", "workflow", "documents"]
    for separator in separators:
        if not re.fullmatch(r"\s*(?:and|و)\s*", separator.group(), re.I):
            continue
        channel_before = [(a, b, channel) for a, b, channel in channel_hits if b <= separator.start()]
        channel_after = [(a, b, channel) for a, b, channel in channel_hits if a >= separator.end()]
        if channel_before and channel_after:
            left_channel = max(channel_before, key=lambda row: row[1])
            right_channel = min(channel_after, key=lambda row: row[0])
            if not re.search(r"[.;!?؟؛]", question[left_channel[1]:right_channel[0]]):
                channel_connectors.add((separator.start(), separator.end()))
        before = [(a, b, service) for a, b, service in entity_hits if b <= separator.start()]
        after = [(a, b, service) for a, b, service in entity_hits if a >= separator.end()]
        if before and after:
            left = max(before, key=lambda row: row[1])
            right = min(after, key=lambda row: row[0])
            between = question[left[1]:right[0]]
            if not any(_hits(between, features.get(key, [])) for key in operation_keys):
                provider_connectors.add((separator.start(), separator.end()))
    separators = [separator for separator in separators
                  if (separator.start(), separator.end()) not in provider_connectors | channel_connectors]
    # A comma can separate an operation scenario from its own price query.
    # Join only a pure adjacent price question, with no new provider/channel
    # or operation on that side. Other coordinated clauses stay independent.
    joined = set()
    for index, separator in enumerate(separators):
        if separator.group() not in {",", "،"}:
            continue
        left = separators[index-1].end() if index else 0
        right = separators[index+1].start() if index+1 < len(separators) else len(question)
        suffix = masked[separator.end():right]
        if any(separator.end() <= a < right for a, _, _ in entity_hits + channel_hits):
            continue
        queries = _raw_nominal_price_questions(suffix)
        if not queries:
            continue
        remaining = list(suffix)
        for row in queries:
            for start, end in [row["head"]] + row["question"]:
                remaining[start:end] = " " * (end-start)
        if set(tokens("".join(remaining))) - {"is", "are", "the", "a", "my", "your", "its", "this", "that", "it", "هو", "هي"}:
            continue
        prefix = masked[left:separator.start()]
        verbs, _ = _raw_money_addition(prefix)
        known_operation = any(_hits(prefix, features.get(key, []))
                              for key in ["deposit", "withdrawal", "opening", "activation", "initial"])
        if verbs or known_operation:
            joined.add((separator.start(), separator.end()))
    separators = [separator for separator in separators if (separator.start(), separator.end()) not in joined]
    for match in separators:
        cuts.update((match.start(), match.end()))
    edges = sorted(cuts)
    demands = []
    missing = []
    scalar_modifiers = []
    structural_modifiers = []
    attribute_modifiers = []
    pending_services = []
    pending_intents = []
    numeric_layout_groups = set()
    last_services = []
    last_intents = []
    last_channels = []
    last_unsupported_subjects = []
    context_only = []
    record_references = []
    noncore_objects = set()
    resolved_ambiguity_bounds = set()
    group = 0
    previous_end = 0
    fronted_contexts=fronted_process_contexts(question,[(a,b) for a,b,_ in entity_hits]
                                             +[(s['start'],s['end']) for s in unsupported_subjects],
                                             [(a,b) for a,b,_ in channel_hits],features)
    for a, b in zip(edges, edges[1:]):
        text = question[a:b]
        if quote_envelope_fragment(question,a,b,quoted_bounds):
            context_only.append({'kind':'unverified_quote_envelope','verified':False,
                                 'span':_mark(question,a,b,'context_only')})
            continue
        if text.strip() and all(unicodedata.category(ch) in {"Cf", "Zs"} for ch in text.strip()):
            context_only.append({"kind": "unicode_format_control",
                                 "span": _mark(question, a, b, "context_only")})
            continue
        if not text.strip() or any(m.start() == a and m.end() == b for m in separators):
            continue
        if re.search(r"[.;؛?؟]", question[previous_end:a]):
            group += 1
        previous_end = b
        local_services = list(dict.fromkeys(s for x, y, s in entity_hits if a <= x < b))
        local_unsupported = [subject for subject in unsupported_subjects if a <= subject["start"] < b]
        if local_services:
            last_unsupported_subjects = []
        elif local_unsupported:
            # An explicit foreign subject replaces canonical conversational
            # context; it never borrows that provider's facts or prior topic.
            last_unsupported_subjects = local_unsupported
            last_services = []
            prior_services = []
            inherited_intents = []
        active_unsupported = local_unsupported or (last_unsupported_subjects if not local_services else [])
        parent_demands=[d for d in demands if d['role']=='requested']
        preservation=binding_preservation_directive(text)
        bound_scopes={(d['service_id'],d['intent_id']) for d in parent_demands}
        if preservation and len(bound_scopes)>=2:
            context_only.append({'kind':'request_binding_preservation','bound_scopes':sorted(bound_scopes),
                                 'span':_mark(question,a,b,'response_constraint')})
            continue
        entity_points=[(x-a,y-a) for x,y,_ in entity_hits if a<=x<b]
        if (entity_nonrestriction(text,entity_points) and local_services and parent_demands
                and set(local_services)<=set(d['service_id'] for d in parent_demands
                                            if d['group']==parent_demands[-1]['group'])):
            context_only.append({'kind':'nonrestrictive_entity_reference','span':_mark(question,a,b,'context_only')})
            continue
        comparison_context=bool(_hits(question[:a],features.get('comparison',[]))
                                or len({d['service_id'] for d in parent_demands})>1)
        if entity_omission(text,entity_points,comparison_context):
            if parent_demands:
                target_group=parent_demands[-1]['group']
                parents=[d for d in parent_demands if d['group']==target_group]
                templates={d['intent_id']:d for d in parents}
                for demand in parents:
                    if demand['service_id'] in local_services:
                        demand['role']='excluded';demand['exclusion_scope_groups']=[target_group]
                for service in local_services:
                    for intent,parent in templates.items():
                        demands.append({'request_id':'Q'+str(len(demands)+1),'service_id':service,'intent_id':intent,
                            'topic':parent['topic'],'channels':[],'conditions':[],'period':parent.get('period'),
                            'procedure_scope':None,'role':'excluded','requested_facets':[],
                            'group':group,'exclusion_scope_groups':[target_group],
                            'evidence_spans':[_mark(question,a,b,'excluded_service')],
                            'clause_span':_mark(question,a,b,'excluded_service'),
                            'antecedent':{'request_id':parent['request_id'],'clause_span':parent['clause_span']}})
            context_only.append({'kind':'current_task_service_exclusion','span':_mark(question,a,b,'excluded_service')})
            continue
        if not local_services and not active_unsupported and response_layout_directive(text):
            context_only.append({'kind':'response_layout_directive','span':_mark(question,a,b,'response_constraint')})
            continue
        if any(span['start']<=a and b<=span['end'] for span in fronted_contexts):
            pending_services=list(dict.fromkeys(pending_services+local_services));last_services=pending_services[:]
            context_only.append({'kind':'fronted_process_context','span':_mark(question,a,b,'context_only')})
            for span in fronted_contexts:
                if span['start']<=a and b<=span['end'] and span['unresolved_context_tokens']:
                    missing.append({'code':'raw_fronted_context_dimension_unresolved',
                                    'span':_mark(question,a,b,'unresolved_context'),
                                    'tokens':span['unresolved_context_tokens']})
            continue
        local_ambiguity = [issue for issue in issues if issue.get("code") == "raw_entity_ambiguous"
                           and a <= issue["span"]["start"] < b]
        local_channel_spans = sorted((x-a, y-a, channel) for x, y, channel in channel_hits if a <= x < b)
        local_ambiguous_channels = [(x, y) for x, y in ambiguous_channel_bounds if a <= x < b]
        if local_ambiguous_channels:
            missing.extend({"code": "raw_channel_ambiguous",
                            "alternatives": ["atm", "cashier"],
                            "span": _mark(question, x, y, "channel")}
                           for x, y in local_ambiguous_channels)
        local_channel_spans = _prior_generic_channel_spans(
            text, local_channel_spans, prior,
            local_services or last_services or prior_services,
            last_intents or inherited_intents, definition, adapter)
        all_local_channels = list(dict.fromkeys(channel for _, _, channel in local_channel_spans))
        tail = question[b:]
        hard_boundary = re.search(r"[.;؛?؟]", tail)
        contrast_continuation = tail[:hard_boundary.start()] if hard_boundary else tail
        local_channels, contrast_excluded_channels = _channel_contrast(
            text, local_channel_spans, contrast_continuation)
        local_mask = masked[a:b]
        hits = {k: _hits(local_mask, phrases) for k, phrases in features.items()}
        # Bounded language variants propose only their typed predicate. They
        # never add a service, channel, fact, or answer.
        hits["workflow"] = sorted(set(hits.get("workflow", []) + _hits(
            local_mask, ["walkthrough", "full procedure", "taree2a kamla", "tare2a kamla",
                         "app registration", "registration in the app", "completes app registration",
                         "investment journey", "app journey", "start investing journey",
                         "مسار بدء الاستثمار", "رحلة بدء الاستثمار"])))
        hits["code"] = sorted(set(hits.get("code", []) + _hits(
            local_mask, ["raqm el service", "ra2m el service", "service raqm"])))
        hits["activation"] = sorted(set(hits.get("activation", []) + _hits(
            local_mask, ["activates", "activate that wallet", "turns on the wallet",
                         "يفعّل", "يفعل", "يشغّل", "يشغل", "بيشغّل", "بيشغل"])))
        hits["withdrawal"] = sorted(set(hits.get("withdrawal", []) + _hits(
            local_mask, ["هيصرف", "يصرف", "هيسحب", "يسحب", "صرف نقدي", "سحب نقدي"])))
        hits["opening"] = sorted(set(hits.get("opening", []) + _hits(
            local_mask, ["wallet creation", "create the wallet", "إنشاء المحفظة", "انشاء المحفظة", "رسم إنشاء", "رسم انشاء"])))
        hits["workflow"] = sorted(set(hits.get("workflow", []) + _hits(
            local_mask, ["menu path", "menu navigation", "مسار القوائم", "ترتيب القوائم"])))
        hits["branch_condition"] = sorted(set(hits.get("branch_condition", []) + _hits(
            local_mask, ["conditional on an app instruction", "conditional on app instruction",
                         "app-directed visit", "visit conditional", "must they visit", "visit trigger",
                         "الزيارة مشروطة بتوجيه التطبيق"])))
        hits["image"] = sorted(set(hits.get("image", []) + _hits(
            local_mask, ["externally supplied images", "outside images", "external images"])))
        hits["existing_wallet"] = sorted(set(hits.get("existing_wallet", []) + _hits(
            local_mask, ["duplicate-wallet", "duplicate wallet", "another linked wallet"])))
        hits["phone_owner"] = sorted(set(hits.get("phone_owner", []) + _hits(
            local_mask, ["phone ownership", "mobile ownership", "line ownership", "mobile-line ownership"])))
        hits["balance_disposition"] = sorted(set(hits.get("balance_disposition", []) + _hits(
            local_mask, ["balance treatment", "balance disposition", "treatment of the balance"])))
        navigation_hits = _navigation_label_hits(text, definition, channel_table)
        navigation_bounds = [(x, y) for x, y, _, _ in navigation_hits]
        if navigation_hits:
            # Labels such as "Add Fund" are ordered UI steps, not a cash-in
            # operation.  Their provider comes only from procedure metadata.
            hits["deposit"] = [point for point in hits.get("deposit", [])
                               if not any(point[0] < y and x < point[1] for x, y in navigation_bounds)]
            if _hits(local_mask, ["source order", "correct order", "sequence", "registration",
                                  "replace that sequence", "بالترتيب", "تسلسل", "ترتيب"]):
                hits["workflow"] = sorted(set(hits.get("workflow", []) + navigation_bounds))
        if re.search(r"\bb\s+esm\s+sa7eb\b", local_mask, re.I):
            hits["phone_owner"] = sorted(set(hits.get("phone_owner", [])
                                               + _hits(local_mask, ["b esm sa7eb"])))
        if re.search(r"\bwallet\s+tanya\b", local_mask, re.I):
            hits["existing_wallet"] = sorted(set(hits.get("existing_wallet", [])
                                                   + _hits(local_mask, ["wallet tanya"])))
        code_context = _raw_code_compound_context(local_mask, hits)
        if code_context:
            hits["workflow"] = [point for point in hits.get("workflow", []) if point not in code_context]
            context_only.extend({"kind": "code_compound_modifier", "span": _mark(question, a+x, a+y, "context_only")}
                                for x, y in code_context)
        addition_verbs, money_addition = _raw_money_addition(local_mask)
        objectless_addition = []
        addition_antecedent = None
        bound_addition = []
        charges = []
        if money_addition:
            hits["deposit"] = sorted(set(hits.get("deposit", []) + money_addition))
            charges = _raw_charge_dimension(local_mask, money_addition)
            charge_heads = [row["head"] for row in charges]
            hits["balance_disposition"] = [point for point in hits.get("balance_disposition", [])
                                           if not any(point[0] < end and start < point[1] for start, end in charge_heads)]
            hits["fee"] = sorted(set(hits.get("fee", []) + charge_heads
                                     + [point for row in charges for point in row["question"]]))
        elif addition_verbs:
            objectless_addition = _raw_objectless_addition(local_mask, addition_verbs, features)
            if objectless_addition:
                charges = _raw_charge_dimension(local_mask, addition_verbs)
                heads = [row["head"] for row in charges]
                hits["balance_disposition"] = [point for point in hits.get("balance_disposition", [])
                                               if not any(point[0] < end and start < point[1] for start, end in heads)]
            # Preserve already authored balance/wallet deposit phrases, while
            # rejecting bare lexical addition cues with a nonfinancial object.
            typed = [point for phrase in features.get("deposit", [])
                     if set(tokens(phrase)) & {"رصيد", "الرصيد", "balance", "wallet", "account"}
                     for point in _hits(local_mask, [phrase])]
            # The existing top-up head remains usable when no contradictory
            # direct object is present; this does not propose a new goal.
            topups = _hits(local_mask, ["top up", "tops up", "topped up", "topping up",
                                       "top-up", "top-ups", "topped-up", "topping-up"])
            other_objects = _hits(local_mask, ["stock", "inventory", "item", "product", "fee", "charge", "amount",
                                               "مخزون", "رسوم", "مبلغ", "بضاعة", "كمية"])
            articles = {"the", "a", "an", "my", "your", "some", "more", "extra", "additional", "arbitrary"}
            typed += [point for point in topups
                      if not any(point[1] <= start <= point[1] + 40
                                 and all(word in articles for word in tokens(local_mask[point[1]:start]))
                                 for start, _ in other_objects)]
            hits["deposit"] = [point for point in hits.get("deposit", [])
                               if not any(point[0] < end and start < point[1] for start, end in addition_verbs)
                               or point in typed]
        goals = _raw_intents(text, hits)
        context_only.extend({"kind":"activation_requirement_purpose",
                             "span":_mark(question,a+x,a+y,"context_only")}
                            for x,y in hits.get("activation_purpose_context",[]))
        context_only.extend({"kind":"condition_procedure_context",
                             "span":_mark(question,a+x,a+y,"context_only")}
                            for x,y in hits.get("workflow_purpose_context",[]))
        service_replacement = bool(local_services and re.search(
            r"\b(?:switch|change|replace)\b[^.;!?]{0,40}\b(?:provider|service)\b"
            r"|(?:بد[ّ]?ل|غي[ّ]?ر|استبدل)[^.;؟!?]{0,40}(?:الخدمة|الشركة|المقدم)",
            local_mask, re.I))
        if service_replacement and len(inherited_intents) == 1:
            # A provider replacement changes only the entity coordinate. Its
            # predicate comes from one traceable prior requested meaning.
            goals = {inherited_intents[0]: [(0, len(text))]}
        if "branch_condition" in goals and "workflow" in goals:
            asks_for_trigger = bool(re.search(
                r"\bwhat(?:\s+actually)?\s+triggers\b|\bwhich\s+condition\b|\bunder\s+what\s+condition\b"
                r"|شرط\s+الزيارة|ما\s+الشرط|ايه\s+الشرط|متى|\bwhen\s+(?:is|must)\b"
                r"|(?:هل|فهل)[^.؛؟!?]{0,80}(?:نلزمه|تلزمه|مطلوب)[^.؛؟!?]{0,40}(?:زيارة|الزيارة)",
                local_mask, re.I))
            asks_for_steps = bool(_hits(local_mask, [
                "steps", "walkthrough", "full procedure", "explain the route", "خطوات", "اشرح الخطوات",
            ]))
            if asks_for_trigger and not asks_for_steps:
                goals.pop("workflow", None)
        ongoing_balance = _raw_ongoing_balance_policy(local_mask)
        if ongoing_balance:
            goals["balance_limit"] = ongoing_balance
        if _raw_activation_principal(local_mask, hits):
            # Asking how much money to add for activation asks for funded
            # principal. The amount interrogative alone is not a charge.
            goals.pop("opening_fee", None)
        retained = _retained_balance_demand(local_mask)
        if retained:
            goals["balance_treatment"] = retained
        elif _hits(local_mask, ["remain", "stay", "retain", "retained", "keep", "kept", "يبقى", "يفضل", "بتفضل", "يستقر", "byefdal"]) and _hits(local_mask, ["payment", "transaction", "refund", "stock", "inventory", "item", "product", "مخزون", "المخزن", "الصنف", "المنتج", "عملية", "معاملة", "استرداد"]) and not _hits(local_mask, ["funding", "deposit", "activation", "إيداع", "ايداع", "تفعيل", "تمويل", "eda3", "taf3eel"]):
            goals.pop("balance_treatment", None)
        additional, noncore_objects, noncore_context = _noncore_meanings(
            text, noncore_objects, local_mask, b < len(question) and question[b] in "?؟")
        if "reprint" in additional:
            goals.pop("documents", None)
        if additional and not hits.get("fee"):
            if set(additional) & {"transaction_status", "transaction_cancel", "repeat_payment"}:
                goals.pop("withdrawal_tariff", None)
                goals.pop("deposit_tariff", None)
            if set(additional) & {"reprint", "transaction_cancel", "refund", "refund_eligibility"}:
                goals.pop("workflow", None)
        goals.update(additional)
        record_fields=transaction_reference_spans(local_mask)
        if record_fields:
            goals.setdefault('transaction_reference',record_fields)
            payment_points=goals.get('payment',[])
            if payment_points and all(any(x<=a and b<=y for x,y in record_fields) for a,b in payment_points):
                goals.pop('payment')
            supplied_fields=valued_record_fields(text,record_fields,_raw_record_references(text))
            if supplied_fields and 'transaction_reference' in goals and len(goals)>1:
                points=goals['transaction_reference']
                if points and all(any(x<=a and b<=y for x,y in supplied_fields) for a,b in points):
                    goals.pop('transaction_reference')
        if not goals:
            nominal=catalog_nominal_proofs(local_mask,_nominal_catalog_rows())
            if hits.get('fee'):nominal.pop('withdrawal_minimum',None)
            goals.update(nominal)
        # Independently enumerate literal nominal catalog requests from the
        # original masked clause, never from the planner's committed list.
        for intent, points in nominal_catalog_heads(local_mask, _catalog_intent_ids()).items():
            goals.setdefault(intent, points)
        kept_goals = {}
        for intent, points in goals.items():
            if not temporal_scopes:
                kept_goals[intent] = points
                continue
            if not points:
                missing.append({'code':'raw_predicate_scope_unresolved','span':_mark(question,a,b,'requested_predicate')})
                continue
            outside = [point for point in points if not any(
                a + point[0] < q['event_span']['end'] and q['event_span']['start'] < a + point[1]
                for q in temporal_scopes)]
            if outside:
                kept_goals[intent] = outside
            else:
                context_only.append({'kind': 'temporal_condition_event',
                                     'span': _mark(question, a, b, 'condition_context')})
        goals = kept_goals
        if not goals and not local_services and nonrestrictive_scalar_focus(local_mask):
            context_only.append({'kind': 'nonrestrictive_scalar_modifier',
                                 'span': _mark(question,a,b,'response_scope_modifier')})
            continue
        if not goals and temporal_context_fragment(local_mask,a,temporal_scopes):
            context_only.append({'kind': 'temporal_condition_context',
                                 'span': _mark(question, a, b, 'condition_context')})
            continue
        resolved_services = _resolve_catalog_ambiguity(
            local_ambiguity, goals, definition, adapter, last_services or prior_services)
        if resolved_services:
            local_services = resolved_services
            resolved_ambiguity_bounds.update(
                (issue["span"]["start"], issue["span"]["end"]) for issue in local_ambiguity)
            local_ambiguity = []
        inherited_clause = None
        preamble = _correction_preamble(question, a, b, features) if not goals else None
        if preamble:
            context_only.append(preamble)
            continue
        if (not goals and demands and not local_services and re.search(
                r"\b(?:keep|retain|preserve)\b[^.;!?]{0,30}\b(?:same|that)\s+(?:requirement|condition|rule|topic)\b"
                r"|(?:خلي|احتفظ|حافظ)[^.;؟!?]{0,30}(?:نفس|ذات)\s+(?:الشرط|المتطلب|الموضوع)",
                local_mask, re.I)):
            context_only.append({"kind": "predicate_replacement_referent",
                                 "span": _mark(question, a, b, "context_only")})
            continue
        named_mask = list(local_mask)
        local_records = _raw_record_references(text)
        for record in local_records:
            start, end = record["span"]["start"], record["span"]["end"]
            named_mask[start:end] = " " * (end-start)
            record_references.append({**record, "span": _mark(question, a+start, a+end, "record_reference")})
        for x, y, _ in channel_hits:
            if a <= x < b:
                named_mask[x-a:y-a] = " " * (y-x)
        noncore_only = bool(goals) and set(goals) <= NONCORE_INTENTS
        early_envelope = _task_envelope_fragment(text, goals, local_services)
        unknown_subjects = _unknown_named_subject(
            "".join(named_mask), features, navigation_bounds) if (
                not local_services and not noncore_only and not early_envelope) else []
        excluded = _excluded_scope(text, hits, features)
        if contrast_excluded_channels and local_channels:
            # "ATM instead of the branch" excludes only the replaced channel,
            # not the operation in the same clause.
            excluded = False
        if excluded and not goals and local_services and _hits(text, [
                "leave out", "leave", "exclude", "excluding", "استبعد", "سيب", "اترك"]):
            inherited_exclusion = list(last_intents)
            if not inherited_exclusion:
                inherited_exclusion = _history_intents(prior, local_services, adapter)
            if not inherited_exclusion:
                inherited_exclusion = list(dict.fromkeys(
                    demand["intent_id"] for demand in demands
                    if demand["role"] == "requested"))
            if inherited_exclusion:
                goals = {intent: [(0, len(text))] for intent in inherited_exclusion}
        if (not excluded and _predicate_scope_restatement(text, goals)
                and any(d["role"] == "requested" and d["intent_id"] in goals
                        for d in demands)):
            context_only.append({"kind": "predicate_scope_restatement",
                                 "span": _mark(question, a, b, "response_constraint")})
            if local_services:
                last_services = local_services
            continue
        envelope = early_envelope or _task_envelope_fragment(text, goals, local_services)
        reported_task_continuation = any(start <= a and b <= end
                                         for start, end in reported_task_bounds)
        if reported_task_continuation and not claim_verification:
            envelope = envelope or "reported_task_claim"
        if envelope:
            if _numeric_response_layout(text):
                numeric_layout_groups.add(group)
            context_only.append({"kind": envelope, "verified": False,
                                 "span": _mark(question, a, b, "context_only")})
            envelope_navigation_services = list(dict.fromkeys(
                service for _, _, service, _ in navigation_hits))
            if envelope_navigation_services:
                last_services = envelope_navigation_services
                last_intents = ["workflow"]
            else:
                if local_services:
                    last_services = local_services
                if goals:
                    last_intents = list(goals)
                    if not local_services:
                        pending_intents = list(goals)
            if all_local_channels:
                last_channels = list(local_channels if contrast_excluded_channels else all_local_channels)
            continue
        if not goals and _numeric_response_layout(text):
            # A response-layout preamble can govern the immediately following
            # coordinated clauses in the same punctuation group.  It carries
            # no business predicate or provider by itself.
            numeric_layout_groups.add(group)
            context_only.append({"kind": "numeric_response_scope",
                                 "span": _mark(question, a, b, "response_constraint")})
            continue
        substitution, constraint = _raw_substitution_constraint(text, goals, demands, local_services or last_services, excluded)
        if substitution:
            if constraint:
                constraint["span"] = _mark(question, a, b, "response_constraint")
                constraint["operator_spans"] = [_mark(question, a+x, a+y, "constraint_operator") for x, y in constraint["operator_spans"]]
                structural_modifiers.append(constraint)
            else:
                missing.append({"code": "raw_substitution_scope_unresolved", "span": _mark(question, a, b, "response_constraint")})
            continue
        if not excluded and _raw_past_event_context(text, b < len(question) and question[b] in "?؟"):
            context_only.append({"kind": "reported_past_event", "verified": False, "span": _mark(question, a, b, "context_only")})
            continue
        if _reported_claim_fragment(text) and not claim_verification:
            context_only.append({"kind": "reported_claim", "verified": False,
                                 "span": _mark(question, a, b, "context_only")})
            if local_services:
                last_services = local_services
            continue
        quoted_context = any((start <= a and b <= end) or (a <= start and end <= b)
                             for start, end in quoted_bounds)
        if _reported_claim_preamble(text) or quoted_context:
            context_only.append({"kind": "reported_claim", "verified": False,
                                 "span": _mark(question, a, b, "context_only")})
            if local_services:
                last_services = local_services
            if not (quoted_context and claim_verification):
                continue
        if claim_verification and not goals and not quoted_context:
            # The current non-quoted clause is an instruction to verify the
            # predicates inside the quoted assertion.  It is response scope,
            # not another policy predicate that must independently map to a
            # business fact.  Quoted clauses are still parsed below and every
            # emitted fact remains subject to source/view eligibility.
            context_only.append({"kind": "claim_verification_reference",
                                 "span": _mark(question, a, b, "context_only")})
            if local_services:
                last_services = local_services
            continue
        if claim_verification and not goals and _hits(text, [
                "verify the claim", "verify those claims", "check the claim", "check those claims",
                "تحقق من الادعاء", "تحقق من هذين الادعاءين", "تحقق من الادعاءات"]):
            context_only.append({"kind": "claim_verification_reference",
                                 "span": _mark(question, a, b, "context_only")})
            continue
        if not goals and _excluded_quantity_fragment(text):
            context_only.append({"kind": "excluded_quantity_alternative",
                                 "span": _mark(question, a, b, "context_only")})
            continue
        if _response_scope_fragment(text) and (excluded or not goals or demands):
            context_only.append({"kind": "response_scope", "span": _mark(question, a, b, "context_only")})
            if local_services:
                last_services = local_services
            continue
        if not goals and excluded and _excluded_generic_fee_fragment(text, hits) and demands:
            context_only.append({"kind": "excluded_generic_fee_scope",
                                 "span": _mark(question, a, b, "context_only")})
            continue
        if excluded and _raw_unknown_negative_predicate(text):
            # Known response-scope verbs (omit/mention/discuss/etc.) were
            # consumed above.  An unknown negated verb remains unresolved
            # even when its object is a known topic; the object must not make
            # an invented operation silently disappear.
            missing.append({"code": "raw_predicate_unresolved", "span": _mark(question, a, b, "requested_predicate")})
            continue
        if not goals and _service_context_fragment(local_mask, local_services):
            context_only.append({"kind": "service_context", "span": _mark(question, a, b, "context_only")})
            last_services = local_services
            continue
        process_context = _process_context_fragment(text, goals, hits, question, features)
        if process_context:
            context_only.append({"kind": "process_context", "span": _mark(question, a, b, "context_only")})
            if local_services:
                last_services = local_services
            continue
        layout = _layout_modifier(local_mask) if not goals else None
        if layout:
            scoped_services = list(dict.fromkeys(pending_services + local_services))
            structural_modifiers.append({"kind": layout, "span": _mark(question,a,b,"response_constraint"),
                                         "group": group, "service_ids": scoped_services})
            pending_services = scoped_services
            if scoped_services:
                last_services = scoped_services
            continue
        if noncore_context and not goals and not excluded:
            context_only.append({"kind": "unverified_record_or_object_context", "verified": False,
                                 "span": _mark(question, a, b, "context_only")})
            continue
        attribute = _identity_modifier(local_mask) if not goals else None
        if attribute:
            attribute_modifiers.append({"attribute": attribute[0], "aliases": attribute[1],
                                        "span": _mark(question,a,b,"requested_attribute"),
                                        "group": group, "service_ids": local_services})
            continue
        if not goals and not addition_verbs and not local_channels and not excluded and not (
                inherited_intents and _hits(text, features.get("followup", []))) and (
                _scalar_fragment(local_mask) or _financial_modifier(local_mask, features)) and not (
                local_services and _service_list_fragment(local_mask, features)):
            scalar_modifiers.append({"span": _mark(question,a,b,"quantity_modifier"),
                                     "service_ids": local_services, "group": group})
            continue
        if not goals and not active_unsupported and local_services and not local_channels and _service_list_fragment(local_mask, features):
            # A provider-only coordinated tail can share the independently
            # established prior predicate, not its provider's facts.
            history_topics = _history_intents(prior, local_services, adapter)
            if history_topics and (_hits(text, features.get("followup", [])) or
                                   additive_provider_reference(question,[(x,y) for x,y,_ in entity_hits])):
                goals = {intent: [(0, len(text))] for intent in history_topics}
            elif pending_intents:
                goals = {intent: [(0, len(text))] for intent in pending_intents}
                pending_intents = []
            elif last_intents and demands and group == demands[-1]["group"]:
                goals = {intent: [(0, len(text))] for intent in last_intents}
                inherited_clause = demands[-1]
            else:
                pending_services.extend(s for s in local_services if s not in pending_services)
                continue
        if not goals and not active_unsupported and not addition_verbs and local_channels:
            if last_intents:
                goals = {i: [(0, len(text))] for i in last_intents}
            elif inherited_intents:
                goals = {i: [(0, len(text))] for i in inherited_intents}
        if not goals and "image_permission" in last_intents and hits.get("permission") and (
                _hits(text, ["it", "that", "دي", "ده"]) or
                re.search(r"(?:استخدام|استعمال|اعتماد)(?:ها|ه)", shadow(text)[0])):
            goals = {"image_permission": hits["permission"]}
        services = list(dict.fromkeys(pending_services + local_services))
        pending_services = []
        navigation_services = list(dict.fromkeys(service for _, _, service, _ in navigation_hits))
        if navigation_services and set(goals) & {"workflow", "branch_condition"}:
            services = navigation_services
        if local_ambiguity or unknown_subjects:
            services = []
            missing.append({"code": "raw_service_reference_ambiguous",
                            "span": _mark(question, a, b, "referent"),
                            "alternatives": sorted({sid for issue in local_ambiguity for sid in issue["alternatives"]}),
                            "unknown_named_subjects": unknown_subjects})
        elif not services and not active_unsupported:
            services = last_services
        distributive = _raw_distributive_subject_reference(text) if excluded and not local_services else None
        if distributive and not (local_ambiguity or unknown_subjects or active_unsupported):
            # Current raw entity spans are the only admissible antecedents.
            # A two-way pronoun cannot silently choose two of three providers.
            explicit = list(dict.fromkeys(s for _, _, s in entity_hits))
            if (distributive == "pair" and len(explicit) == 2) or (distributive == "all" and len(explicit) >= 2):
                services = explicit
        if not services and not active_unsupported and not local_ambiguity and not unknown_subjects:
            explicit = list(dict.fromkeys(s for _, _, s in entity_hits))
            if len(explicit) == 1:
                services = explicit
            elif comparative_reference:
                services = prior_services
            elif len(prior_services) == 1:
                services = prior_services
            elif prior_services:
                missing.append({"code": "raw_service_reference_ambiguous",
                                "alternatives": prior_services,
                                "span": _mark(question, a, b, "referent")})
        if objectless_addition and len(services) == 1 and not (local_ambiguity or unknown_subjects or active_unsupported):
            compatible = {"initial_funding", "balance_treatment"}
            parents = [d for d in demands if d["role"] == "requested" and d["service_id"] == services[0]
                       and d["intent_id"] in compatible]
            prior_financial = compatible & set(_history_intents(prior, services, adapter))
            if parents or prior_financial:
                if parents:
                    latest = max(d["clause_span"]["end"] for d in parents)
                    parents = [d for d in parents if d["clause_span"]["end"] == latest]
                    addition_antecedent = {"kind": "financial_subject", "request_ids": [d["request_id"] for d in parents],
                                           "clause_span": parents[0]["clause_span"], "service_id": services[0]}
                else:
                    addition_antecedent = {"kind": "financial_subject", "turn_id": prior.get("turn_id", prior.get("language_turn_id")),
                                           "intent_ids": sorted(prior_financial), "service_id": services[0]}
                bound_addition = sorted({point for row in objectless_addition for point in [row["action"]] + row["fee_question"]})
                goals["deposit_tariff"] = bound_addition
                hits["deposit"] = sorted(set(hits.get("deposit", []) + [row["action"] for row in objectless_addition]))
        current_inherited = _history_intents(prior, services or prior_services, adapter)
        referent = bool(_hits(text, features.get("followup", [])
                             + ["it", "there", "same one", "that one", "that sequence", "the sequence",
                                "source order", "registration order", "that field", "each route", "each channel",
                                "both routes", "both channels", "kol wa7da", "عليه", "هناك", "نفسه", "نفسها", "دي", "ده"]))
        inherited_referent_intents = current_inherited or last_intents
        if (not goals and not active_unsupported and not addition_verbs
                and inherited_referent_intents and (referent or local_channels)):
            goals = {i: [(0, len(text))] for i in inherited_referent_intents}
        if services and not excluded:
            last_services = services
        if goals and not excluded:
            last_intents = list(goals)
        if not goals:
            if text.strip() and (not local_services or not _hits(text, features.get("followup", []))):
                missing.append({"code": "raw_predicate_unresolved", "span": _mark(question, a, b, "requested_predicate")})
            continue
        if not services:
            services = [None]
        period, period_ambiguous = _condition_period(text)
        if period_ambiguous:
            missing.append({"code": "raw_period_binding_unresolved", "span": _mark(question, a, b, "condition")})
        for intent, proof in goals.items():
            intent_excluded = _intent_excluded(text, proof, excluded)
            local_entities = [(x-a, y-a, sid) for x, y, sid in entity_hits if a <= x < b]
            bound_services = (navigation_services if intent in {"workflow", "branch_condition"} and navigation_services else
                              [None] if local_ambiguity or unknown_subjects or active_unsupported else
                              _services_for_intent(intent, proof, local_entities, services,
                                                   hits, demands, group, text))
            for service in bound_services or [None]:
                if service is None and (intent in NONCORE_INTENTS or intent_excluded) and not (local_ambiguity or unknown_subjects or active_unsupported):
                    service = "unspecified_service"
                # A branch/app mention is context for permission, identity,
                # code or navigation. Tariff channels remain independent.
                channels = local_channels if intent in TARIFFS or adapter.get(intent,{}).get('channel_reference_group') else []
                if not channels and intent in TARIFFS and referent and last_channels:
                    channels = list(last_channels)
                if (not channels and intent in TARIFFS and inherited_clause is not None
                        and inherited_clause["intent_id"] == intent):
                    channels = list(inherited_clause["channels"])
                quoted_route=None
                if not intent_excluded and intent in TARIFFS and not channels:
                    quoted_route=quoted_channel_reference(question,_mark(question,a,b,'requested_predicate'),service,
                        features['deposit' if intent=='deposit_tariff' else 'withdrawal'],
                        [dict(_mark(question,x,y,'service'),service_id=s,entity_role=roles.get(s,'service'))
                         for x,y,s in entity_hits],
                        [dict(_mark(question,x,y,'channel'),channel=c) for x,y,c in channel_hits],
                        quoted_bounds,_channel_parents())
                    if quoted_route:
                        if not quoted_route['resolved']:
                            missing.append({'code':'raw_channel_ambiguous','service_id':service,
                                            'intent_id':intent,'span':quoted_route['reference_spans'][0],
                                            'alternatives':quoted_route['candidate_channels'],'reference':quoted_route})
                        else:channels=[quoted_route['channel']]
                condition_mask = list(local_mask)
                for x, y, _ in channel_hits:
                    if a <= x < b:
                        condition_mask[x-a:y-a] = " " * (y-x)
                channel_alternative = (intent in TARIFFS and len(all_local_channels) > 1
                                       and bool(re.search(r"(?:^|\s)لو\b.*(?:^|\s)و?لو\b|\bif\b.*\b(?:or|and)\b.*\bif\b",
                                                          shadow(text)[0], re.I)))
                explicit_channel_switch = bool(contrast_excluded_channels and intent in current_inherited)
                verifying_claim_clause = claim_verification and any(
                    start <= a and b <= end for start, end in quoted_bounds)
                literal_conditions = [] if (intent == "branch_condition" or channel_alternative
                                             or explicit_channel_switch or verifying_claim_clause) else _conditions(
                    text, "".join(condition_mask), features, bound_addition)
                if (quoted_route and quoted_route['resolved'] and quoted_route['claim_scope_requested']
                        and quoted_route['unverified_scope_spans']):
                    literal_conditions.append({'type':'user_condition','operator':'quoted_scope_requires_source_verification',
                        'value':'unverified quoted scope','source_spans':quoted_route['unverified_scope_spans'],
                        'claim_spans':[row['claim_span'] for row in quoted_route['antecedents']]})
                if not literal_conditions and _conditions(text) and not verifying_claim_clause:
                    context_only.append({"kind": "operation_scenario", "span": _mark(question, a, b, "context_only")})
                demand = {
                    "request_id": "Q" + str(len(demands) + 1),
                    "service_id": service, "intent_id": intent,
                    "topic": adapter.get(intent, {}).get("topic"),
                    "channels": list(dict.fromkeys(channels)), "conditions": literal_conditions, "period": period,
                    "procedure_scope": _workflow_scope(text, service, definition, adapter, features)
                                       if intent == "workflow" else None,
                    "role": "excluded" if intent_excluded else "requested",
                    "requested_facets": [] if intent_excluded else (
                        ["amount_only"] if intent == "initial_funding"
                        and group in numeric_layout_groups
                        else _requested_facets(text, intent,[(left,right) for left,right,_ in local_entities])),
                    "group": group,
                    "evidence_spans": [_mark(question, a+x, a+y,
                                             "scope_operator" if intent_excluded else
                                             "referent" if not hits.get("workflow") and proof == [(0, len(text))] else "requested_predicate")
                                       for x, y in proof],
                    "clause_span": _mark(question, a, b, "requested_predicate"),
                    "antecedent": {"turn_id": prior.get("turn_id", prior.get("language_turn_id")),
                                   "service_ids": services}
                                  if not local_services and not any(s == service for _, _, s in entity_hits) and prior_services else None,
                }
                if quoted_route:demand['quoted_channel_reference']=quoted_route
                if (proof == [(0,len(text))] and additive_provider_reference(
                        question,[(x,y) for x,y,_ in entity_hits])):
                    inherited_scope=antecedent_scope(prior,intent,service)
                    if inherited_scope is None:
                        missing.append({'code':'raw_request_scope_antecedent_ambiguous',
                                        'service_id':service,'intent_id':intent})
                    else:
                        demand.update(inherited_scope['scope'])
                        demand['antecedent']=inherited_scope
                if intent == "deposit_tariff" and addition_antecedent:
                    demand["object_antecedent"] = addition_antecedent
                    demand["commit_basis"] = "new_action_with_resolved_financial_object"
                if active_unsupported:
                    demand["unsupported_named_provider"] = [subject["text"] for subject in active_unsupported]
                    demand["unsupported_subject_spans"] = active_unsupported
                    demand["linguistic_only"] = True
                    demand["required_route"] = "source_evidence_required"
                if intent in NONCORE_INTENTS:
                    demand["linguistic_only"] = True
                    demand["required_route"] = "live_record_required" if intent in NONCORE_LIVE_INTENTS else "source_evidence_required"
                if intent == "workflow":
                    demand["channels"] = _navigation_channel(demand["procedure_scope"], service, definition, adapter)
                if service is None and not (local_ambiguity or unknown_subjects or active_unsupported) and _grammatical_subject_head(local_mask, features):
                    demand["deferred_service_head"] = True
                if service is None and not active_unsupported:
                    missing.append({"code": "raw_service_unresolved", "request_id": demand["request_id"]})
                if intent in {"identity", "documents"} and _hits(text, ["all", "complete", "every", "كل", "جميع", "كامل", "كافة"]):
                    demand["full_inventory"] = True
                if intent == "identity":
                    demand["requested_attributes"] = [name for name, aliases in IDENTITY_ATTRIBUTES.items()
                                                        if _hits(text, aliases)]
                demands.append(demand)
                if demand["role"] == "requested" and intent in TARIFFS and contrast_excluded_channels:
                    for excluded_channel in contrast_excluded_channels:
                        proof_spans = [(x, y) for x, y, channel in local_channel_spans
                                       if channel == excluded_channel]
                        demands.append({
                            **demand,
                            "request_id": "Q" + str(len(demands) + 1),
                            "role": "excluded",
                            "channels": [excluded_channel],
                            "conditions": [],
                            "evidence_spans": [_mark(question, a+x, a+y, "scope_operator")
                                               for x, y in proof_spans],
                            "channel_contrast_of": demand["request_id"],
                        })
        if all_local_channels:
            # Preserve the immediately preceding typed channel for an
            # elliptic price/percentage continuation in the same request.
            # This is not a cross-turn default and does not infer a channel
            # when more than one antecedent is present.
            last_channels = list(local_channels if contrast_excluded_channels else all_local_channels)
    explicit_pairs={(d.get("service_id"),d.get("request_id")) for d in demands
                    if d.get("role")=="requested" and any(
                        span.get("role")=="requested_predicate" for span in d.get("evidence_spans",[]))}
    demands=[d for d in demands if not (
        d.get("role")=="requested" and d.get("antecedent") and d.get("evidence_spans") and not d.get("channels")
        and all(span.get("role")=="referent" for span in d["evidence_spans"])
        and any(service==d.get("service_id") and request_id!=d.get("request_id")
                for service,request_id in explicit_pairs))]
    # Exclusion polarity carries across a simple coordinated list and stops
    # at punctuation or an explicit positive clause. This mirrors the typed
    # planner boundary while remaining an independent raw-question audit.
    moved=[]
    for demand in list(demands):
        if demand.get("role") != "requested":
            continue
        start=demand.get("clause_span",{}).get("start",0)
        parents=[row for row in demands if row.get("role")=="excluded"
                 and row.get("clause_span",{}).get("end",0) <= start]
        if not parents:
            continue
        parent=max(parents,key=lambda row:row["clause_span"]["end"])
        between=question[parent["clause_span"]["end"]:start]
        if re.fullmatch(r"\s*(?:and|or|و|أو)\s*",between,re.I) and not re.search(r"[.;!?؟؛]",between):
            demands.remove(demand)
            moved.append({**demand,"role":"excluded",
                          "clause_span":dict(demand["clause_span"],role="excluded"),
                          "commit_basis":"coordinated_exclusion_scope"})
    demands.extend(moved)
    projection_services=list(dict.fromkeys(
        [service for _,_,service in entity_hits]
        + (prior_services if len(prior_services)==1 else [])))
    projections=[project_procedure_members(question,service,definition) for service in projection_services]
    projections=[row for row in projections if row]
    if len(projections)==1:
        projection=projections[0];service=projection["service_id"]
        scope_span=projection["request_span"]
        if not projection_covers_span(question,scope_span,projection):
            missing.append({'code':'raw_procedure_scope_remainder_unresolved','service_id':service,
                            'span':dict(scope_span,role='unresolved_procedure_scope')})
        removed={d["request_id"] for d in demands
                 if projection_covers_span(question,d.get("clause_span"),projection)}
        demands=[d for d in demands if d["request_id"] not in removed]
        entry=adapter.get("workflow",{});contract=projection.get("procedure_contract")
        scope=next((name for name,values in entry.get("procedure_scope_bindings",{}).items()
                    if contract in values),contract)
        channels=[name for name,values in entry.get("procedure_channel_bindings",{}).items()
                  if contract in values]
        demands.append({
            "request_id":"Q"+str(len(demands)+1),"service_id":service,"intent_id":"workflow",
            "topic":entry.get("topic","workflow"),"channels":channels,"conditions":[],"period":None,
            "procedure_scope":scope,"procedure_member_ids":projection["fact_ids"],"role":"requested",
            "requested_facets":[],"group":group,
            "evidence_spans":[dict(span,role="requested_predicate") for span in projection["support_spans"]],
            "clause_span":dict(scope_span,role="requested_predicate"),
            "antecedent":{"turn_id":prior.get("turn_id",prior.get("language_turn_id")),"service_ids":[service]}
                         if service in prior_services else None,
        })
        missing=[row for row in missing if not (
            row.get("code") in {"raw_predicate_unresolved","raw_service_unresolved"}
            and (projection_covers_span(question,row.get("span"),projection)
                 or row.get("request_id") in removed))]
    generic_channel_aliases=[]
    for row in channel_table:
        if row.get("channel_id") == "other_unspecified":
            generic_channel_aliases.extend(alias for values in row.get("aliases", {}).values() for alias in values)
    generic_channel_spans=_hits(question,generic_channel_aliases)
    if generic_channel_spans and any(d["role"] == "requested" and d["intent_id"] in TARIFFS for d in demands):
        typed_bounds=[(a,b) for a,b,_ in channel_hits]
        for start,end in generic_channel_spans:
            if any(a <= start and end <= b for a,b,_ in all_entities):
                continue
            # Do not manufacture ambiguity for a generic word already bound
            # by a typed requested/excluded demand (for example "not the
            # branch" in a channel replacement).  A genuinely bare branch
            # tariff has no such binding and remains a clarification.
            containing=[d for d in demands if d.get("intent_id") in TARIFFS
                        and d.get("clause_span",{}).get("start",-1) <= start
                        and end <= d.get("clause_span",{}).get("end",-1)]
            # "app" and other placeholders outside a tariff clause are not
            # transaction channels.  A same-operation generic reference is
            # resolved only from one earlier typed request of that service.
            bound=any(d.get("role")=="excluded" and d.get("channels") for d in containing)
            local_text=question[max(0,start-8):min(len(question),end+8)]
            referential=bool(_hits(local_text,["the branch","الفرع","that branch","same branch","the same branch",
                                               "نفس الفرع","الفرع ده","الفرع دا"]))
            if containing and not bound and referential:
                for d in containing:
                    earlier={channel for row in demands
                             if row.get("role")=="requested"
                             and row.get("service_id")==d.get("service_id")
                             and row.get("intent_id")==d.get("intent_id")
                             and row.get("clause_span",{}).get("end",0) <= d.get("clause_span",{}).get("start",0)
                             for channel in row.get("channels",[])
                             if _channel_parents().get(channel)=="branch"}
                    if len(earlier)==1:
                        bound=True
                        break
            if containing and not bound and not any(a <= start and end <= b for a,b in typed_bounds):
                missing.append({"code":"raw_channel_ambiguous","alternatives":["provider_branch","fawry_plus","other_branch"],
                                "span":_mark(question,start,end,"channel")})
    if pending_services:
        missing.append({"code": "raw_predicate_unresolved", "service_ids": pending_services})
    # A later explicit amount-only instruction narrows an earlier broad
    # rendering of the same service/predicate. This is response scope, not an
    # additional request. It must not narrow another provider's clause.
    amount_only_pairs = {
        (d["service_id"], d["intent_id"])
        for d in demands if d["role"] == "requested"
        and "amount_only" in d.get("requested_facets", [])
    }
    if amount_only_pairs:
        demands = [d for d in demands if not (
            d["role"] == "requested"
            and (d["service_id"], d["intent_id"]) in amount_only_pairs
            and "amount_only" not in d.get("requested_facets", [])
            and any(n["clause_span"]["start"] >= d["clause_span"]["end"]
                    for n in demands
                    if n["role"] == "requested"
                    and (n["service_id"], n["intent_id"]) == (d["service_id"], d["intent_id"])
                    and "amount_only" in n.get("requested_facets", []))
        )]
    if resolved_ambiguity_bounds:
        issues = [issue for issue in issues
                  if not (issue.get("code") == "raw_entity_ambiguous"
                          and (issue["span"]["start"], issue["span"]["end"]) in resolved_ambiguity_bounds)]
    # A grammatical predicate head before an explicit coordinated provider
    # list can apply to each list member. An unknown name or substantive
    # leftover is never replaced by the known provider elsewhere in the turn.
    expanded = []
    resolved_deferred = set()
    for demand in demands:
        group_services = list(dict.fromkeys(d["service_id"] for d in demands
                                           if d["group"] == demand["group"] and d["service_id"] is not None))
        if demand.get("deferred_service_head") and group_services:
            resolved_deferred.add(demand["request_id"])
            for index, service in enumerate(group_services, 1):
                expanded.append({**demand, "request_id": demand["request_id"] + "." + str(index),
                                 "service_id": service, "bound_from_current_group": True})
        else:
            expanded.append(demand)
    demands = expanded
    missing = [issue for issue in missing if not (issue.get("code") == "raw_service_unresolved"
                                                and issue.get("request_id") in resolved_deferred)]
    for modifier in scalar_modifiers:
        peers = [d for d in demands if d["role"] == "requested"
                 and d["group"] == modifier["group"]
                 and d["intent_id"] in TARIFFS | {"initial_funding", "opening_fee"}
                 and (not modifier["service_ids"] or d["service_id"] in modifier["service_ids"])]
        if not peers and not modifier["service_ids"]:
            previous = [d for d in demands if d["role"] == "requested"
                        and d["intent_id"] in TARIFFS | {"initial_funding", "balance_treatment"}
                        and d["clause_span"]["end"] <= modifier["span"]["start"]]
            if previous:
                last_end = max(d["clause_span"]["end"] for d in previous)
                nearest = [d for d in previous if d["clause_span"]["end"] == last_end]
                if len({d["service_id"] for d in nearest}) == 1 and len({d["intent_id"] for d in nearest}) == 1:
                    peers = nearest
                    modifier["antecedent_clause"] = nearest[0]["clause_span"]
        modifier["bound_request_ids"] = [d["request_id"] for d in peers]
        fee_floor = bool(_hits(modifier["span"]["text"], [
            "minimum fee", "minimum charge", "minimum commission", "fee floor",
            "الحد الأدنى للعمولة", "الحد الادنى للعمولة", "أقل عمولة", "اقل عمولة",
        ]))
        if fee_floor:
            modifier["requested_attribute"] = "fee_floor"
            for demand in peers:
                marker = {"type": "requested_attribute", "name": "fee_floor"}
                if marker not in demand["conditions"]:
                    demand["conditions"].append(marker)
        if not peers:
            missing.append({"code": "raw_quantity_scope_unresolved", "span": modifier["span"]})
    for modifier in structural_modifiers:
        if modifier["kind"] == "predicate_separation":
            continue
        # A bare separator at the start of a new task introduces the following
        # request; it does not assert that two list members exist in that task.
        following = [d for d in demands if d["role"] == "requested"
                     and d["group"] == modifier["group"]
                     and d["clause_span"]["start"] >= modifier["span"]["end"]]
        preceding = [d for d in demands if d["role"] == "requested"
                     and d["group"] == modifier["group"]
                     and d["clause_span"]["end"] <= modifier["span"]["start"]]
        if (modifier["kind"] == "separate_scopes" and following and not preceding
                and set(tokens(modifier["span"]["text"])) <= {"separately", "individually"}):
            modifier["binding_kind"] = "following_independent_task"
            modifier["bound_request_ids"] = [d["request_id"] for d in following]
            continue
        peers = [d for d in demands if d["role"] == "requested"
                 and d["clause_span"]["end"] <= modifier["span"]["start"]
                 and (not modifier.get("service_ids") or d["service_id"] in modifier["service_ids"])]
        if not peers:
            peers = [d for d in demands if d["role"] == "requested"
                     and d["group"] == modifier["group"]
                     and d["clause_span"]["start"] >= modifier["span"]["end"]
                     and (not modifier.get("service_ids") or d["service_id"] in modifier["service_ids"])]
        strict_reference = modifier["kind"] == "tariff_reference"
        if strict_reference:
            peers = [d for d in peers if d["intent_id"] in TARIFFS]
        elif modifier["kind"] == "list_reference" and _hits(modifier["span"]["text"], ["other", "remaining", "باقي"]):
            referenced = {request_id for previous in structural_modifiers
                          if previous["kind"] == "tariff_reference" and previous["span"]["end"] <= modifier["span"]["start"]
                          for request_id in previous.get("bound_request_ids", [])}
            if referenced:
                peers = [d for d in peers if d["request_id"] not in referenced]
                strict_reference = True
        count = len({(d["service_id"], tuple(d.get("unsupported_named_provider", [])), d["intent_id"]) for d in peers})
        number_words = {word: value for value, word in enumerate(
            ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"])}
        number_words["both"] = 2
        quantities = [int(word) if word.isdigit() else number_words[word]
                      for word in tokens(modifier["span"]["text"])
                      if word.isdigit() or word in number_words]
        if count < (2 if modifier["kind"] == "separate_scopes" else 1) or any(
                quantity != count if strict_reference else quantity > count for quantity in quantities):
            missing.append({"code": "raw_list_reference_unresolved", "span": modifier["span"]})
        modifier["bound_request_ids"] = [d["request_id"] for d in peers]
    for modifier in attribute_modifiers:
        peers = [d for d in demands if d["role"] == "requested" and d["intent_id"] == "identity"
                 and d["group"] == modifier["group"]
                 and (not modifier["service_ids"] or d["service_id"] in modifier["service_ids"])]
        modifier["bound_request_ids"] = [d["request_id"] for d in peers]
        for demand in peers:
            selection = _select_for_raw_request(demand, facts, definition, adapter)
            if not any(_attribute_in_evidence(modifier["attribute"], facts[fid])
                       for fid in selection["eligible_fact_ids"]):
                missing.append({"code": "raw_identity_attribute_without_evidence",
                                "attribute": modifier["attribute"], "request_id": demand["request_id"]})
        if not peers:
            missing.append({"code": "raw_attribute_subject_unresolved", "span": modifier["span"]})
    # A single explicit channel may qualify coordinated same-service tariff
    # heads. Never propagate across a hard boundary or another provider.
    for d in demands:
        if d["role"] != "requested" or d["intent_id"] not in TARIFFS or d["channels"]:
            continue
        peers = [x for x in demands if x["role"] == "requested" and x["service_id"] == d["service_id"]
                 and x["group"] == d["group"] and x["intent_id"] == d["intent_id"]
                 and x["conditions"] == d["conditions"] and x["period"] == d["period"]]
        unique = set(c for x in peers for c in x["channels"])
        if unique:
            d["channels"] = sorted(unique)
        elif _hits(d["clause_span"]["text"], features.get("branch", []) + ["same channel", "that channel"]):
            # A generic branch is not Fawry Plus by default. It may refer to
            # exactly one earlier explicitly named compatible channel of this
            # same service and operation, including across sentence boundaries.
            branch_reference = bool(_hits(d["clause_span"]["text"], features.get("branch", [])))
            earlier = [p for p in demands if p["role"] == "requested"
                       and p["service_id"] == d["service_id"] and p["intent_id"] == d["intent_id"]
                       and p["clause_span"]["end"] <= d["clause_span"]["start"] and p["channels"]]
            candidates = {channel for p in earlier for channel in p["channels"]
                          if not branch_reference or _channel_parents().get(channel) == "branch"}
            if len(candidates) == 1:
                d["channels"] = sorted(candidates)
                d["channel_antecedent_request_ids"] = [p["request_id"] for p in earlier
                                                        if candidates & set(p["channels"])]
    for issue in bind_dimension_channel_references(question,demands,adapter):
        missing.append({'code':'raw_channel_reference_ambiguous',**issue})
    for modifier in [row for row in context_only if row.get('kind')=='nonrestrictive_scalar_modifier']:
        parents=[d for d in demands if d['role']=='requested' and d['intent_id'] in {'initial_funding','balance_treatment'}]
        if parents:
            distance=lambda d:max(0,modifier['span']['start']-d['clause_span']['end'],d['clause_span']['start']-modifier['span']['end'])
            nearest=min(distance(d) for d in parents)
            parents=[d for d in parents if distance(d)==nearest]
        if not parents:missing.append({'code':'raw_scope_reference_unresolved','span':modifier['span']})
        elif any('amount_only' in d.get('requested_facets',[]) for d in parents):
            missing.append({'code':'raw_answer_scope_conflict','span':modifier['span']})
    remaining_temporal = [q for q in temporal_scopes if not any(
        projection_covers_span(question, q['span'], projection) for projection in projections)]
    assignments, unbound_temporal = temporal_scope_bindings(remaining_temporal, demands)
    for index, qualifiers in assignments.items():
        demands[index]['conditions'].extend(temporal_condition(q) for q in qualifiers)
        for qualifier in qualifiers:
            if qualifier['event_missing']:
                missing.append({'code': 'raw_condition_operand_unresolved', 'span': qualifier['span']})
    missing.extend({'code': 'raw_condition_target_unresolved', 'span': q['span']} for q in unbound_temporal)
    excluded_ids = set()
    allowed = set()
    required = set()
    conflicts = []
    excluded_required_procedure = set()
    positive_projections = {}
    for demand in demands:
        if demand["role"] == "requested" and not demand.get("unsupported_named_provider"):
            projection = _select_for_raw_request(demand, facts, definition, adapter)
            for fid in projection["eligible_fact_ids"]:
                positive_projections.setdefault(fid, []).append(demand)
    for d in demands:
        if d["role"] == "excluded":
            for fid, f in facts.items():
                if f.get("service_id") != d["service_id"] or d["topic"] not in f.get("selection_tags", []):
                    continue
                if (d.get("intent_id") == "balance_treatment"
                        and f.get("scope", {}).get("balance_treatment") is None):
                    # A shared activation row that only states the amount is
                    # still usable for an explicit amount-only answer.
                    continue
                if not d["channels"] or f.get("required_channel") in d["channels"]:
                    if d.get('exclusion_scope_groups') is not None and any(
                        p.get('group') not in d['exclusion_scope_groups'] for p in positive_projections.get(fid,[])):
                        continue
                    # Excluding repetition of a complete ordered procedure
                    # does not forbid an independently requested narrow
                    # predicate of an atomic member (e.g. the visit trigger).
                    narrow_projection = (d["topic"] == "workflow" and f.get("atomic_group")
                                         and any(p.get("topic") != "workflow"
                                                 for p in positive_projections.get(fid, [])))
                    if not narrow_projection:
                        excluded_ids.add(fid)
                        for positive in positive_projections.get(fid, []):
                            if positive.get("topic") == "workflow" and f.get("atomic_group"):
                                excluded_required_procedure.add(fid)
                                conflicts.append({"code": "excluded_required_procedure_member",
                                                  "fact_id": fid,
                                                  "positive_request_id": positive["request_id"],
                                                  "excluded_request_id": d["request_id"]})
            continue
        if d.get("unsupported_named_provider"):
            d["required_fact_ids"] = []
            d["eligible_fact_ids"] = []
            missing.append({"request_id": d["request_id"], "code": "unsupported_named_provider_without_evidence",
                            "subjects": d["unsupported_named_provider"]})
            continue
        selection = _select_for_raw_request(d, facts, definition, adapter)
        d["required_fact_ids"] = selection["required_fact_ids"]
        d["eligible_fact_ids"] = selection["eligible_fact_ids"]
        required.update(selection["required_fact_ids"])
        allowed.update(selection["eligible_fact_ids"])
        conflicts.extend(selection["conflicts"])
        for attribute in d.get("requested_attributes", []):
            if not any(_attribute_in_evidence(attribute, facts[fid])
                       for fid in selection["eligible_fact_ids"]):
                missing.append({"code": "raw_identity_attribute_without_evidence",
                                "attribute": attribute, "request_id": d["request_id"]})
        for gap in selection["gaps"]:
            missing.append({"request_id": d["request_id"], **gap})
    # Channel-only exclusions remove the negative side from a positive shared
    # channel list. They cannot cancel another provider's requested channel.
    required -= excluded_ids - excluded_required_procedure
    allowed -= excluded_ids
    forbidden_emitted = emitted & excluded_ids
    missing_ids = required - emitted
    if missing_ids:
        missing.append({"code": "raw_requested_facts_missing", "fact_ids": sorted(missing_ids)})
    unrelated = emitted - allowed
    contract = actual.get("evidence_contract")
    convergence = _independent_fulfillment(demands, emitted, actual, facts, definition, adapter)
    can_converge = (convergence["verified"] and not missing and not issues and not conflicts
                    and not forbidden_emitted and not unrelated)
    if (not isinstance(contract, dict) or contract.get("complete") is not True) and not can_converge:
        issues.append({"code": "existing_evidence_contract_not_complete"})
    if forbidden_emitted:
        issues.append({"code": "raw_excluded_scope_emitted", "fact_ids": sorted(forbidden_emitted)})
    if unrelated:
        issues.append({"code": "raw_unrelated_fact_emitted", "fact_ids": sorted(unrelated)})
    if not demands:
        missing.append({"code": "no_raw_requested_meaning_established"})
    complete = bool(emitted) and not (missing or issues or conflicts)
    if complete:
        decision = "complete"
    elif emitted & allowed:
        decision = "supported_partial"
    elif conflicts:
        decision = "conflict"
    elif any(x.get("code", "").startswith("raw_") or x.get("code") == "no_raw_requested_meaning_established"
             for x in missing):
        decision = "clarify"
    elif any(d.get("required_route") == "live_record_required" for d in demands if d["role"] == "requested"):
        decision = "live_lookup_required"
    else:
        decision = "unsupported"
    for demand in demands:
        for s in demand["evidence_spans"] + [demand["clause_span"]]:
            if question[s["start"]:s["end"]] != s["text"]:
                raise ValueError("Independent raw span mismatch")
    return {
        "complete_eligible": complete, "missing_demands": missing,
        "excluded_fact_ids": sorted(forbidden_emitted),
        "unrelated_fact_ids": sorted(unrelated), "issues": issues,
        "raw_demands": demands, "decision": decision,
        "required_fact_ids": sorted(required), "conflicts": conflicts,
        "raw_quantity_modifiers": scalar_modifiers,
        "raw_context_only": context_only,
        "raw_structural_modifiers": structural_modifiers,
        "raw_attribute_modifiers": attribute_modifiers,
        "raw_record_references": record_references,
        "unsupported_named_subjects": unsupported_subjects,
        "independent_fulfillment": convergence,
        "fulfillment_convergence_applied": bool(can_converge and
                                                (not isinstance(contract, dict)
                                                 or contract.get("complete") is not True)),
        "semantic_independence_claimed": False,
        "independence_scope": "Separate original-clause demand enumeration; does not read planner requests or use its predicate function. Shared lexical resources can still omit unfamiliar meaning.",
        "source_freshness_and_view_approval_required_separately": True,
    }
