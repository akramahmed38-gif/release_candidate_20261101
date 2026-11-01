"""Language-only operation/object/dimension frames with original Unicode spans.

This module does not read evidence, fact IDs, expected questions, approvals or
business policies.  A recognized intent is a linguistic proposal, never proof
that the named action is possible or that a source-backed answer exists.
"""
import re

from linguistic_spans import mark, spans, tokens, shadow


# Atomic vocabulary complements the authored multiword intent cues.  These are
# language components, not service rules or complete question patterns.
ATOMS = {
    "wallet_balance": ["balance", "رصيد", "الرصيد", "raseed"],
    "balance_bound": ["minimum", "maximum", "ceiling", "floor", "الحد الأدنى", "الحد الادنى", "الحد الأقصى", "أقل", "أكبر", "minimum", "maximum", "a2al", "akbar"],
    "ongoing_balance": ["ongoing", "permanent", "always", "maintain", "must keep", "مستمر", "دائم", "دايما", "لازم أسيب", "dayman"],
    "complaint": ["complaint", "ticket", "شكوى", "شكوتي", "الشكوى", "shakwa", "shakwety"],
    "issue": ["issue", "problem", "المشكلة", "مشكله", "moshkela"],
    "refund": ["refund", "الاسترداد", "استرداد", "رد المبلغ", "رجوع الفلوس", "استرجاع المبلغ", "esterdad"],
    "transaction": ["transaction", "payment", "transfer", "عملية", "العملية", "معاملة", "المعاملة", "سداد", "الدفع", "3amaleya", "payment", "daf3a"],
    "item": ["item", "product", "goods", "size", "physical", "الصنف", "صنف", "المنتج", "منتج", "سلعة", "بضاعة", "senf", "montag", "beda3a"],
    "stock": ["stock", "inventory", "warehouse", "المخزن", "المخزون", "مخزون", "المستودع", "stock", "ma5zan"],
    "receipt": ["receipt", "slip", "coupon", "إيصال", "الإيصال", "كوبون", "الكوبون", "وصل", "wesl", "coupon"],
    "cash_drawer": ["till", "cash drawer", "الخزينة", "درج الصراف", "النقدية", "khazna"],
    "status": ["status", "state", "progress", "update", "pending", "reached", "arrived", "received", "already", "حالة", "وصل", "وصلت", "وصل لفين", "معلقة", "تمت", "نجحت", "وصلت لفين", "mawgood", "wesel", "weslet", "pending"],
    "resolution": ["resolved", "fixed", "resolution", "اتحلت", "حلت", "حل الشكوى", "et7alet", "el 7al"],
    "closure_state": ["closed", "closure", "اتقفلت", "أغلقت", "et2afalet"],
    "acknowledgment": ["acknowledged", "acknowledgment", "reply sent", "response sent", "رد اتبعت", "رد اتبعت", "رد وصل", "wesel el rad"],
    "count": ["count", "quantity", "units", "stocktake", "عدد", "العدد", "الكمية", "كمية", "جرد", "نعد", "تعداد", "gard", "kemeya", "ne3ed"],
    "available": ["available", "availability", "in stock", "موجود", "متاح", "توافر", "متوفر", "mawgood", "available"],
    "eligibility": ["eligible", "eligibility", "qualifying", "qualify", "allowed", "conditions", "rules", "policy", "أهلية", "استحقاق", "شروط", "قواعد", "سياسة", "مسموح", "ينفع", "shoroot", "yenfa3"],
    "cancel": ["cancel", "cancelling", "canceled", "cancelled", "void", "stop", "ألغي", "الغي", "إلغاء", "وقف", "اتلغت", "الغيت", "elghy", "etlaghet", "wa2af"],
    "return": ["return", "returning", "send back", "إرجاع", "أرجع", "ارجع", "مرتجع", "رد سلعة", "araga3", "mortaga3"],
    "reprint": ["reprint", "reprinting", "duplicate", "طباعة", "أطبع", "اطبع", "atba3"],
    "draft": ["draft", "phrase", "word", "wording", "reply", "respond", "explanation", "صياغة", "صغ", "صيغلي", "أقول", "اقول", "أرد", "ارد", "رد", "seghly", "a2ool", "ard"],
    "draft_request": ["help me", "draft", "phrase", "what should I tell", "how should I reply", "صيغلي", "صغ", "أقول للعميل", "أرد عليه", "a2ool", "seghly", "ard 3aleh"],
    "callback": ["callback", "call me", "call me back", "contact me", "يكلموني", "كلموني", "يكلمني", "يرن عليا", "معاودة الاتصال", "yekalemny", "kallemony", "yerenn 3alaya"],
    "employee": ["employee", "agent", "colleague", "الموظف", "موظف", "employee", "mowazaf"],
    "create": ["create", "make", "open", "raise", "lodge", "log", "تقديم", "أقدم", "اقدم", "فتح", "سجل", "عمل", "اعمل", "تعمل", "efta7", "a2adem"],
    "closure": ["close", "closing", "closure", "إغلاق", "اغلاق", "إقفال", "اقفال", "اقفل", "قفل"],
    "wallet": ["wallet", "account", "محفظة", "حساب", "ma7faza"],
    "transfer_operation": ["transfer", "تحويل", "حول", "حوّل", "7awel", "t7awel"],
    "monetary_value": ["value", "amount", "money", "funds", "cash", "قيمة", "مبلغ", "أموال", "اموال", "فلوس", "نقود", "floos"],
    "retention": ["keep", "kept", "retain", "retained", "remain", "stay", "يحتفظ", "تحتفظ", "محفوظ", "محتفظ", "يبقى", "تبقى", "يفضل", "بتفضل", "يستقر", "تستقر", "byefdal", "yefdal", "stay"],
    "balance_object": ["balance", "رصيد", "الرصيد", "raseed"],
    "new": ["new", "جديدة", "جديد", "new"],
    "procedure": ["procedure", "instructions", "steps", "explain", "how", "طريقة", "خطوات", "إجراءات", "اشرح", "ازاي", "كيفية", "steps", "ezay"],
    "action": ["do", "perform", "execute", "now", "immediately", "حالاً", "حالا", "دلوقتي", "اعمل", "نفذ", "5ally", "خلي", "فورا", "سجل"],
    "question": ["is", "has", "was", "whether", "can", "what", "where", "هل", "إيه", "ايه", "فين", "emta", "fein", "wala la"],
    "verify": ["verify", "check", "correct", "true", "right", "accurate",
               "تحقق", "تحقّق", "راجع", "صحح", "صحّح", "صحيح", "صح",
               "حقيقة", "صحة", "kalam sa7", "sa7"],
    "permission": ["may I", "allowed", "permitted", "can I use", "هل يجوز", "ينفع", "يجوز", "مسموح", "أقدر أستخدم", "اقدر استخدم", "yenfa3", "masmoo7"],
    "preserve": ["preserve", "preserving", "retain", "keep", "including", "include", "مع الحفاظ", "إبقاء", "ابقاء", "حافظ", "مع توضيح", "موضحا", "وضح", "ما تنساش", "matensash"],
    "condition": ["condition", "conditional", "when", "point at which", "شرط", "حالة", "امتى", "متى", "توقيت", "الحالة", "وقت", "emta"],
    "branch": ["branch", "فرع", "الفرع", "فرعية", "far3"],
    "workflow": ["workflow", "navigation", "procedure", "steps", "walk me through", "خطوات", "خطوة خطوة", "الإجراءات", "التسلسل", "khatwa khatwa", "steps"],
    "promise": ["promise", "promising", "guarantee", "commitment", "وعد", "ضمان", "التزام", "wa3d", "me3ad"],
    "negative": ["not", "no", "never", "do not", "without", "مش", "ما", "لا", "ليس", "دون", "بلا", "غير", "mesh", "msh", "mat", "men gheir", "mat7awelsh"],
    "desired_time": ["before", "after", "by", "tomorrow", "today", "بعد", "قبل", "بكرة", "النهاردة", "غدا", "ba3d", "abl", "bokra", "elnaharda"],
    "reported": ["customer says", "customer said", "customer claims", "according to the customer", "I heard", "العميل بيقول", "العميل قال", "عميل بيقول", "قال العميل", "يقول العميل", "يذكر العميل", "el 3ameel bey2ool"],
    "customer": ["customer", "العميل", "عميل", "الزبون", "el 3ameel"],
    "display_event": ["showed", "sent", "brought", "showing", "بعث", "بعت", "أرسل", "ارسل", "وراني", "عرض", "جاب", "ba3at", "ba3atly", "warany"],
    "image": ["image", "picture", "photo", "photograph", "screenshot", "صورة", "صور", "سكرين", "لقطة", "sora", "screenshot"],
}


def _uniq(values):
    return list(dict.fromkeys(values))


def _hits(raw, phrases):
    pairs = {pair for phrase in phrases if isinstance(phrase, str)
             for pair in spans(raw, phrase)}
    # A feminine noun changes ta-marbuta to ta before a pronoun: حالة → حالتها.
    # This is a bounded morphological relation, not fuzzy semantic matching.
    feminine = {token for phrase in phrases if isinstance(phrase, str)
                for token in tokens(phrase) if len(tokens(phrase)) == 1 and token.endswith("ه")}
    if feminine:
        for word in re.finditer(r'[\u0621-\u064a][\u0621-\u064a\u064b-\u065f\u0670]*', raw):
            normalized = tokens(word.group())
            if not normalized:
                continue
            for suffix in ["ها", "هم", "هن", "ه", "ك", "كم", "نا"]:
                if normalized[0].endswith(suffix):
                    stem = normalized[0][:-len(suffix)]
                    if stem.endswith("ت") and stem[:-1] + "ه" in feminine:
                        pairs.add((word.start(), word.end()))
    return sorted(pairs)


def _negative_operation_forms(raw):
    """Return current negative verb spans with catalog-independent polarity."""
    result = []
    for match in re.finditer(r'(?<!\w)ma([a-z0-9]{3,})sh(?!\w)', raw, re.I):
        result.append((match.start(), match.end(), match.group(1).casefold()))
    for word in re.finditer(r'[\u0621-\u064a][\u0621-\u064a\u064b-\u065f\u0670]*', raw):
        parsed = tokens(word.group())
        if not parsed or not parsed[0].endswith("ش"):
            continue
        value = parsed[0][:-1]
        previous = tokens(raw[max(0, word.start()-8):word.start()])
        if previous and previous[-1] == "ما":
            result.append((word.start(), word.end(), value))
        if value.startswith("ما") and len(value) > 4:
            result.append((word.start(), word.end(), value[2:]))
        elif value.startswith("م") and len(value) > 4:
            result.append((word.start(), word.end(), value[1:]))
    return list(dict.fromkeys(result))


def _past_cancel_questions(raw):
    """Locate interrogative cancelled-state predicates, not imperatives.

    English past auxiliaries and explicit Arabic interrogatives are grammar;
    the same participle in a declaration or a relative clause cannot authorize
    an action.  The caller retains independent imperative clauses separately.
    """
    states = []
    for sentence in re.finditer(r'[^.;!?؟؛]+[?؟]?', raw):
        clause = sentence.group()
        words = tokens(clause)
        if not words:
            continue
        interrogative = (words[0] in {"was", "were", "has", "have", "had", "is", "are", "هل"}
                         or bool(_hits(clause, ["whether"]))
                         or clause.rstrip().endswith(("?", "؟")))
        if not interrogative:
            continue
        for a, b in _hits(clause, ["cancelled", "canceled", "voided", "stopped", "اتلغت", "ألغيت", "الغيت"]):
            # A lexical imperative "cancel" does not appear in this list.
            # Require a finite question cue before the past state predicate.
            if _hits(clause[:a], ["was", "were", "has", "have", "had", "is", "are", "been", "whether", "هل"]):
                states.append((sentence.start() + a, sentence.start() + b))
    return sorted(set(states))


def _financial_addition(raw):
    """Compose an addition verb with its explicit money object, not amount.

    Egyptian person/tense affixes belong to the verb. They do not make a bare
    increase, a stock increase, or an increased fee into a cash-in operation.
    The caller supplies entity/report-masked text and retains original offsets.
    """
    normalized, positions = shadow(raw)
    actions = []
    money = []
    # Past/imperative suffixes and present/future person prefixes are bounded
    # morphology of زود, rather than a list of complete question variants.
    arabic_action = re.compile(
        r'(?:و|ف)?(?:(?:[اهحبتين]|ب[اتين]|[هح][اتين]?)?زود(?:ت|تي|نا|تم|تو|وا|ي|ون)?)\Z')
    money_noun = re.compile(r'(?:ال)?(?:فلوس|اموال|نقود|مال)(?:ي|ك|ه|ها|نا|كم|هم|هن)?\Z')
    english_actions = {
        "add", "adds", "added", "adding", "increase", "increases", "increased", "increasing",
        "top-up", "top-ups", "topped-up", "topping-up",
    }
    for word in re.finditer(r"[a-z]+(?:-[a-z]+)*|[\u0621-\u064a]+", normalized):
        value = word.group()
        point = (positions[word.start()], positions[word.end() - 1] + 1)
        if arabic_action.fullmatch(value) or value in english_actions:
            actions.append(point)
        if money_noun.fullmatch(value) or value in {"money", "fund", "funds", "cash"}:
            money.append(point)
    actions += _hits(raw, ["top up", "tops up", "topped up", "topping up"])
    filler = {"the", "some", "more", "extra", "additional", "my", "your", "his", "her", "our", "their",
              "customer's", "a", "bit", "of", "شويه", "كمان", "اكتر", "زياده", "بعض", "المزيد", "من"}
    proof = []
    for a, b in actions:
        for x, y in money:
            middle = raw[b:x]
            if (b <= x <= b + 50 and not re.search(r'[.;!?؟؛,،\n]', middle)
                    and set(tokens(middle)) <= filler):
                proof.extend([(a, b), (x, y)])
    return sorted(set(actions)), _uniq(proof)


def _addition_charge_dimension(raw, addition):
    """Bind a finite charge consequence to a following price/rate question."""
    normalized, coordinates = shadow(raw)
    charge_heads = []
    dimensions = []
    for match in re.finditer(
            r'(?<!\w)(?:بيتاخد|بتتاخد|بيتخصم|بيخصم|بيكلف|بتكلف|charges?|charged|costs?)(?!\w)', normalized):
        a, b = coordinates[match.start()], coordinates[match.end() - 1] + 1
        prior = [end for _, end in addition if end <= a]
        if not prior or re.search(r'[.;!?؟؛]', raw[max(prior):a]):
            continue
        stop = re.search(r'[.;!?؟؛]', raw[b:])
        end = b + stop.start() if stop else len(raw)
        interrogatives = _hits(raw[b:end], ["كام", "بكام", "قد ايه", "how much", "what percentage", "which rate", "ايه النسبة"])
        if interrogatives:
            charge_heads.append((a, b))
            dimensions.extend([(a, b)] + [(b + x, b + y) for x, y in interrogatives])
    # A nominal price question puts its interrogative before the price head:
    # "what is the charge?" The intervening words are grammar, not another
    # operation or an amount/customer restriction.
    links = {"is", "are", "the", "a", "my", "your", "its", "this", "that", "it", "هو", "هي"}
    for a, b in _hits(raw, ["charge", "cost", "fee", "tariff", "رسوم", "عمولة", "تكلفة", "مصاريف"]):
        prior = [end for _, end in addition if end <= a]
        if not prior or re.search(r'[.;!?؟؛]', raw[max(prior):a]):
            continue
        offset = max(prior)
        for x, y in _hits(raw[offset:a], ["what", "which", "how much", "ايه", "كام", "بكام", "قد ايه"]):
            start, end = offset + x, offset + y
            if set(tokens(raw[end:a])) <= links:
                charge_heads.append((a, b))
                dimensions.extend([(a, b), (start, end)])
    return _uniq(charge_heads), _uniq(dimensions)


def _balance_retention(raw, hits, features):
    """Recognize a retention predicate whose destination is a balance."""
    funding = _hits(raw, ["funding", "deposit", "activation", "إيداع", "ايداع", "تفعيل", "تمويل", "eda3", "taf3eel"])
    if (hits["stock"] or hits["item"] or hits["transaction"] or hits["refund"]) and not funding:
        return []
    functional = {"in", "into", "within", "the", "a", "my", "your", "his", "her", "their", "our",
                  "customer", "customer's", "customers", "wallet", "account", "it", "that", "amount", "money", "funding",
                  "في", "داخل", "ضمن", "ب", "العميل", "المبلغ", "الفلوس", "به", "بها", "الحساب", "حساب", "محفظه", "المحفظه"}
    proof = []
    for a, b in hits["retention"]:
        for x, y in hits["balance_object"]:
            if x < b or x - b > 75 or re.search(r'[.;!?؟؛,،]', raw[b:x]):
                continue
            between = tokens(raw[b:x])
            destination = any(word in {"in", "into", "within", "في", "داخل", "ضمن"} for word in between)
            balance_words = tokens(raw[x:y])
            destination |= bool(balance_words and balance_words[0] in {"بالرصيد", "برصيد"})
            if destination and set(between) <= functional:
                proof.extend([(a, b), (x, y)])
    return _uniq(proof)


def _catalog_rows(value, key):
    if isinstance(value, dict):
        value = value.get(key, list(value.values()))
    return [row for row in value or [] if isinstance(row, dict)]


def _span_union(raw, points, role):
    points = list(points)
    if not points:
        return None
    return mark(raw, min(a for a, _ in points), max(b for _, b in points), role)


def _negative_predicate_groups(raw, predicates, negatives):
    """Bind polarity locally; a later independent command is not proof.

    Normal noun coordination stays inside the clause ("no X or Y promise").
    Punctuation and a contrast/new-command connector bound each predicate's
    governing negative rather than unioning all negative words in the turn.
    """
    boundaries = list(re.finditer(
        r'[;؛.!?؟\n]|\b(?:but|rather than|and then)\b|(?:ولكن|بل|ثم)(?=\s)',
        raw, re.I))
    groups = []
    for a, b in predicates:
        left = max([m.end() for m in boundaries if m.end() <= a] + [0])
        right = min([m.start() for m in boundaries if m.start() >= b] + [len(raw)])
        local = [(x, y) for x, y in negatives if left <= x and y <= right]
        if not local:
            continue
        preceding = [(x, y) for x, y in local if x <= a]
        negative = max(preceding, key=lambda pair: pair[0]) if preceding else min(local)
        group = sorted(set([negative, (a, b)]))
        if group not in groups:
            groups.append(group)
    return groups


def _bind_dimension(hits, dimension, object_keys, raw=None):
    """Attach a dimension head to its uniquely nearest explicit object family."""
    bound = {key: [] for key in object_keys}
    objects = [(key, (a + b) / 2) for key in object_keys for a, b in hits.get(key, [])]
    for a, b in hits.get(dimension, []):
        if not objects:
            continue
        # A directly governed complement ("qualifying for a refund") is more
        # informative than distance to the object of a preceding conjunction.
        if raw is not None:
            following = [(x - b, key) for key in object_keys for x, _ in hits.get(key, [])
                         if b <= x <= b + 24 and set(tokens(raw[b:x])) <= {
                             "for", "a", "an", "the", "of", "ل", "عن", "في", "علي"}]
            if following:
                distance = min(d for d, _ in following)
                keys = {key for d, key in following if d == distance}
                if len(keys) == 1:
                    bound[next(iter(keys))].append((a, b))
                    continue
        center = (a + b) / 2
        distances = [(abs(center - obj_center), key) for key, obj_center in objects]
        nearest_distance = min(distance for distance, _ in distances)
        nearest_keys = {key for distance, key in distances if distance == nearest_distance}
        if len(nearest_keys) == 1:
            bound[next(iter(nearest_keys))].append((a, b))
    return bound


def annotate_operators(raw, operators):
    """Match authored operator forms; return canonical IDs and literal spans.

    `meaning` is the catalog's canonical operator name.  Its interpretation
    rule remains a separate field; example scope is never imported.
    """
    result = []
    for row in _catalog_rows(operators, "operators"):
        forms = row.get("forms", {})
        phrases = [phrase for values in forms.values() for phrase in values]
        for a, b in _hits(raw, phrases):
            result.append({"operator_id": row["operator_id"],
                           "name": row.get("name"),
                           "meaning": row.get("name"),
                           "interpretation_rule": row.get("interpretation_rule"),
                           "span": mark(raw, a, b, "operator"),
                           "basis": "current_authored_operator_form"})
    return sorted(result, key=lambda row: (row["span"]["start"], row["operator_id"]))


def _speech(raw, atoms):
    """Bound user reports at punctuation or the outer employee request."""
    quote_envelopes = [mark(raw, m.start(), m.end(), "claim_envelope")
              for m in re.finditer(r'"[^"\n]+"|“[^”\n]+”|«[^»\n]+»|‘[^’\n]+’|\u2018[^\u2019\n]+\u2019', raw)]
    quotes = [mark(raw, q["start"] + 1, q["end"] - 1, "claim") for q in quote_envelopes]
    claims = [{"source": "user_quoted_claim", "verified": False,
               "verified_business_fact": False,
               "speaker_role": "reported_customer", "span": quote,
               "envelope": envelope} for quote, envelope in zip(quotes, quote_envelopes)]
    outer = _hits(raw, ["help me", "please explain", "explain", "هل", "can you", "what should", "how should", "صيغلي", "اشرح", "أقول", "اقول"])
    for a, b in atoms["reported"]:
        if any(q["start"] <= a < q["end"] for q in quote_envelopes):
            continue
        following_quote = next((q for q in quote_envelopes if q["start"] >= b
                                and not raw[b:q["start"]].strip(' ,:؛،')), None)
        if following_quote:
            continue
        # A postfix attribution governs the preceding proposition, not the
        # instructions that follow it in the next sentence.
        if spans(raw[a:b], "according to the customer"):
            left = max([0] + [m.end() for m in re.finditer(r'[.;!?؟؛]', raw[:a])])
            right = a
        else:
            left = b
            tails = [m.start() + b for m in re.finditer(r'[.;!?؟؛]', raw[b:])]
            tails += [x for x, _ in outer if x >= b]
            right = min(tails or [len(raw)])
        while left < right and raw[left].isspace():
            left += 1
        while right > left and raw[right - 1] in ' ,،:':
            right -= 1
        if right > left:
            claims.append({"source": "reported_customer_claim", "verified": False,
                           "verified_business_fact": False,
                           "speaker_role": "reported_customer",
                           "span": mark(raw, left, right, "claim")})
    # A user's declarative report of a previous request or administrative state
    # remains unverified even without an explicit "customer said" introducer.
    # These forms describe past events; they do not execute the event or prove
    # successful processing/resolution.
    event_cues = _hits(raw, ["was requested", "has been requested", "had requested",
                            "was marked closed", "is closed", "بقى closed", "اتقفلت"])
    object_points = atoms["refund"] + atoms["complaint"]
    for a, b in event_cues:
        left = max([0] + [m.end() for m in re.finditer(r'[.;!?؟؛]', raw[:a])])
        right_match = re.search(r'[.;!?؟؛,،]', raw[b:])
        right = b + right_match.start() if right_match else len(raw)
        if not any(left <= x < right for x, _ in object_points):
            continue
        if any(c["span"]["start"] <= a < c["span"]["end"] for c in claims):
            continue
        # Questions about an event must not be reclassified as assertions.
        prefix = raw[left:a]
        if _hits(prefix, ["has", "had", "is", "was", "whether", "هل"]):
            continue
        while left < right and raw[left].isspace():
            left += 1
        claims.append({"source": "reported_prior_event", "verified": False,
                       "verified_business_fact": False,
                       "speaker_role": "reporting_user",
                       "span": mark(raw, left, right, "claim")})
    return claims


def _numeric_claim_components(raw, reports):
    """Separate reported values from source evidence and eligibility conditions."""
    components = []
    pattern = re.compile(r'(?<![\w.])(?:[0-9٠-٩]+(?:[.,٫][0-9٠-٩]+)?)\s*(?:[%٪]|EGP\b|جنيه(?:ا|اً)?\b|pounds?\b)', re.I)
    for report in reports:
        a, b = report["span"]["start"], report["span"]["end"]
        for match in pattern.finditer(raw, a, b):
            value = match.group()
            is_rate = bool(re.search(r'[%٪]', value))
            before = raw[max(a, match.start() - 30):match.start()]
            floor = bool(_hits(before, ["minimum", "fee floor", "حد أدنى", "حد ادنى", "بحد أدنى", "بحد ادنى", "أقل رسوم", "a2al rosoom"]))
            components.append({"source": report["source"], "speaker_role": report["speaker_role"],
                               "verified": False, "verified_business_fact": False,
                               "claim_type": "rate" if is_rate else "fee_floor" if floor else "monetary_amount",
                               "span": mark(raw, match.start(), match.end(), "claim"),
                               "parent_assertion_span": report["span"]})
    return components


def infer_clause(text, masked, features, intent_catalog, operators):
    """Propose typed current-clause meanings, without deciding answerability.

    `masked` must retain original Unicode length.  The caller owns service,
    channel, condition and discourse binding.  All offsets returned are local
    to `text`; caller adds the enclosing clause offset exactly once.
    """
    if not isinstance(masked, str) or len(text) != len(masked):
        raise ValueError("The clause mask must preserve original Unicode length")
    ids = {row.get("intent_id") for row in _catalog_rows(intent_catalog, "intents")}
    atoms = {key: _hits(text, values) for key, values in ATOMS.items()}
    reports = _speech(text, atoms)
    work = list(masked)
    for claim in reports:
        envelope = claim.get("envelope", claim["span"])
        for index in range(envelope["start"], envelope["end"]):
            work[index] = " "
    work = "".join(work)
    h = {key: _hits(work, values) for key, values in ATOMS.items()}
    negative_verbs = _negative_operation_forms(work)
    for a, b, stem in negative_verbs:
        for key in ["create", "cancel", "transfer_operation", "closure", "return"]:
            if any(set(tokens(stem)) & set(tokens(cue)) for cue in ATOMS[key] if len(tokens(cue)) == 1):
                h[key] = _uniq(h[key] + [(a, b)])
                h["negative"] = _uniq(h["negative"] + [(a, b)])
    # Common process nouns are also catalog aliases.  Entity masking may hide
    # them, but a current status/action dimension still needs its explicit
    # linguistic object.  Restoring only object anchors does not restore quoted
    # imperatives, decide a provider or create any business evidence.
    quoted_ranges = [(r["envelope"]["start"], r["envelope"]["end"]) for r in reports if r.get("envelope")]
    for key in ["complaint", "issue", "refund", "transaction", "item", "stock", "receipt", "cash_drawer"]:
        h[key] = [p for p in atoms[key] if not any(a <= p[0] < b for a, b in quoted_ranges)]
    for key, feature in [("workflow", "workflow"), ("permission", "permission"), ("branch", "branch")]:
        h[key] = _uniq(h[key] + _hits(work, features.get(feature, [])))
    components = _numeric_claim_components(text, reports)
    replaced = {(c["parent_assertion_span"]["start"], c["parent_assertion_span"]["end"]) for c in components}
    claims = components + [c for c in reports if (c["span"]["start"], c["span"]["end"]) not in replaced]
    # The dimensions of one object may not cross into a second operation merely
    # because both are mentioned in the current clause.
    for obj, points in _bind_dimension(h, "status", ["complaint", "refund", "transaction"], text).items():
        h[obj + "_status_dimension"] = points
    if h["transaction"]:
        h["transaction_status_dimension"] = _uniq(h["transaction_status_dimension"] + _past_cancel_questions(work))
    h["identity_object"] = _hits(work, features.get("identity", []))
    for obj, points in _bind_dimension(h, "eligibility", ["refund", "item", "identity_object", "transaction"], text).items():
        h[obj + "_eligibility_dimension"] = points
    has = lambda key: bool(h.get(key))
    goals, subsumed, suppressions, obligations, actors, context = [], [], [], [], [], []
    unbound_financial = []
    modes = {}
    annotations = annotate_operators(text, operators)
    operator_rows = {row.get("operator_id"): row for row in _catalog_rows(operators, "operators")}

    def annotation(iid, points, reason):
        row = operator_rows.get(iid)
        span = _span_union(text, points, "operator")
        if row and span:
            annotations.append({"operator_id": iid, "name": row.get("name"),
                                "meaning": row.get("name"),
                                "interpretation_rule": row.get("interpretation_rule"),
                                "span": span, "basis": reason})

    def add(iid, keys, mode="information", domain=None):
        if iid not in ids:
            return
        points = _uniq(point for key in keys for point in h.get(key, []))
        if not points:
            return
        existing = next((goal for goal in goals if goal["intent_id"] == iid), None)
        if existing:
            existing["predicate_spans"] = _uniq(existing["predicate_spans"] + points)
            return
        goal = {"intent_id": iid, "predicate_spans": points,
                "head_spans": h.get(keys[0], points),
                "support_features": ["semantic_atom:" + key for key in keys],
                "commit_basis": "current_operation_object_dimension", "mode": mode}
        if domain:
            goal["domain_id"] = domain
        goals.append(goal)
        modes[iid] = mode

    def suppress(iid, keys, reason):
        points = _uniq(point for key in keys for point in h.get(key, []))
        if points:
            subsumed.append(iid)
            suppressions.append({"intent_id": iid, "spans": points, "reason": reason})

    addition_actions, addition = _financial_addition(work)
    h["addition_action"] = addition_actions
    if addition:
        h["financial_addition_relation"] = addition
        charge_heads, charge_dimension = _addition_charge_dimension(work, addition)
        h["tariff_charge_head"] = charge_heads
        h["financial_charge_dimension"] = charge_dimension
        if charge_heads:
            suppress("balance_treatment", ["tariff_charge_head"], "cash_in_charge_question_is_not_balance_disposition")
            suppress("initial_funding", ["tariff_charge_head"], "cash_in_charge_question_is_not_initial_funding")
        funding_context = _hits(work, features.get("initial", []) + features.get("activation", []) + [
            "initial", "first funding", "first deposit", "اول مرة", "activate", "activation", "تفعيل",
        ])
        incompatible = any(_hits(work, features.get(key, []))
                           for key in ["workflow", "image", "code"])
        disposition = _hits(work, features.get("balance_disposition", []))
        incompatible |= any(not any(a < y and x < b for x, y in charge_heads) for a, b in disposition)
        if not funding_context and not incompatible:
            add("deposit_tariff", ["financial_addition_relation", "financial_charge_dimension"])
    elif addition_actions:
        # Older lexical cues include bare زودت and top up. Only their local
        # heads are suppressed; an independent explicit deposit head survives.
        typed_cues = [point for phrase in features.get("deposit", [])
                      if set(tokens(phrase)) & {"رصيد", "الرصيد", "balance", "wallet", "account"}
                      for point in _hits(work, [phrase])]
        legacy_topups = _hits(work, ["top up", "tops up", "topped up", "topping up",
                                    "top-up", "top-ups", "topped-up", "topping-up"])
        competing_objects = _hits(work, ["stock", "inventory", "item", "product", "fee", "charge", "amount",
                                         "مخزون", "رسوم", "مبلغ", "بضاعة", "كمية"])
        determiners = {"the", "a", "an", "my", "your", "some", "more", "extra", "additional", "arbitrary"}
        typed_cues += [point for point in legacy_topups
                       if not any(point[1] <= a <= point[1] + 40
                                  and set(tokens(work[point[1]:a])) <= determiners
                                  for a, _ in competing_objects)]
        h["untyped_addition_action"] = [point for point in addition_actions
                                        if not any(a <= point[0] and point[1] <= b for a, b in typed_cues)]
        suppress("deposit_tariff", ["untyped_addition_action"], "addition_without_explicit_money_object")
        funding_context = _hits(work, features.get("initial", []) + features.get("activation", []) + [
            "initial", "first funding", "first deposit", "اول مرة", "activate", "activation", "تفعيل",
        ])
        incompatible = any(_hits(work, features.get(key, [])) for key in ["workflow", "image", "code"])
        if not funding_context and not incompatible:
            for action in h["untyped_addition_action"]:
                charge_heads, question_points = _addition_charge_dimension(work, [action])
                if not charge_heads:
                    continue
                consequence_start = min(a for a, _ in charge_heads)
                objects = [point for point in competing_objects
                           if point[0] < consequence_start]
                # An explicit contradictory object cannot be replaced by an
                # antecedent. The finite charge head itself is a dimension.
                if objects:
                    continue
                h["unbound_tariff_charge_head"] = charge_heads
                suppress("balance_treatment", ["unbound_tariff_charge_head"], "objectless_addition_fee_dimension_is_not_balance_disposition")
                suppress("initial_funding", ["unbound_tariff_charge_head"], "objectless_addition_fee_dimension_is_not_initial_funding")
                unbound_financial.append({
                    "dimension": "financial_addition", "intent_id": "deposit_tariff",
                    "object_family": "financial_subject",
                    "compatible_antecedent_intents": ["initial_funding", "balance_treatment"],
                    "action_spans": [action], "fee_question_spans": question_points,
                    "spans": _uniq([action] + question_points),
                })

    retention = _balance_retention(work, h, features)
    if retention:
        h["balance_retention_relation"] = retention
        add("balance_treatment", ["balance_retention_relation"])
    elif h["retention"] and (h["stock"] or h["item"] or h["transaction"] or h["refund"]) and not _hits(work, ["funding", "deposit", "activation", "إيداع", "ايداع", "تفعيل", "تمويل", "eda3", "taf3eel"]):
        suppress("balance_treatment", ["retention", "balance_object"], "nonfunding_object_retention_is_not_initial_deposit_disposition")
        suppress("initial_funding", ["retention", "balance_object"], "nonfunding_object_retention_is_not_initial_deposit_disposition")

    # A customer's quoted imperative is context.  Drafting/coaching is the
    # employee's outer request and cannot authorize the quoted operation.
    if has("wallet_balance") and has("balance_bound") and has("ongoing_balance") and not (has("stock") or has("item") or has("cash_drawer")):
        add("balance_limit", ["wallet_balance", "balance_bound", "ongoing_balance"], "policy_query")
        h["post_activation_context"] = _hits(work, ["after activation", "after activating", "once activated", "بعد التفعيل", "بعد تفعيل المحفظة"])
        suppress("initial_funding", ["post_activation_context"], "post_activation_is_ongoing_policy_context_not_new_funding")
    drafting = has("draft_request") and has("draft")
    if drafting:
        add("response_draft", ["draft_request", "draft"], domain="customer_care")
        annotation("O35", h["draft_request"], "outer_employee_drafting_request")
        for constraint in _negative_predicate_groups(work, h["promise"], h["negative"]):
            obligations.append({"kind": "response_constraint", "value": "no_unverified_promise",
                                "span": _span_union(text, constraint, "constraint")})
            annotation("O45", constraint, "no_promise_drafting_constraint")

    if has("complaint") or has("issue") and has("resolution"):
        if has("resolution") and (has("question") or has("closure_state") or has("acknowledgment")):
            add("complaint_resolution_confirmation", ["complaint", "issue", "resolution"], "ask_status", "customer_care")
            suppress("complaint_status", ["complaint", "closure_state"], "resolution_is_distinct_from_administrative_status")
            annotation("O38", h["closure_state"] + h["resolution"], "closure_resolution_contrast")
        elif has("complaint_status_dimension") or has("closure_state"):
            add("complaint_status", ["complaint", "complaint_status_dimension", "closure_state"], "ask_status", "customer_care")
        elif has("create"):
            add("complaint_create", ["complaint", "create"], "action_request_or_capability", "customer_care")

    if has("refund") and not drafting:
        # Existing-progress dimensions outrank the generic refund noun.  A
        # separate eligibility clause remains separately representable.
        if has("refund_status_dimension"):
            add("refund_status", ["refund", "refund_status_dimension"], "ask_status", "unspecified_service")
            suppress("refund", ["refund", "refund_status_dimension"], "refund_progress_is_not_refund_execution")
        elif has("refund_eligibility_dimension"):
            add("refund_eligibility", ["refund", "refund_eligibility_dimension"], "policy_query", "retail_operations" if has("item") else None)
            suppress("refund", ["refund", "refund_eligibility_dimension"], "refund_eligibility_is_not_execution")
        elif has("action"):
            add("refund", ["refund", "action"], "action_request_or_capability")
            annotation("O37", h["refund"] + h["action"], "explicit_refund_action_versus_description")
        elif has("procedure"):
            add("refund", ["refund", "procedure"], "procedure_query")

    if has("transaction") and not drafting:
        # Tense/state is an independent requested attribute.  A past cancel
        # participle does not instruct the assistant to cancel an operation.
        status_question = has("transaction_status_dimension") and (has("question") or not has("action"))
        if status_question:
            add("transaction_status", ["transaction", "transaction_status_dimension", "cancel"], "ask_status")
            suppress("payment", ["transaction", "transaction_status_dimension"], "transaction_state_is_not_payment_execution")
            if has("cancel"):
                annotation("O37", h["cancel"] + h["status"], "cancel_state_versus_cancel_action")
        elif has("cancel"):
            add("transaction_cancel", ["cancel", "transaction"], "action_request_or_capability")
            suppress("payment", ["transaction", "cancel"], "cancellation_is_not_new_payment")
            annotation("O37", h["cancel"], "explicit_cancel_operation")

    if has("item") or has("stock"):
        if has("count"):
            add("inventory_count", ["count", "item", "stock"], domain="retail_operations")
            suppress("balance_treatment", ["count", "item", "stock"], "physical_units_are_not_wallet_money")
        elif has("available"):
            add("stock_availability", ["stock", "item", "available"], "ask_status", "retail_operations")
            suppress("balance_treatment", ["stock", "item", "available"], "physical_availability_is_not_wallet_balance")
        if has("return"):
            add("product_return", ["return", "item"], "policy_query" if has("eligibility") else "procedure_query", "retail_operations")
        annotation("O42", h["item"] + h["stock"], "physical_object_dimension")

    if has("cash_drawer") and (has("monetary_value") or has("count")):
        add("cash_reconciliation", ["cash_drawer", "monetary_value", "count"], domain="branch_operations")
        annotation("O42", h["cash_drawer"] + h["monetary_value"], "physical_cash_not_retail_stock")
    if has("wallet") and has("closure"):
        add("closure", ["closure", "wallet"], "action_request_or_capability" if has("action") else "information")
    if has("transfer_operation") and (has("monetary_value") or has("wallet")) and not drafting:
        add("transfer", ["transfer_operation", "monetary_value", "wallet"], "action_request_or_capability")

    if has("receipt") and has("reprint"):
        add("reprint", ["reprint", "receipt"], "procedure_query", "pos")
        suppress("documents", ["receipt", "reprint"], "receipt_reprinting_is_not_identity_document_inventory")
        suppress("payment", ["receipt", "reprint"], "existing_receipt_reprint_is_not_new_payment")

    if has("callback") and not drafting:
        add("callback", ["callback"], "action_request_or_capability", "customer_care")
        if has("desired_time"):
            obligations.append({"kind": "customer_desired_time", "confirmed": False,
                                "span": _span_union(text, h["desired_time"], "customer_preference")})
            annotation("O40", h["desired_time"], "desired_time_is_not_confirmed_appointment")

    # Source-condition preservation is an obligation of the requested workflow,
    # not a second request for a partial procedure.  Standalone branch questions
    # do not enter this branch.
    if has("workflow") and has("preserve") and has("branch") and has("condition"):
        obligations.append({"kind": "preserve_source_condition", "parent_intent": "workflow",
                            "condition_type": "branch_visit_condition",
                            "span": _span_union(text, h["preserve"] + h["condition"] + h["branch"], "obligation")})
        suppress("branch_condition", ["branch", "condition"], "workflow_condition_preservation_modifier")

    verification = None
    if has("verify") and (reports or atoms["reported"]):
        subject_keys = {
            "opening_fee": ["opening"], "deposit_tariff": ["deposit"],
            "withdrawal_tariff": ["withdrawal"], "initial_funding": ["initial", "activation"],
            "balance_treatment": ["balance_disposition"], "identity": ["identity"],
            "phone_ownership": ["phone_owner"], "existing_wallet": ["existing_wallet"],
        }
        for intent, keys in subject_keys.items():
            phrases = [phrase for key in keys for phrase in features.get(key, [])]
            if any(_hits(text[claim["span"]["start"]:claim["span"]["end"]], phrases) for claim in reports):
                modes[intent] = "verify_claim"
        verification = {"mode": "verify_claim", "span": _span_union(text, h["verify"], "verification_request"),
                        "claim_spans": [claim["span"] for claim in claims],
                        "bound_intents": [intent for intent, mode in modes.items() if mode == "verify_claim"]}
        annotation("O24", h["verify"], "verify_reported_proposition")
    if has("permission"):
        for intent in ["image_permission", "existing_wallet"]:
            modes[intent] = "permission"

    # Explicitly reported display events are contextual, not permission queries.
    # Suppression is span-scoped so a later permission request survives.
    if atoms["customer"] and atoms["display_event"] and atoms["image"]:
        for event_a, event_b in atoms["display_event"]:
            left = max([0] + [m.end() for m in re.finditer(r'[.;!?؟؛,،]', text[:event_a])])
            stop = re.search(r'[.;!?؟؛]', text[event_b:])
            right = event_b + stop.start() if stop else len(text)
            people = [p for p in atoms["customer"] if left <= p[0] < right]
            images = [p for p in atoms["image"] if event_a <= p[0] < right]
            if not people or not images:
                continue
            event_span = mark(text, min(a for a, _ in people), right, "context_only")
            actors.append({"actor": "reported_customer", "event": "display_or_supply_image",
                           "span": event_span, "verified": False})
            context.append({"feature": "reported_display_event", "span": event_span})
            # The later employee question is deliberately outside this span.
            event_questions = [p for p in h["permission"] + h["question"] if event_span["start"] <= p[0] < right]
            if not event_questions:
                subsumed.append("image_permission")
                suppressions.append({"intent_id": "image_permission", "spans": images,
                                     "reason": "reported_image_event_without_employee_permission_request"})

    references = []
    for match in re.finditer(r'(?<![\w-])[A-Za-z]{1,12}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-])', text):
        # Natural compounds (cash-in, sign-up, source-bound, end-to-end) are
        # language, not record identifiers.  A literal identifier must contain
        # a digit; never fabricate a reference from a hyphen alone.
        if not any(char.isdigit() for char in match.group()):
            continue
        object_points = [(key, point) for key in ["complaint", "refund", "transaction"] for point in atoms[key]]
        distances = [(min(abs(match.start() - b), abs(a - match.end())), key) for key, (a, b) in object_points]
        nearest = min(distances)[1] if distances else "unresolved_record"
        references.append({"kind": "record_identifier", "record_type": nearest,
                           "value": match.group(), "verified": False,
                           "span": mark(text, match.start(), match.end(), "record_reference")})
        annotation("O41", [(match.start(), match.end())], "literal_record_object_binding")

    for claim in reports:
        actors.append({"actor": claim["speaker_role"], "event": "reported_assertion",
                       "span": claim["span"], "verified": False})
        annotation("O14", [(claim["span"]["start"], claim["span"]["end"])],
                   "current_bounded_reported_assertion")
    for claim in components:
        if claim["claim_type"] == "fee_floor":
            annotation("O27", [(claim["span"]["start"], claim["span"]["end"])],
                       "reported_topic_specific_monetary_minimum")
    context_heads = _hits(work, features.get("registration_context", []))
    context_markers = _hits(work, features.get("context_start", []) + ["during", "while", "for registration", "wa2t", "اثناء", "أثناء"])
    if context_heads and context_markers:
        annotation("O13", context_heads + context_markers, "current_process_context_frame")
    exclusion_markers = _hits(work, ["not asking", "do not perform", "do not explain", "leave out", "rather than",
                                    "not a", "not about", "مش مجرد", "مش عايز", "ما تعملش", "لا أسأل", "لا أريد", "لا احتاج", "ليس", "وليس", "من غير ما", "mesh basa2al", "mat7awelsh"])
    if exclusion_markers:
        annotation("O01", exclusion_markers, "current_explicit_scope_exclusion_marker")
    if negative_verbs:
        annotation("O01", [(a, b) for a, b, _ in negative_verbs], "current_discontinuous_negative_operation")
    additive = _hits(work, features.get("additive_negation", []))
    if additive:
        annotation("O04", additive, "current_additive_negation_retains_both_requested_scopes")
    ordinary_additive = _hits(work, ["and", "also", "alongside", "as well as", "كمان", "أيضا", "ايضا", "we", "w"])
    if ordinary_additive:
        annotation("O08", ordinary_additive, "current_explicit_additive_connector")
    if has("transaction_status_dimension") or has("refund_status_dimension"):
        annotation("O37", h["transaction_status_dimension"] + h["refund_status_dimension"],
                   "requested_existing_operation_state")
    # Preserve canonical IDs and all actual spans; merge only exact duplicates.
    annotations = list({(row["operator_id"], row["span"]["start"], row["span"]["end"]): row
                        for row in annotations}.values())
    return {"supplemental_goals": goals, "subsumed_core_intents": _uniq(subsumed),
            "subsumption_spans": suppressions, "mode_by_intent": modes,
            "actor_frames": actors, "user_claims": claims,
            "context_mentions": context, "obligations": obligations,
            "references": references, "operator_annotations": annotations,
            "claim_verification": verification, "reported_assertions": reports,
            "unbound_dimensions": unbound_financial + [{"dimension": dimension, "spans": h[dimension]}
                                   for dimension in ["status", "eligibility", "cancel", "return", "resolution"]
                                   if h[dimension] and not any(h[key] for key in ["complaint", "refund", "transaction", "item", "stock", "receipt", "issue"])]}
