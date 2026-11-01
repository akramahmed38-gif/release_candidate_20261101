"""Source-metadata projection for a single member of an ordered procedure.

This module never contains a question, case ID, service name, expected fact ID,
or answer text.  It derives navigation labels and sequence relations from the
current registered facts.  The caller remains responsible for source/view
eligibility and citations.
"""
from __future__ import annotations

import re

from linguistic_spans import shadow, spans, tokens


def projection_covers_span(question, span, projection):
    """Certify only sequence grammar and registered labels in this fragment."""
    scope = projection["request_span"]
    if not isinstance(span, dict) or span.get("start", -1) < scope["start"]:
        return False
    start, end = span["start"], span["end"]
    continuation = end > scope["end"]
    if continuation and (start < scope["end"] or tokens(question[scope["end"]:start])):
        return False
    chars = list(question[start:end])
    for point in projection.get("context_spans", []) + projection["support_spans"]:
        left, right = max(start, point["start"]), min(end, point["end"])
        if left < right:
            chars[left-start:right-start] = " " * (right-left)
    grammar = {
        "in", "the", "a", "an", "app", "journey", "path", "route", "navigation",
        "what", "comes", "immediately", "after", "before", "next", "step", "steps",
        "item", "items", "only", "that", "this", "intervening", "answer", "give",
        "show", "provide", "please", "and", "then", "for", "of", "to", "first",
        "i", "we", "have", "has", "is", "are", "already", "reached", "selected", "entered", "opened", "menu",
        "choosing", "selecting", "entering", "following", "opening",
        "one", "two", "three", "four", "five", "six",
        "في", "مسار", "بعد", "اختيار", "قبل", "ما", "الخطوة", "التالية", "فقط",
        "ثم", "اول", "الاول", "خطوة", "خطوتين", "ثلاث", "ثلاثة", "اربع", "اربعة", "خمس", "ست",
        "اذكر", "اعرض", "وضح", "اشرح", "من", "بدء", "الاستثمار", "داخل", "خطوات",
        "فتح", "مباشرة", "أدخل", "ادخل", "فين", "أين", "واحدة", "واحده", "بس",
    }
    grammar = set(tokens(" ".join(grammar)))
    words = tokens("".join(chars))
    if continuation:
        imperative=bool({"answer", "show", "give", "provide"} & set(words)
                        and {"step", "steps", "item", "items"} & set(words))
        unit_words=set(tokens('step item خطوة'))
        single_words=set(tokens('one 1 واحدة واحده only فقط بس'))
        single_modifier=bool(set(words)&unit_words and set(words)&set(tokens('one 1 واحدة واحده'))
                             and set(words)<=unit_words|single_words and len(projection['fact_ids'])==1)
        if not (imperative or single_modifier):return False
    return all(word in grammar or word.isdigit() for word in words)


def _aliases(fact):
    values = []
    english = str(fact.get("english", "")).strip(" .")
    arabic = str(fact.get("arabic", "")).strip(" .")
    if english:
        values.append(english)
        # Registered camel-case application labels remain atomic even when
        # the surrounding source-view noun (such as "app") is omitted.
        values.extend(re.findall(r"\b[A-Z][a-z]+[A-Z][A-Za-z]*\b", english))
        match = re.match(r"^(Open|Enter|Select|Follow|Visit)\s+(?:the\s+)?(.+)$", english, re.I)
        if match:
            verb, tail = match.groups()
            tail = re.split(r"\s+when\s+", tail, maxsplit=1, flags=re.I)[0].strip(" .")
            values.append(tail)
            variants = {
                "open": "opening", "enter": "entering", "select": "choosing",
                "follow": "following", "visit": "visiting",
            }
            values.append(variants[verb.casefold()] + " the " + tail)
    if arabic:
        values.append(arabic)
        tail = re.sub(r"^(?:و?ثم\s+|و?يتم\s+|و?زيارة\s+|الدخول\s+إلى\s+|فتح\s+|اتباع\s+)", "", arabic).strip(" .")
        tail = re.split(r"\s+عند\s+", tail, maxsplit=1)[0].strip(" .")
        if tail:
            values.append(tail)
    return sorted({value for value in values if len(value.strip()) >= 4}, key=len, reverse=True)


def project_procedure_members(question, service_id, definition):
    """Return a uniquely source-derived narrow sequence projection or None."""
    groups = {}
    for fact in definition.get("facts", []):
        if (fact.get("service_id") != service_id or not fact.get("atomic_group")
                or not isinstance(fact.get("sequence_order"), int)
                or "workflow" not in fact.get("selection_tags", [])):
            continue
        groups.setdefault(fact["atomic_group"], []).append(fact)
    normalized, original_positions = shadow(question)
    direct_successor = bool(re.search(r'(?<!\w)بعد(?!\w)',normalized)
                            and re.search(r'(?<!\w)مباشره(?!\w)',normalized)
                            and re.search(r'(?<!\w)(?:ادخل|فين|اين)(?!\w)',normalized)
                            and re.search(r'(?<!\w)خطوه\s+واحده(?!\w)',normalized))
    next_marker = direct_successor or bool(re.search(
        r"\b(?:immediately\s+after|what\s+comes\s+after|next\s+(?:menu\s+)?(?:step|item|action))\b"
        r"|(?:بعد\s+اختيار|بعدها|الخطوة\s+التالية|ما\s+الخطوة\s+التالية)", normalized, re.I))
    before_marker = bool(re.search(r"\bbefore\b|(?:قبل|وقبل)", normalized, re.I))
    first_count = None
    first_match = re.search(
        r"\bfirst\s+(one|two|three|four|five|six|[1-6])\s+(?:steps?|items?)\b"
        r"|(?:أول|اول)\s+(?:ال)?(خطوة|خطوتين|ثلاث|ثلاثة|أربع|اربعة|خمس|ست)\b",
        normalized, re.I)
    if first_match:
        token = next(value for value in first_match.groups() if value)
        counts = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                  "خطوة": 1, "خطوتين": 2, "ثلاث": 3, "ثلاثة": 3,
                  "أربع": 4, "اربعة": 4, "خمس": 5, "ست": 6}
        first_count = int(token) if token.isdigit() else counts.get(token.casefold(), counts.get(token))
    narrow = bool(first_count) or next_marker or before_marker and bool(re.search(r"\bafter\b|بعد", normalized, re.I))
    if not narrow:
        return None
    marker = first_match or re.search(
        r"\b(?:immediately\s+after|what\s+comes\s+after|next\s+(?:menu\s+)?(?:step|item|action)|after)\b"
        r"|(?:بعد\s+اختيار|بعدها|الخطوة\s+التالية|ما\s+الخطوة\s+التالية|بعد)", normalized, re.I)
    if marker is None:
        return None
    # Regex operators live in normalized coordinates; all source, entity and
    # clause spans below live in original Unicode coordinates.
    marker_start = original_positions[marker.start()]
    marker_end = original_positions[marker.end()-1] + 1
    # Projection owns only the clause containing its sequence operator. It
    # cannot clear another service's unresolved request or replace its facts.
    boundaries = list(re.finditer(r"[;؛.!?؟]", question))
    scope_start = max([0] + [match.end() for match in boundaries if match.end() <= marker_start])
    scope_end = min([len(question)] + [match.start() for match in boundaries if match.start() >= marker_end])
    label_bounds = [(start, end) for facts in groups.values() for fact in facts
                    for alias in _aliases(fact) for start, end in spans(question, alias)]
    # A completed source-labelled position can be the antecedent of the next
    # sentence's sequence question. It must name this same service and contain
    # no other provider. Never search arbitrary earlier paragraphs or sessions.
    antecedent_span = None
    if next_marker and not any(scope_start <= start and end <= scope_end for start,end in label_bounds):
        prior_boundary = next((m for m in boundaries if m.end()==scope_start),None)
        previous_start=max([0]+[m.end() for m in boundaries if m.end()<scope_start])
        state=question[previous_start:scope_start]
        state_normalized=shadow(state)[0]
        completed=bool(re.search(r'\b(?:i|we)\s+(?:have\s+)?(?:reached|selected|entered|opened)\b',state_normalized,re.I))
        named_services=set()
        for named_service,profile in definition.get('service_profiles',{}).items():
            for alias in [profile.get('name','')]+profile.get('aliases',[]):
                if alias and spans(state,alias):named_services.add(named_service)
        if (prior_boundary and prior_boundary.group()=='.' and completed
                and named_services=={service_id}
                and any(previous_start<=start and end<=scope_start for start,end in label_bounds)):
            antecedent_span={'start':previous_start,'end':scope_start,'text':state,'role':'user_sequence_position'}
            scope_start=previous_start
    named = []
    service_context = []
    for named_service, profile in definition.get("service_profiles", {}).items():
        for alias in [profile.get("name", "")] + profile.get("aliases", []):
            if not alias:
                continue
            for start, end in spans(question, alias):
                if scope_start <= start and end <= scope_end:
                    if any(left <= start and end <= right for left, right in label_bounds):
                        continue
                    distance = max(0, marker_start - end, start - marker_end)
                    named.append((distance, named_service))
                    if named_service == service_id:
                        service_context.append({"start": start, "end": end})
    if named:
        nearest = min(distance for distance, _ in named)
        subjects = {name for distance, name in named if distance == nearest}
        if subjects != {service_id}:
            return None
    projections = []
    for group, facts in groups.items():
        hits = []
        for fact in facts:
            for alias in _aliases(fact):
                for start, end in spans(question, alias):
                    if scope_start <= start and end <= scope_end:
                        hits.append((start, end, fact))
        # One fact can match both its full view and a derived label.
        by_id = {}
        for start, end, fact in hits:
            current = by_id.get(fact["fact_id"])
            if current is None or end - start > current[1] - current[0]:
                by_id[fact["fact_id"]] = (start, end, fact)
        hits = sorted(by_id.values())
        if first_count:
            selected = [fact for fact in facts if fact["sequence_order"] <= first_count]
        elif before_marker and len(hits) >= 2:
            orders = sorted({fact["sequence_order"] for _, _, fact in hits})
            selected = [fact for fact in facts if orders[0] < fact["sequence_order"] < orders[-1]]
        elif next_marker and len({fact['sequence_order'] for _,_,fact in hits})==1:
            anchor = hits[0][2]
            selected = [fact for fact in facts if fact["sequence_order"] == anchor["sequence_order"] + 1]
        else:
            selected = []
        if selected:
            projections.append({
                "service_id": service_id,
                "atomic_group": group,
                "procedure_contract": selected[0].get("procedure_contract"),
                "request_span": {"start": scope_start, "end": scope_end,
                                 "text": question[scope_start:scope_end]},
                "context_spans": service_context + [{"start": start, "end": end}
                    for start, end in label_bounds if scope_start <= start and end <= scope_end],
                "position_antecedent": antecedent_span,
                "fact_ids": [fact["fact_id"] for fact in sorted(selected, key=lambda row: row["sequence_order"])],
                "support_spans": ([{"start": original_positions[first_match.start()],
                                     "end": original_positions[first_match.end()-1] + 1,
                                     "text": question[original_positions[first_match.start()]:original_positions[first_match.end()-1] + 1]}]
                                  if first_count else
                                  [{"start": start, "end": end, "text": question[start:end]}
                                   for start, end, _ in hits]),
            })
    return projections[0] if len(projections) == 1 else None
