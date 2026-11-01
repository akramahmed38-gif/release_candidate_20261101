"""Catalog-driven lexical spans; no facts, gold questions or model calls.

Feature matching supports bounded morphology. Entity matching is stricter:
Latin plurals never shorten brand names; an internal-ya spelling variant is
accepted only when its catalog skeleton belongs to one provider. Equal-length
ambiguous entity matches remain separate hits for the caller to resolve.
"""
from functools import lru_cache
import json
from pathlib import Path
import re

_TABLE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه",
    "ک": "ك", "ی": "ي", "’": "'", "‘": "'",
})
_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*(?:')?|[\u0621-\u064a]+")
_ARABIC = re.compile(r"[\u0621-\u064a]+\Z")
_LATIN = re.compile(r"[a-z]+\Z")


def shadow(raw):
    """Return normalized text and one original character index per character."""
    chars, positions = [], []
    for index, char in enumerate(raw):
        if char == "ـ" or "\u064b" <= char <= "\u065f" or char == "\u0670":
            continue
        for normalized in char.casefold().translate(_TABLE):
            chars.append(normalized)
            positions.append(index)
    return "".join(chars), positions


def mark(raw, start, end, role):
    """Describe a checked half-open span in the original Unicode string."""
    if (not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or not 0 <= start <= end <= len(raw)):
        raise ValueError("Invalid original-text span bounds")
    return {"start": start, "end": end, "text": raw[start:end], "role": role}


def _arabic_forms(word):
    values = {word}
    bases = {word}
    if word[:1] in {"و", "ف"} and len(word) > 3:
        bases.add(word[1:])
    values.update(bases)
    for base in bases:
        if base.startswith("لل") and len(base[2:]) >= 3:
            values.add(base[2:])
        if base.startswith("ال") and len(base[2:]) >= 3:
            values.add(base[2:])
        if base[:1] in {"ب", "ك", "ل"} and len(base[1:]) >= 3:
            stem = base[1:]
            values.add(stem)
            if stem.startswith("ال") and len(stem[2:]) >= 3:
                values.add(stem[2:])
    return values


def _possessive_forms(word):
    values = {word}
    if word.endswith("'s") and len(word) > 3:
        values.add(word[:-2])
    elif word.endswith("'") and len(word) > 2:
        values.add(word[:-1])
    return values


@lru_cache(maxsize=8192)
def forms(word):
    """Bounded feature-word forms, never a fuzzy spelling correction."""
    word = shadow(word)[0]
    if _ARABIC.fullmatch(word):
        values=set(_arabic_forms(word))
        # Bounded dialect future/possessive morphology applies to linguistic
        # features only. Entity names retain their stricter matcher.
        if word.startswith('ه') and len(word)>4:values.update(_arabic_forms(word[1:]))
        for suffix in ('ها','هم','ه'):
            if word.endswith(suffix) and len(word)-len(suffix)>=3:values.update(_arabic_forms(word[:-len(suffix)]))
        return values
    values = _possessive_forms(word)
    for base in tuple(values):
        if not _LATIN.fullmatch(base):
            continue
        if len(base) > 3 and base.endswith("s"):
            values.add(base[:-1])
        if len(base) > 5 and base.endswith("ing"):
            values.add(base[:-3])
        if len(base) > 4 and base.endswith("ed"):
            values.add(base[:-2])
    return set(values)


def tokens(raw):
    return [match.group() for match in _TOKEN.finditer(shadow(raw)[0])]


def transaction_reference_spans(raw):
    """Relational record fields, never a service code or a national-ID rule.

    A reference/identifier head must bind locally to a transaction-family noun.
    Role, service identity and whether a live record is available are separate
    decisions. No reference value or business answer is inferred here.
    """
    heads=[point for phrase in ['reference','identifier','ID','مرجع','مرجعي','معرف','ريفرنس']
           for point in spans(raw,phrase)]
    records=[point for phrase in ['transaction','payment','remittance','حوالة','حوالات','عملية','معاملة','سداد']
             for point in spans(raw,phrase)]
    grammar=set(tokens('of for the a an particular specific one رقم الرقم ل للـ'))
    proofs=set()
    for a,b in heads:
        for c,d in records:
            if a<d and c<b:
                continue
            between=raw[min(b,d):max(a,c)]
            if re.search(r'[,،;؛.!?؟\n]',between) or not set(tokens(between))<=grammar:
                continue
            proofs.add((min(a,c),max(b,d)))
    return sorted(proofs)


def valued_record_fields(raw, fields, references):
    """Bind a supplied literal key to its field label, without verifying it."""
    return [(a,b) for a,b in fields if any(
        row.get('kind')=='record_identifier'
        and row.get('span',{}).get('start',-1)>=b
        and re.fullmatch(r'\s*[:=#]?\s*',raw[b:row['span']['start']]) is not None
        for row in references)]


def funds_balance_destination(raw):
    """Language-only nominal-funds/direction/balance relation with raw spans."""
    blocked=['refund','transaction','transfer','stock','item','استرداد','تحويل','مخزون','منتج']
    if any(spans(raw,w) for w in blocked):return []
    subjects=[p for w in ['deposit','funding','amount','money','funds','إيداع','ايداع','المبلغ','الفلوس','التمويل'] for p in spans(raw,w)]
    movements=[p for w in ['go','enter','flow','يدخل','يخش','يضاف','يتضاف'] for p in spans(raw,w)]
    balances=[p for w in ['balance','رصيد','الرصيد'] for p in spans(raw,w)]
    auxiliary=set(tokens('will would can does do be is are not never still the automatically تلقائيا'))
    grammar=set(tokens("in into to within the my your its our their customer customer's account wallet في إلى الي داخل العميل حساب محفظة"))
    proof=[]
    for s,t in subjects:
        for a,b in movements:
            if a<t or re.search(r'[.;!?؟؛,،]',raw[t:a]) or not set(tokens(raw[t:a]))<=auxiliary:continue
            for x,y in balances:
                if x<b or re.search(r'[.;!?؟؛,،]',raw[b:x]):continue
                between=tokens(raw[b:x])
                if set(between)<=grammar and any(w in {'in','into','to','within','في','الي','داخل'} for w in between):
                    proof.extend([(s,t),(a,b),(x,y)])
    return sorted(set(proof))


def quote_envelope_fragment(raw, start, end, quote_bounds):
    """Pure labels/attributions adjacent to a quote remain unverified context."""
    # Coordination between two quotations links claims, not user requests.
    # Require both quote boundaries so an ordinary following clause survives.
    if (any(start==right for _,right in quote_bounds)
            and any(end==left for left,_ in quote_bounds)
            and tokens(raw[start:end])
            and set(tokens(raw[start:end]))<=set(tokens('and or و أو او'))):
        return True
    if not any(end==left or start==right for left,right in quote_bounds):
        return False
    labels=set(tokens('sentence statement claim quote assertion الجملة العبارة الادعاء الكلام elgomla'))
    speakers=set(tokens('customer client employee colleague manager supervisor bank عميل العميل زبون موظف زميل مدير بنك 3ameel'))
    speech=set(tokens('said says claims words كلام قول قال بيقول يقول bey2ool'))
    grammar=set(tokens('the a an this that is are my our from مجرد هذا هذه ده دي من حسب el'))
    words=tokens(raw[start:end])
    return bool(words and all(forms(w)&(labels|speakers|speech|grammar) for w in words)
                and (any(forms(w)&labels for w in words)
                     or any(forms(w)&speakers for w in words) and any(forms(w)&speech for w in words)))


def current_tariff_focus(raw, clause, operation_terms, entities):
    """An explicit current-price adjective overrides historical quote context.

    Execution adverbs such as 'correct it now' are not price-period evidence.
    """
    a,b=clause['start'],clause['end'];text=raw[a:b]
    mask=list(text)
    for e in entities:
        if a<=e['start'] and e['end']<=b:mask[e['start']-a:e['end']-a]=' '*(e['end']-e['start'])
    named_mask=''.join(mask)
    current=sorted({p for word in ['current','الحالي','الحالية','الحاليه'] for p in spans(named_mask,word)})
    prices=sorted({p for word in ['fee','charge','tariff','rate','رسوم','تعريفة','عمولة'] for p in spans(named_mask,word)})
    for term in operation_terms:
        for x,y in spans(named_mask,term):mask[x:y]=' '*(y-x)
    masked=''.join(mask);grammar=set(tokens('the a an of for applicable المطبقة الخاصه الخاصة في'))
    return any(set(tokens(masked[min(y,v):max(x,u)]))<=grammar for x,y in current for u,v in prices)


def quoted_channel_reference(raw, clause, service, operation_terms, entities,
                             channels, quote_bounds, channel_parents=None):
    """Resolve a deictic channel from a quoted naming context, never its rule.

    Callers independently supply raw entity/channel marks and their requested
    predicate. Asserted amounts, rates and approval claims are never exported.
    Competing routes prevent channel resolution. Conditional claim scope
    remains unverified even when the naming reference resolves.
    """
    if not quote_bounds:return None
    a,b=clause['start'],clause['end']
    pointers=sorted({point for phrase in ['that channel','this channel','same channel','that route','the quoted channel',
        'القناة دي','القناه دي','للقناة دي','هذه القناة','القناة نفسها','القناه نفسها',
        'el channel da','el channel de','nafs el channel'] for point in spans(raw[a:b],phrase)})
    if not pointers:return None
    candidates=[];qualifiers=[];parents=channel_parents or {}
    verifying=any(spans(raw[a:b],word) for word in ['verify','check','correct','راجع','صحح','تحقق','تأكد','اتأكد'])
    scope_requested=bool(verifying and not current_tariff_focus(raw,clause,operation_terms,entities+channels))
    for left,right in quote_bounds:
        if a<right and left<b:continue
        names=[e for e in entities if left<=e['start'] and e['end']<=right]
        owners={e['service_id'] for e in names if e.get('entity_role','service')=='service'}
        if owners!={service}:continue
        routes=[c for c in channels if left<=c['start'] and c['end']<=right]
        body=list(raw[left:right])
        for item in names+routes:
            x,y=item['start']-left,item['end']-left;body[x:y]=' '*(y-x)
        masked=''.join(body)
        operations=sorted({point for term in operation_terms for point in spans(masked,term)})
        if not operations:continue
        route_ids={c['channel'] for c in routes}
        route_ids-={parents[value] for value in route_ids if value in parents}
        if not route_ids:continue
        scope_words=['if','unless','except','provided','after','before','during','up to','above','below','under','over',
                     'discount','offer','promotion','exempt','daily','monthly','per day','per month',
                     'last year','last month','yesterday',
                     'لو','إذا','اذا','بشرط','باستثناء','بعد','قبل','خلال','خصم','عرض','اعفاء','يومي','شهري',
                     'اقل من','أقل من','اكثر من','اكتر من','فوق','تحت','تجاوز',
                     'السنة الماضية','العام الماضي','الشهر الماضي','أمس','امبارح']
        for phrase in scope_words:
            qualifiers.extend(mark(raw,left+x,left+y,'unverified_claim_scope') for x,y in spans(masked,phrase))
        for proof in principal_minimum_proofs(masked,operations):
            x,y=proof['span'];qualifiers.append(mark(raw,left+x,left+y,'unverified_claim_scope'))
        calendar,positions=shadow(masked)
        calendar=calendar.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789'))
        year=r'(?:19|20)\d{2}'
        dated=r'\b(?:in|on|during)\s+(?:the\s+year\s+)?'+year+r'\b|(?<!\w)(?:في\s+)?(?:سنة|سنه|عام)\s+'+year+r'(?!\w)|(?<!\w)في\s+'+year+r'(?!\w)'
        for match in re.finditer(dated,calendar,re.I):
            qualifiers.append(mark(raw,left+positions[match.start()],left+positions[match.end()-1]+1,'unverified_claim_period'))
        candidates.append({'claim_span':mark(raw,left,right,'unverified_user_claim'),
            'service_spans':[mark(raw,e['start'],e['end'],'quoted_service_reference') for e in names if e['service_id']==service],
            'operation_spans':[mark(raw,left+x,left+y,'quoted_operation_reference') for x,y in operations],
            'channel_spans':[dict(mark(raw,c['start'],c['end'],'quoted_channel_reference'),channel=c['channel'])
                             for c in routes if c['channel'] in route_ids],
            'channel_ids':sorted(route_ids)})
    choices=sorted({value for candidate in candidates for value in candidate['channel_ids']})
    if not candidates:return None
    return {'reference_spans':[mark(raw,a+x,a+y,'channel_referent') for x,y in pointers],
            'antecedents':candidates,'candidate_channels':choices,
            'resolved':len(choices)==1,'channel':choices[0] if len(choices)==1 else None,
            'unverified_scope_spans':qualifiers,'claim_scope_requested':scope_requested,
            'claims_verified':False,'business_fact_authority':False}


@lru_cache(maxsize=1)
def _answer_scope_data():
    value=json.loads((Path(__file__).resolve().parent/'resources/answer_scopes.json').read_text(encoding='utf-8'))
    if value.get('schema')!='NOMINAL_ANSWER_SCOPE_2' or any(
            not isinstance(value.get(key),list) or not value[key] or any(not isinstance(item,str) or not item for item in value[key])
            for key in ('scalar_heads','focus_words','modifiers','condition_starters',
                        'nonrestrictive_prefixes','exclusive_focus_words')):
        raise ValueError('Answer scope resource invalid')
    if (not isinstance(value.get('temporal_heads'),dict) or not value['temporal_heads']
            or any(not isinstance(key,str) or not key or relation not in {'after','before'}
                   for key,relation in value['temporal_heads'].items())):
        raise ValueError('Temporal scope resource invalid')
    return value


def _scalar_focus_proofs(raw, entity_spans=(), nonrestrictive=False):
    """Return original-span proof that focus governs an amount/minimum head.

    Provider names, other topics and condition clauses cannot be swallowed by
    the intervening modifier grammar. The caller must separately establish
    the requested business intent, source scope and evidence completeness.
    """
    data=_answer_scope_data()
    heads=sorted({point for phrase in data['scalar_heads'] for point in spans(raw,phrase)})
    focus=sorted({point for phrase in data['focus_words'] for point in spans(raw,phrase)})
    allowed={form for phrase in data['modifiers']+data['scalar_heads']+data.get('possessive_determiners',[])
             for word in tokens(phrase) for form in forms(word)}
    conditions={form for phrase in data['condition_starters'] for word in tokens(phrase) for form in forms(word)}
    proofs=[]
    for start,end in focus:
        if any(right<=start and not tokens(raw[right:start]) for left,right in entity_spans):
            # "Provider only" restricts the entity, not the scalar value.
            continue
        following=tokens(raw[end:])
        if following and forms(following[0])&conditions:
            continue
        for left,right in heads:
            if max(start,left)<min(end,right):
                continue
            gap=raw[end:left] if end<=left else raw[right:start]
            if re.search(r'[,،;؛.!?؟]',gap):
                continue
            bound=min(start,left)
            negated=any(stop<=bound and not re.search(r'[,،;؛.!?؟]',raw[stop:bound])
                        and all(forms(word)&allowed for word in tokens(raw[stop:bound]))
                        for phrase in data.get('nonrestrictive_prefixes',[])
                        for begin,stop in spans(raw,phrase))
            if negated != nonrestrictive:continue
            if all(forms(word)&allowed for word in tokens(gap)):
                proofs.append({'head_span':mark(raw,left,right,'scalar_head'),
                               'focus_span':mark(raw,start,end,'response_scope')})
    return proofs


def nominal_scalar_focus(raw, entity_spans=()):
    return _scalar_focus_proofs(raw,entity_spans)


def nonrestrictive_scalar_focus(raw):
    """A pure response-scope modifier; it cannot supply a business predicate."""
    data=_answer_scope_data()
    allowed={form for key in ('modifiers','scalar_heads','focus_words','nonrestrictive_prefixes','possessive_determiners')
             for phrase in data.get(key,[]) for word in tokens(phrase) for form in forms(word)}
    if not all(forms(word)&allowed for word in tokens(raw)):return []
    return _scalar_focus_proofs(raw,nonrestrictive=True)


def exclusive_temporal_scopes(raw, excluded_spans=()):
    """Literal user restrictions; these are not established business rules."""
    data=_answer_scope_data();result=[]
    hard=list(re.finditer(r'[;؛!?؟]|(?<!\d)\.(?!\d)',raw))
    for focus in data.get('exclusive_focus_words',[]):
        for start,stop in spans(raw,focus):
            for phrase,relation in data.get('temporal_heads',{}).items():
                heads=[(a,b) for a,b in spans(raw,phrase) if a>=stop
                       and not tokens(raw[stop:a]) and not re.search(r'[,،;؛.!?؟]',raw[stop:a])]
                if not heads:continue
                left,right=min(heads)
                scope_left=max([0]+[m.end() for m in hard if m.end()<=start])
                scope_right=min([len(raw)]+[m.start() for m in hard if m.start()>=right])
                ends=[m.start() for m in re.finditer(r'[,،]|\b(?:what|how|which)\b|(?<!\w)(?:هل|ايه|إيه|ماذا|كام)(?!\w)',raw[right:scope_right],re.I)]
                end=right+min(ends) if ends else scope_right
                if any(a<=start<b for a,b in excluded_spans):continue
                quoted=[(m.start(),m.end()) for m in re.finditer(r'“[^”\n]+”|"[^"\n]+"|«[^»\n]+»|‘[^’\n]+’',raw)]
                enclosing=next(((a,b) for a,b in quoted if a<=start<b),None)
                if enclosing:end=min(end,enclosing[1]-1)
                negations=[(a,b) for phrase in data.get('nonrestrictive_prefixes',[]) for a,b in spans(raw,phrase)
                           if b<=start and not tokens(raw[b:start])]
                negation=max(negations,key=lambda point:point[1]) if negations else None
                condition_start=negation[0] if negation else start
                event_start=right
                while event_start<end and raw[event_start].isspace():event_start+=1
                # Offset the local punctuation boundaries back to raw Unicode.
                local_prefix=raw[scope_left:condition_start]
                prefix_left=scope_left+max([0]+[m.end() for m in re.finditer(r'[,،:]',local_prefix)])
                prefix=not (set(tokens(raw[prefix_left:condition_start]))-{'please','not','never','مش','ليس','لا'})
                result.append({'span':mark(raw,condition_start,end,'scope_restriction'),
                               'event_span':mark(raw,event_start,end,'condition_context'),
                               'head_span':mark(raw,left,right,'temporal_relation'),
                               'relation':relation,'prefix':prefix,'negated':bool(negation),
                               'origin':'user_claim' if enclosing else 'current_request',
                               'scope_start':scope_left,'scope_end':scope_right,
                               'event_missing':not bool(tokens(raw[event_start:end]))})
    unique={(q['span']['start'],q['span']['end'],q['relation']):q for q in result}
    return sorted(unique.values(),key=lambda q:q['span']['start'])


def temporal_scope_bindings(qualifiers, requests):
    """Bind to nearest clause-supported predicate, not an evidence/fact list."""
    assignments={};unbound=[]
    for qualifier in qualifiers:
        left=[];right=[];start=qualifier['span']['start'];end=qualifier['span']['end']
        for index,request in enumerate(requests):
            if request.get('role','requested')!='requested':continue
            for point in request.get('evidence_spans',[]):
                a,b=point.get('start',-1),point.get('end',-1)
                if not qualifier['scope_start']<=a<=b<=qualifier['scope_end']:continue
                if b<=start:left.append((start-b,index))
                elif a>=end:right.append((a-end,index))
        candidates=(right if qualifier['prefix'] else left) or (left if qualifier['prefix'] else right)
        if not candidates:unbound.append(qualifier);continue
        nearest=min(distance for distance,index in candidates)
        for index in {index for distance,index in candidates if distance==nearest}:
            assignments.setdefault(index,[]).append(qualifier)
    return assignments,unbound


def temporal_condition(qualifier):
    return {'operator':'exclusive_temporal_restriction','relation':qualifier['relation'],
            'negated':qualifier.get('negated',False),'origin':qualifier.get('origin','current_request'),
            'text':qualifier['span']['text'],'evidence_span':qualifier['span']}


def temporal_context_fragment(masked, offset, qualifiers):
    """Only a qualifier plus grammatical framing may be context-only."""
    chars=list(masked);overlap=False
    for qualifier in qualifiers:
        left=max(offset,qualifier['span']['start'])
        right=min(offset+len(masked),qualifier['span']['end'])
        if left<right:
            chars[left-offset:right-offset]=' '*(right-left);overlap=True
    allowed={form for phrase in _answer_scope_data()['modifiers']
             for word in tokens(phrase) for form in forms(word)}
    return overlap and all(forms(word)&allowed for word in tokens(''.join(chars)))

def filter_predicate_entity_mentions(raw,hits,features):
    """Separate short common nouns inside typed predicates from product names."""
    cues=[(a,b) for key in ['initial','existing_wallet','balance_disposition'] for phrase in features.get(key,[]) if len(tokens(phrase))>1 for a,b in spans(raw,phrase)]
    context=[h for h in hits if len(tokens(h['text']))==1 and any(a<=h['start'] and h['end']<=b and b-a>h['end']-h['start'] for a,b in cues)]
    rejected={(h['service_id'],shadow(h['text'])[0]) for h in context}
    for h in hits:
        if (h['service_id'],shadow(h['text'])[0]) in rejected and any(spans(raw[max(0,h['start']-12):h['start']],w) for w in ['هذا','نفس','ذلك','this','that']):
            if h not in context:context.append(h)
    return [h for h in hits if h not in context],context

def _positive_family_context(prefix):
    """A contextual family cue must not be the object of an exclusion."""
    prefix=re.sub(r'\bnot\s+(?:only|just)\b|ليس\s+فقط|مش\s+بس',' ',prefix,flags=re.I)
    exclusions=[point for phrase in ['not','never',"don't",'without','exclude','excluding','مش','ليس','بدون','لا']
                for point in spans(prefix,phrase)]
    exclusions += [(row['start'],row['end']) for row in egyptian_negative_verbs(prefix)]
    glue=set(tokens('the a an about asking ask requesting request mention discuss include give show talk for of عن في الـ'))
    return not any(set(tokens(prefix[end:]))<=glue for start,end in exclusions)


def qualified_catalog_entities(raw,profiles,roles,rules):
    """Resolve shared catalog brands from nearest explicit family qualifiers."""
    hits=resolve_entities(raw,profiles,roles)
    for rule in rules:
        choices=rule.get('candidates',[]);qualifiers=rule.get('qualifiers',{})
        if len(choices)<2 or not qualifiers:continue
        targets=[h for h in hits if h['service_id'] in choices]
        positions={(h['start'],h['end']) for h in targets}
        positions.update(spans(raw,rule.get('example','')))
        for alias in rule.get('brand_aliases',[]):positions.update(spans(raw,alias))
        foreign_names=[(h['start'],h['end']) for h in hits if h['service_id'] not in choices]
        rewritten=[]
        for a,b in positions:
            left=max([0]+[m.end() for m in re.finditer(r';|؛|[؟?]|\band\b',raw[:a],re.I)])
            tail=re.search(r';|؛|[؟?]|\band\b',raw[b:],re.I);right=b+tail.start() if tail else len(raw)
            scores={};basis='explicit_catalog_family_qualifier'
            for service in choices:
                distances=[]
                for phrase in qualifiers.get(service,[]):
                    for x,y in spans(raw[left:right],phrase):
                        start,end=left+x,left+y
                        if any(c<=start and end<=d and (c,d)!=(start,end) for c,d in foreign_names):continue
                        if not (a<=start and end<=b) and not _positive_family_context(raw[left:start]):continue
                        distances.append(max(0,a-end,start-b))
                if distances:scores[service]=min(distances)
            # Operational wording is weaker than an explicit family name.
            # Keep it clause-local, outside the brand and positively scoped.
            if not scores:
                weak_left=max([left]+[m.end() for m in re.finditer(r'[,،]',raw[:a]) if m.end()>=left])
                comma=re.search(r'[,،]',raw[b:right]);weak_right=b+comma.start() if comma else right
                for service in choices:
                    distances=[]
                    for phrase in rule.get('contextual_qualifiers',{}).get(service,[]):
                        for x,y in spans(raw[weak_left:weak_right],phrase):
                            start,end=weak_left+x,weak_left+y
                            if start<b and a<end:continue
                            if any(c<=start and end<=d and (c,d)!=(start,end) for c,d in foreign_names):continue
                            if not _positive_family_context(raw[weak_left:start]):continue
                            distances.append(max(0,a-end,start-b))
                    if distances:scores[service]=min(distances)
                basis='positive_catalog_family_context'
            selected=[s for s,v in scores.items() if v==min(scores.values())] if scores else []
            if len(selected)==1:
                rewritten.append({'service_id':selected[0],**mark(raw,a,b,'service'),'entity_role':roles.get(selected[0],'service'),'match_basis':basis})
            else:
                # A shorter existing alias is not evidence for choosing one
                # service family. Keep every equally possible owner of the
                # current brand span until an explicit qualifier resolves it.
                rewritten.extend([{'service_id':service,**mark(raw,a,b,'service'),'entity_role':roles.get(service,'service'),'match_basis':'ambiguous_catalog_brand'} for service in (selected or choices)])
        if rewritten:hits=[h for h in hits if h['service_id'] not in choices]+rewritten
    return sorted({(h['service_id'],h['start'],h['end']):h for h in hits}.values(),key=lambda h:h['start'])


def _entity_forms(word):
    return _arabic_forms(word) if _ARABIC.fullmatch(word) else _possessive_forms(word)


def _matches(raw, phrase, word_forms):
    normalized, positions = shadow(raw)
    words = list(_TOKEN.finditer(normalized))
    target = tokens(phrase)
    if not target:
        return []
    result = []
    for index in range(len(words) - len(target) + 1):
        if all(word_forms(words[index + offset].group()) & word_forms(term)
               for offset, term in enumerate(target)):
            result.append((positions[words[index].start()],
                           positions[words[index + len(target) - 1].end() - 1] + 1))
    return result


def spans(raw, phrase):
    """Return exact raw slices matching a normalized feature phrase."""
    return _matches(raw, phrase, forms)


def nominal_scope_omission(raw, predicate_heads):
    """A leading omission operator governing a fee noun, not a proposition.

    Callers supply independently detected heads from the raw clause. Questions
    and finite/modal assertions are deliberately left to ordinary polarity
    handling: ``can I deposit without fees`` is not an omission instruction.
    """
    value = shadow(raw)[0].strip(' ,،;؛:')
    leading = re.match(r'^(?:without\b|بدون\b|دون\b|من\s+غير\b)', value, re.I)
    if not leading or not predicate_heads:
        return False
    if re.search(r'\b(?:can|could|may|must|should|would|will|does|do|is|are|was|were|why|how|what|whether|if)\b'
                 r'|(?<!\w)(?:هل|كيف|ليه|لماذا|ينفع|ممكن|لازم|يجب|لو|اذا)(?!\w)', value, re.I):
        return False
    return True


def egyptian_negative_verbs(raw):
    """Original spans for split/attached negation and optional conjunctions."""
    value,positions=shadow(raw);words=list(re.finditer(r'[\u0621-\u064a]+',value));rows=[]
    for index,word in enumerate(words):
        text=word.group();start=word.start()
        if not text.endswith('ش'):continue
        base=text[:-1]
        if base.startswith(('وما','فما')):base=base[1:]
        if base.startswith(('وم','فم')) and not base.startswith(('وما','فما')):base=base[1:]
        if base.startswith('ما') and len(base)>4:stem=base[2:]
        elif base.startswith('م') and len(base)>4:stem=base[1:]
        elif index and words[index-1].group() in {'ما','وما','فما'}:
            stem=base;start=words[index-1].start()
        else:continue
        rows.append({'stem':stem,'start':positions[start],'end':positions[word.end()-1]+1})
    return rows


def response_scope_omission(raw):
    """Second-person metadiscourse, not past events or business prohibition."""
    discourse={'ذكر','شرح','ناقش','تكلم'}
    for row in egyptian_negative_verbs(raw):
        prefix=shadow(raw[:row['start']])[0].strip(' ,،;؛:')
        if prefix not in {'','و','ف','please','لو سمحت'}:continue
        stem=row['stem']
        if not stem.startswith('ت'):continue
        root=stem[1:];tail=raw[row['end']:]
        if root in discourse or root=='دخل' and re.match(r'\s*(?:في|عن)(?!\w)',shadow(tail)[0]):
            return True
    return False


def fronted_process_contexts(question, entity_spans, channel_spans, features):
    """Certified fronted operation/task context before an explicit field query.

    No source facts, default provider or retrieved-example roles are consulted.
    Unknown words/conditions remain explicit unresolved context, never a
    license to turn the contextual operation into an additional fee question.
    """
    comma=re.search(r'[,،]',question)
    if comma is None or re.search(r'[;؛.!?؟\n]',question[:comma.start()]):return []
    start,end=0,comma.start();prefix=question[:end];tail=question[comma.end():]
    # Inspect the actual following clause, not excluded or unrelated material
    # later in the question. A current price query still needs its operation.
    stop=re.search(r'[,،;؛.!?؟\n]',tail)
    main_tail=tail[:stop.start()] if stop else tail
    normalized=shadow(prefix)[0].strip(' \t:')
    purpose=bool(re.match(r'^(?:for|during|while)\b|^ل(?=[\u0621-\u064a])',normalized,re.I))
    preparatory=bool(re.match(r'^(?:before\s+(?:i|we)\s+(?:compare|contrast|review)|قبل\s+ما\s+(?:اقارن|نقارن|اراجع|نراجع))\b',normalized,re.I))
    if not (purpose or preparatory):return []
    if not re.match(r'^\s*(?:what|which|how|tell|give|state|show|write|اكتب|أكتب|قول|وضح|ما|ايه|إيه)\b',tail,re.I):return []
    field_keys=['code','identity','phone_owner','existing_wallet','documents','image','permission','initial','activation','balance_disposition']
    if not any(spans(main_tail,phrase) for key in field_keys for phrase in features.get(key,[])):return []
    if any(spans(main_tail,phrase) for phrase in features.get('fee',[])):return []
    operation_keys=['deposit','withdrawal','opening','workflow','initial','activation']
    operation_spans=[point for key in operation_keys for phrase in features.get(key,[]) for point in spans(prefix,phrase)]
    if not operation_spans:return []
    chars=list(prefix)
    erase=list(entity_spans)+list(channel_spans)+operation_spans
    erase += [point for key in ['fee','comparison'] for phrase in features.get(key,[]) for point in spans(prefix,phrase)]
    for left,right in erase:
        if 0<=left<right<=end:chars[left:right]=' '*(right-left)
    functional=set(tokens('for during while before I we compare contrast review and or the a an of to in at through via each customer wallet remittance transfer transaction process قبل ما اقارن نقارن اراجع نراجع و او من في عند عن للعميل العميل محفظة حوالة حوالات عملية عمليات مصرف'))
    functional.add('cash')
    if preparatory:functional.update(tokens('with against مع مقابل'))
    remainder=tokens(''.join(chars))
    unknown=[word for word in remainder if word not in functional]
    return [{'start':start,'end':end,'text':prefix,'role':'context_only',
             'kind':'preparatory_task' if preparatory else 'operation_subject',
             'unresolved_context_tokens':unknown,
             'following_request_span':{'start':comma.end(),'end':comma.end()+len(main_tail),'text':main_tail}}]


def principal_minimum_proofs(raw, operation_spans):
    """Compose a bounded principal amount; a fee floor is a different object."""
    bounds=[p for phrase in ['minimum','least','smallest','الحد الأدنى','أقل','اقل','a2al'] for p in spans(raw,phrase)]
    amounts=[p for phrase in ['amount','principal','sum','مبلغ','قيمة','mablagh'] for p in spans(raw,phrase)]
    fee_heads=[p for phrase in ['fee','charge','commission','رسوم','عمولة','3omoola','3amoola','rosoom'] for p in spans(raw,phrase)]
    grammar=set(tokens('the a an its their my your of for to per transaction transactions cash out operation operations amount required needed at on الحد الادنى اقل مبلغ قيمة عملية العملية المعاملة المعامله من في عن لكل ال'))
    results=[]
    for bound in bounds:
        for amount in amounts:
            for operation in operation_spans:
                left=min(bound[0],amount[0],operation[0]);right=max(bound[1],amount[1],operation[1])
                if re.search(r'[;؛,:.،!?؟()\[\]/|\n]',raw[left:right]):continue
                if any(left<=a and b<=right for a,b in fee_heads):continue
                if any(right<=a and not re.search(r'[;؛,:.،!?؟()\[\]/|\n]',raw[right:a])
                       and set(tokens(raw[right:a]))<=grammar for a,b in fee_heads):continue
                chars=list(raw[left:right])
                for a,b in [bound,amount,operation]:chars[a-left:b-left]=' '*(b-a)
                if not set(tokens(''.join(chars)))<=grammar:continue
                proof={'bound':bound,'amount':amount,'operation':operation,'span':(left,right)}
                if proof not in results:results.append(proof)
    return results


def bind_dimension_channel_references(question, requests, adapter):
    """Bind a current referent across dimensions of one declared operation.

    Each caller supplies its own request reconstruction. No facts or prior
    session defaults are used, and ambiguity never becomes a union of routes.
    """
    ambiguous=[]
    for request in requests:
        family=adapter.get(request.get('intent_id'),{}).get('channel_reference_group')
        clause=request.get('clause_span',{})
        references=spans(clause.get('text',''),'its')+spans(clause.get('text',''),'their')+spans(clause.get('text',''),'same')+spans(clause.get('text',''),'نفس')
        if (not family or request.get('channels') or request.get('role')!='requested'
                or not request.get('service_id') or not references):continue
        peers=[row for row in requests if row is not request and row.get('role')=='requested'
               and row.get('service_id')==request['service_id'] and row.get('channels')
               and row.get('intent_id')!=request['intent_id']
               and adapter.get(row.get('intent_id'),{}).get('channel_reference_group')==family
               and row.get('period')==request.get('period') and row.get('conditions',[])==request.get('conditions',[])
               and row.get('excluded_channels',[])==request.get('excluded_channels',[])
               and row.get('clause_span',{}).get('end',len(question)+1)<=clause.get('start',-1)
               and not re.search(r'[;؛.!?؟\n]',question[row['clause_span']['end']:clause['start']])]
        routes={channel for row in peers for channel in row['channels']}
        if len(routes)==1:
            request['channels']=list(routes)
            request['channel_antecedent_requests']=[row['request_id'] for row in peers]
            request['channel_reference_spans']=[mark(question,clause['start']+a,clause['start']+b,'channel_referent') for a,b in references]
        elif routes:ambiguous.append({'request_id':request['request_id'],'channels':sorted(routes),'span':clause})
    return ambiguous


def nominal_catalog_heads(raw, intent_ids):
    """Literal catalog heads in an otherwise nominal information request.

    Entity masking and clause-role decisions belong to each caller. This span
    primitive neither reads request graphs nor promotes retrieved examples.
    A competing substantive word prevents a shorter head from taking scope.
    """
    functional = {'what', 'about', 'the', 'please', 'explain', 'tell', 'me',
                  'a', 'an', 'for', 'information', 'on', 'only'}
    words = set(tokens(raw))
    found = {}
    for intent in intent_ids:
        phrase = intent.replace('_', ' ')
        heads = spans(raw, phrase)
        if heads and words <= set(tokens(phrase)) | functional:
            found[intent] = heads
    return found


def response_layout_directive(raw):
    """Pure response arrangement, never an additional business predicate."""
    actions=set(tokens('keep give show list present state need want اعرض اذكر وضح قول محتاج عايز'))
    markers=set(tokens('separate separately individually explicit منفصل منفصلة منفصله لوحده لوحدها حدة'))
    objects=set(tokens('each every both all their its these those answers answer response service services provider providers scope scopes part parts field fields topic topics evidence missing كل لكل نطاق نطاقات اجابة اجابات رد ردود خدمة خدمات جزء اجزاء بينهم'))
    grammar=set(tokens('the a an for of on to by please it them one per بشكل على في'))
    words=tokens(raw)
    return bool(any(forms(w)&actions for w in words) and any(forms(w)&markers for w in words)
                and any(forms(w)&objects for w in words)
                and all(forms(w)&(actions|markers|objects|grammar) for w in words))


def nominal_layout_mask(raw):
    for separator in re.finditer(':',raw):
        if response_layout_directive(raw[separator.end():]):
            return raw[:separator.start()]+' '*(len(raw)-separator.start())
    return raw


def catalog_nominal_proofs(raw,rows):
    """Whole nominal-clause proofs from catalog language, not example graphs."""
    masked=nominal_layout_mask(raw)
    functional=set(tokens('what which is are the a an please explain tell me for of on about information only give ما ماذا ايه عن من في بخصوص فقط'))
    results={}
    canonical={}
    for row in rows:
        intent=row['intent_id']
        if intent in {'other_or_unknown','permission','explanation'}:continue
        literal=intent.replace('_',' ')
        cues=[literal]+[cue for key in ['en_cues','ar_msa_cues','ar_eg_cues','franco_eg_cues']
                       for cue in row.get(key,[]) if len(tokens(cue))>1]
        for cue in cues:
            points=spans(masked,cue)
            if not points:continue
            chars=list(masked)
            for a,b in points:chars[a:b]=' '*(b-a)
            if all(forms(word)&functional for word in tokens(''.join(chars))):
                results.setdefault(intent,[]).extend(p for p in points if p not in results.get(intent,[]))
                if cue==literal:canonical.setdefault(intent,[]).extend(p for p in points if p not in canonical.get(intent,[]))
    if canonical:return canonical
    # Conflicting aliases are proposals, never permission to request both
    # meanings of the same phrase. Other typed interpretation may resolve it.
    ambiguous={intent for intent,points in results.items() for other,other_points in results.items()
               if other!=intent and any(a<y and x<b for a,b in points for x,y in other_points)}
    return {intent:points for intent,points in results.items() if intent not in ambiguous}


def _name_variants(profile):
    seen = set()
    values = [(str(alias), "catalog_alias") for alias in profile.get("aliases", [])
              if isinstance(alias, str) and alias.strip()]
    name = profile.get("name", "")
    if isinstance(name, str) and name.strip():
        values.append((name, "catalog_name"))
        for segment in re.split(r"[/|]", name):
            if segment.strip():
                values.append((segment.strip(), "catalog_name_segment"))
            # Derive an app brand head only from a catalog name, never arbitrary
            # question text or an alias suffix such as "Wallet"/"Remittance".
            head = re.sub(r"\s+(?:app|application)\s*$", "", segment,
                          flags=re.IGNORECASE).strip()
            if head and head != segment.strip():
                values.append((head, "catalog_name_app_head"))
                if re.fullmatch(r"[A-Za-z]+(?:\s+[A-Za-z]+)+", head):
                    values.append((re.sub(r"\s+", "", head),
                                   "catalog_name_app_head_compact"))
    for phrase, basis in values:
        key = tuple(tokens(phrase))
        if key and key not in seen:
            seen.add(key)
            yield phrase, basis


def _ya_skeleton(word):
    """Only internal ي is optional; four remaining Arabic letters required."""
    if not _ARABIC.fullmatch(word):
        return None
    value = word[:1] + word[1:-1].replace("ي", "") + word[-1:]
    return value if len(value) >= 4 else None


def _skeleton_keys(phrase):
    # Conservative single-token catalog aliases only. Multiword names retain
    # their ordinary lexical matching, avoiding combinatorial fuzzy variants.
    words = tokens(phrase)
    if len(words) != 1:
        return set()
    return {key for value in _arabic_forms(words[0])
            if (key := _ya_skeleton(value)) is not None}


def resolve_entities(raw, profiles, roles):
    """Resolve catalog names without selecting between equal ambiguous hits.

    profiles may be a {service_id: profile} mapping or a profile list. Returned
    hits always retain exact Unicode start/end/text. A longer explicitly named
    provider outranks a shorter contained head; same-span providers survive.
    """
    items = list(profiles.items()) if isinstance(profiles, dict) else [
        (profile["service_id"], profile) for profile in profiles]
    variants = [(service, phrase, basis) for service, profile in items
                for phrase, basis in _name_variants(profile)]
    acronym_owners = {}
    declared_heads = {tuple(tokens(segment)) for _, profile in items
                      for segment in re.split(r"[/|]", profile.get("name", ""))
                      if len(tokens(segment)) == 1}
    for service, profile in items:
        for segment in re.split(r"[/|]", profile.get("name", "")):
            match = re.match(r"\s*([A-Z][A-Z0-9]{2,})\b", segment)
            if match:
                acronym_owners.setdefault(match.group(1).casefold(), set()).add(service)
    skeleton_owners = {}
    for service, phrase, _ in variants:
        for key in _skeleton_keys(phrase):
            skeleton_owners.setdefault(key, set()).add(service)
    hits = []
    def append(service, start, end, basis):
        hits.append({"service_id": service, "start": start, "end": end,
                     "text": raw[start:end], "role": "service",
                     "entity_role": roles.get(service, "service"),
                     "match_basis": basis})
    for service, phrase, basis in variants:
        for start, end in _matches(raw, phrase, _entity_forms):
            append(service, start, end, basis)
            key = tokens(phrase)
            if (len(key) == 1 and tuple(key) not in declared_heads
                    and len(acronym_owners.get(key[0], ())) > 1):
                for other in acronym_owners[key[0]] - {service}:
                    append(other, start, end, "catalog_shared_acronym_ambiguous")
    normalized, positions = shadow(raw)
    for word in _TOKEN.finditer(normalized):
        start, end = positions[word.start()], positions[word.end() - 1] + 1
        # Never use skeleton matching to override an existing literal/morph hit.
        if any(hit["start"] <= start and hit["end"] >= end for hit in hits):
            continue
        candidates = set()
        for value in _arabic_forms(word.group()) if _ARABIC.fullmatch(word.group()) else ():
            key = _ya_skeleton(value)
            if key is not None and len(skeleton_owners.get(key, ())) == 1:
                candidates.update(skeleton_owners[key])
        if len(candidates) == 1:
            append(next(iter(candidates)), start, end,
                   "catalog_unique_internal_ya_skeleton")
    unique = {}
    for hit in hits:
        unique.setdefault((hit["service_id"], hit["start"], hit["end"]), hit)
    hits = list(unique.values())
    return sorted([hit for hit in hits if not any(
        other["start"] <= hit["start"] and other["end"] >= hit["end"]
        and other["end"] - other["start"] > hit["end"] - hit["start"]
        for other in hits)], key=lambda hit: (hit["start"], -hit["end"], hit["service_id"]))
