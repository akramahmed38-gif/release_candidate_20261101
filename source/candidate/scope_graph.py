"""Clause-role graph: language proposals never commit current business scope."""
from pathlib import Path
import json,re
from linguistic_spans import shadow,spans,tokens,forms,mark,filter_predicate_entity_mentions,nominal_scalar_focus,nominal_scope_omission,nominal_catalog_heads,exclusive_temporal_scopes,temporal_scope_bindings,temporal_condition,nonrestrictive_scalar_focus,temporal_context_fragment
from chatbot.query_language import reply_language
from annotation_candidates import lexical_candidates
from semantic_frames import infer_clause,annotate_operators,ATOMS
from procedure_projection import project_procedure_members,projection_covers_span
from dialogue_scope import additive_provider_reference,antecedent_scope
from entity_scope import task_group,entity_omission,entity_nonrestriction
from response_binding import binding_preservation_directive
from linguistic_spans import catalog_nominal_proofs,response_layout_directive
from linguistic_spans import response_scope_omission,fronted_process_contexts,principal_minimum_proofs,bind_dimension_channel_references
from linguistic_spans import transaction_reference_spans,valued_record_fields
from linguistic_spans import quoted_channel_reference

ROOT=Path(__file__).resolve().parent
CONTEXT_CHANNEL_INTENTS={'workflow','branch_condition','identity','phone_ownership','existing_wallet','image_permission','documents','transaction_code'}
TARIFFS={'deposit_tariff','withdrawal_tariff'}
QUOTE_RE=re.compile(r'“[^”\n]+”|"[^"\n]+"|«[^»\n]+»|‘[^’\n]+’|\u2018[^\u2019\n]+\u2019')

# These words describe the employee's artefact or review task.  They are not
# business predicates.  The classifier below is deliberately bounded by a
# task action/preamble and refuses to consume an unknown substantive question.
TASK_OBJECTS=[
    'ticket','memo','card','form','sheet','worksheet','file','record','row','field',
    'note','handover','review','audit','shift','minutes','line','entry','control','instruction','route','gap','answer','item','items',
    'تذكرة','مذكرة','بطاقة','كارت','نموذج','ورقة','شيت','ملف','سجل','صف','خانة',
    'حقل','ملاحظة','تسليم','مراجعة','تدقيق','شيفت','محضر','سطر','بند','نقطة','إجابة','اجابة','إجابتين','اجابتين',
    'tazkara','memo','card','form','sheet','file','record','field','review','audit','shift'
]
TASK_ACTIONS=[
    'wrote','written','says','states','contains','puts','makes','has a blank','have a blank',
    'labelled','labeled','field named','خانة اسمها','named field','missing','stopped at','reconciling','cross-check',
    'populate','fill','list','answer','need','want','correct this','replace that','switch','change','changed','move on',
    'close the shift','closing the shift','كتب','مكتوب','ورد','يقول','فيه','ناقص',
    'covered','missing','substitute','عايز','محتاج','املأ','املا','صحح','استبدل','حوّل','حول','غيّر','غير','غاب','فجوة','seebha',
    'اقفل الشيفت','ba3mel','aktob','emla','sa7a7','ghayar'
]
TASK_REFERENCE=[
    'this field','that field','these fields','this line','that line','this claim',
    'that claim','these claims','two claims','that phrase','this phrase','each route','new route','new channel',
    'the source order','faulty sequence','tariff correction','source correction',
    'الخانة','الحقل','السطر','الادعاء','الادعاءين','تصحيح التعرفة','تصحيح المرجع',
    'هذين الادعاءين','العبارة','التسلسل','الترتيب الصحيح','كل طريق','المسار الجديد','القناة الجديدة','kol wa7da'
]
RESPONSE_EXCLUSION=[
    'do not mention','do not state','do not give','do not include','do not assess',
    'do not explain','not asking for','not requesting','leave out','keep out',
    'without mentioning','without discussing','without talking about',
    'not in scope','outside the review','outside this review',
    'لا تذكر','لا تكتب','لا تعط','لا تعطي','لا تشرح','لا أطلب','لا اطلب','لا تعامل',
    'مش محتاج','مش عايز','من غير كلام','بدون كلام','دون ذكر','مالناش دعوة',
    'ملناش دعوة','مش داخل المراجعة','خارج المراجعة','ماتحطليش','ما تحطليش','متقوليش',
    'matdeeneesh','malnaash da3wa','mesh dakhel','msh dakhel'
]

def any_span(raw,phrases):return [x for phrase in phrases for x in spans(raw,phrase)]
def unique(values):return list(dict.fromkeys(values))

def overlaps(left,right):
    return left[0]<right[1] and right[0]<left[1]

def task_envelope(text,goals):
    """Return a structural task kind without swallowing unknown policy scope.

    Administrative nouns are common in employee questions, but a bare noun is
    not enough.  A current task action/preamble must also be present.  Unknown
    interrogatives remain unresolved so this cannot turn arbitrary wording
    into harmless context.
    """
    value=shadow(text)[0]
    objects=any_span(text,TASK_OBJECTS)
    actions=any_span(text,TASK_ACTIONS)
    anchored=bool(re.match(
        r'^\s*(?:before\s+we\s+move\s+on|before\s+(?:i|we)\s+close\s+the\s+shift|'
        r'قبل\s+ما\s+اقفل\s+الشيفت|في\s+(?:مراجعة|مراجعه|تدقيق|(?:quality\s+)?review|audit)|fi\s+(?:review|audit)|'
        r'fi\s+(?:end-of-day|shift)\s+(?:sheet|form)|'
        r'(?:el\s+)?(?:shift|handover|end-of-day)\s+(?:sheet|form)|'
        r'(?:for|in)\s+(?:a\s+)?(?:review|audit)|'
        r'(?:an?|the)\s+\w+(?:\s+\w+){0,3}\s+(?:memo|note|card|form|sheet|file|record))\b',
        value,re.I))
    if not ((objects and actions) or anchored):return None
    # An unrecognised substantive question inside the wrapper must still reach
    # clarification.  Recognised goals are safe to retain outside the shell.
    if not goals and re.search(r'\b(?:what|which|how|whether|required|allowed|rule|policy)\b|(?<!\w)(?:هل|ايه|إيه|كيف|ما\s+شرط|مطلوب)(?!\w)',value,re.I):
        return None
    return 'task_envelope'

def response_exclusion(text):
    value=shadow(text)[0]
    return bool(response_scope_omission(text) or any_span(text,RESPONSE_EXCLUSION) or
                re.search(r'\bleave\b.{0,48}\bout\b|\bdo\s+not\b.{0,48}\b(?:mention|state|give|include|assess|explain)\b',value,re.I))

def numeric_field_envelope(text):
    """Identify a task asking for a bounded list of numeric fields.

    The envelope narrows numeric renderings, not business meaning.  It needs
    both a review/form/list context and an explicit plural number/value/field
    object, so an ordinary scalar funding question is unaffected.
    """
    value=shadow(text)[0]
    task=bool(re.search(
        r'\b(?:review|audit|sheet|form|worksheet|table|list|fields?|columns?|entries)\b|'
        r'(?<!\w)(?:مراجعة|مراجعه|تدقيق|شيت|نموذج|جدول|قائمة|خانات?|حقول|بنود)(?!\w)',
        value,re.I))
    numeric=bool(re.search(
        r'\b(?:(?:two|three|four|five|\d+)\s+(?:different\s+)?(?:numbers?|amounts?|figures?|values?|numeric\s+fields?)|'
        r'(?:two|three|four|five|\d+)[-\s](?:number|amount|figure|value)(?:\s+(?:fields?|columns?|entries))?|'
        r'(?:numeric|number|amount)\s+(?:fields?|columns?|entries))\b|'
        r'(?<!\w)(?:رقمين|رقمان|أرقام|ارقام|قيمتين|قيم|مبلغين|مبالغ|خانتين\s+رقميتين)(?!\w)',
        value,re.I))
    return task and numeric

def numeric_field_groups(text):
    """Return sentence-bounded spans governed by a numeric task envelope."""
    groups=[]
    for match in re.finditer(r'[^.!?؟\n]*(?:[.!?؟\n]+|$)',text):
        segment=match.group(0)
        if segment.strip() and numeric_field_envelope(segment):
            groups.append((match.start(),match.end()))
    return groups
def subject_key(request):
    if request.get('service_id') is not None:return ('service',request['service_id'])
    providers=tuple(request.get('unsupported_named_provider') or [])
    return ('unsupported_named',providers) if providers else ('unresolved_subject',)

def binding_subject_key(binding):
    if isinstance(binding,str) and binding.startswith('unsupported_named:'):
        return ('unsupported_named',(binding.split(':',1)[1],))
    return subject_key({'service_id':binding})

def independent_request_head(text):
    value=shadow(text)[0].lstrip(' ,،:؛;.')
    return bool(re.match(r'(?:(?:separately|then|also|now)\s+)?(?:explain\b|tell\s+me\b|show\s+me\b|give\s+me\b|check\b|describe\b|what\s+(?:is|are|does)\b|how\s+(?:much|does|do)\b|اشرح\b|وضح\b|هل\b|ايه\b|ما\s+(?:هي|هو)\b)',value))

def franco_reply_language(text):
    """Detect bounded Egyptian Arabizi grammar without treating brands as Arabic."""
    value=shadow(text)[0]
    if re.search(r'(?<!\w)(?:[a-z]+[23789][a-z][a-z0-9]*|[a-z]{2,}[23789]|[23789][a-z]+)(?!\w)',value,re.I):
        return True
    words=set(tokens(value))
    markers={'tab','w','el','da','de','tany','lama','wala','bas','mesh','msh',
             'men','fel','3aleih','3ala','arooh','aroo7','yewagahny','ba2y'}
    return len(words & markers)>=3

def distributive_subject_reference(text):
    """Classify an explicit reference to every member of a provider set.

    This is grammatical scope only.  It never discovers a provider or policy;
    callers may bind it solely to independently named current-turn subjects.
    ``pair`` requires exactly two subjects, while ``all`` may bind two or more.
    """
    value=shadow(text)[0]
    pair=[
        r'\b(?:either|neither|both)\s+(?:provider|providers|service|services|wallet|wallets)\b',
        r'\b(?:either|neither|both)\s+of\s+(?:the\s+)?(?:providers|services|wallets)\b',
        r'(?<!\w)(?:كلا|كلتا)\s+(?:الخدمتين|المحفظتين|المقدمين)(?!\w)',
        r'(?<!\w)(?:أي|اي|لاي)\s+من\s+(?:الخدمتين|المحفظتين|مقدمي\s+الخدمة)(?!\w)',
        r'(?<!\w)(?:ولا\s+واحد|الاتنين|الاثنين)\s+من\s+(?:الخدمتين|المحفظتين|مقدمي\s+الخدمة)(?!\w)',
        r'\b(?:either|neither|both|wala\s+wa7ed|el\s+etneen)\s+(?:provider|providers|service|services|wallet|wallets)\b',
    ]
    broad=[
        r'\b(?:each|every|all)\s+(?:provider|providers|service|services|wallet|wallets)\b',
        r'(?<!\w)(?:كل|جميع)\s+(?:خدمة|الخدمات|محفظة|المحافظ|مقدم\s+خدمة|مقدمي\s+الخدمة)(?!\w)',
        r'\b(?:kol|gamee3)\s+(?:provider|providers|service|services|wallet|wallets)\b',
    ]
    if any(re.search(pattern,value,re.I) for pattern in pair):return 'pair'
    if any(re.search(pattern,value,re.I) for pattern in broad):return 'all'
    return None

class ScopeGraph:
    def __init__(self,planner):
        self.p=planner
        extra=json.loads((ROOT/'resources/recovery_features.json').read_text(encoding='utf-8'))
        self.features={k:unique(v+extra.get(k,[])) for k,v in planner.features.items()}
        for k,v in extra.items():self.features.setdefault(k,v)
    def procedure_service_for_platform(self,platform_id):
        """Resolve a platform to a unique procedure owner from fixture metadata.

        This is intentionally metadata-driven.  A platform mention is not a
        provider by itself, and no service name is embedded in this rule.
        """
        if not isinstance(platform_id,str) or not platform_id:return None
        bindings=self.p.adapter.get('workflow',{}).get('procedure_channel_bindings',{})
        contracts=set(bindings.get(platform_id,[]))
        candidates=[]
        for fact in self.p.definition.get('facts',[]):
            if not fact.get('atomic_group') or 'workflow' not in fact.get('selection_tags',[]):continue
            scope=fact.get('scope') or {}
            # A shared word in a view is not a platform/owner relationship.
            # Only the registered contract binding or an explicit source-scope
            # platform identifier can establish this edge.
            if fact.get('procedure_contract') in contracts or scope.get('platform_id')==platform_id:
                candidates.append(fact.get('service_id'))
        values=unique(service for service in candidates if service)
        return values[0] if len(values)==1 else None

    def entity_clause_region(self,question,entity,entities):
        """Local ownership window; connectors inside catalog names stay atomic."""
        separators=[match for match in re.finditer(
            r'[;؛,،?!؟]|(?<!\d)\.(?!\d)|\b(?:and|but|versus|vs|alongside|whereas|also)\b|(?<!\w)و(?!\w)',
            question,re.I)
            if not any(row['start']<=match.start()<row['end'] for row in entities)]
        left=max([0]+[match.end() for match in separators if match.end()<=entity['start']])
        right=min([len(question)]+[match.start() for match in separators if match.start()>=entity['end']])
        return left,right

    def catalog_entity_is_context(self,question,entity,region,products):
        """Apply declared alias/relationship rules, not blanket entity types."""
        left,right=region;local=question[left:right]
        for rule in self.p.entity_rules:
            aliases=rule.get('contextual_aliases',[])
            candidate=entity['service_id'] in rule.get('candidates',[])
            exact_alias=any(shadow(entity['text'])[0].strip()==shadow(alias)[0].strip() for alias in aliases)
            if candidate and exact_alias and products and not any_span(local,rule.get('independent_qualifiers',[])):
                return 'declared_product_topic_alias'
            if entity.get('entity_role') in rule.get('context_entity_roles',[]):
                local_products=[row for row in products if left<=row['start']<right]
                if not local_products:continue
                prefix=question[left:entity['start']]
                for start,end in any_span(prefix,rule.get('context_prepositions',[])):
                    if all(word in {'the','app','application','system'} for word in tokens(prefix[end:])):
                        return 'clause_local_platform_context'
        return None

    def service_linguistic_fit(self,service,text):
        """Score an ambiguous alias from current language, never evidence."""
        profile=self.p.definition.get('service_profiles',{}).get(service,{})
        family=profile.get('family','')
        family_cues={
            'remittance':['remittance','money transfer','حوالة','حوالات','صرف حوالة','7awala','7awalet'],
            'wallets':['wallet','e-wallet','mobile wallet','محفظة','ma7faza'],
        }
        return len(any_span(text,family_cues.get(family,[])))

    def channel_replacements(self,text,channels):
        """Return typed (new, old) channel switches from current wording."""
        if any_span(text,['each route','each channel','both routes','both channels',
                          'each one','each of them','both options','compare both',
                          'not only','but also','كل طريق','كل قناة','الطريقين','القناتين',
                          'كل واحد','كل واحدة','في كل واحد','في كل واحدة','الاتنين','الاثنين',
                          'ليس فقط','مش بس','ولكن أيضا','لكن كمان']):return []
        ordered=sorted(channels,key=lambda row:(row['start'],row['end']))
        result=[]
        for left,right in zip(ordered,ordered[1:]):
            between=shadow(text[left['end']:right['start']])[0]
            prefix=shadow(text[max(0,left['start']-24):left['start']])[0]
            if re.search(r'\b(?:instead\s+of|rather\s+than)\b|(?<!\w)بدل(?!\w)',between,re.I):
                result.append((left['channel'],right['channel'],left['start'],right['end']))
            elif re.search(r'(?<!\w)(?:مش|ليس|not|mesh|msh)\s+(?:من\s+|through\s+|via\s+|from\s+)?$',between,re.I):
                result.append((left['channel'],right['channel'],left['start'],right['end']))
            elif re.search(r'\b(?:but|لكن|bas)\b',between,re.I) and re.search(r'\b(?:not|mesh|msh)\b|(?<!\w)مش(?!\w)',prefix,re.I):
                result.append((right['channel'],left['channel'],left['start'],right['end']))
        return unique(result)
    def hits(self,text):
        hits={k:unique(any_span(text,pp)) for k,pp in self.features.items()}
        # Discourse operators such as بالنسبة contain the letters of a rate
        # noun; that substring is not a monetary request.
        hits['fee']=[(a,b) for a,b in hits.get('fee',[]) if not any(x<=a and b<=y for x,y in hits.get('followup',[]))]
        return hits
    def modifier_only(self,text):
        chars=list(text)
        for key in ['fee','comparison','followup','presentation']:
            for a,b in any_span(text,self.features.get(key,[])):chars[a:b]=' '*(b-a)
        ignored={'what','the','is','are','and','of','in','for','please','tell','me','that','amount','it','about','including','minimum','maximum','percentage','rate','egp','how','much','whether','does','apply','needed','at','each','one','i','am','comparing','customer','must','be','itself','valid','original','كام','كم','ده','دي','المبلغ','وهل','ايه','هل','ما','هو','على','في','كل','واحد','قد','3ayez','a3raf','عليها','من','عن','لا','لأ','الحد','حد','الادني','ادني','نسبه','موضحا','الي','نفسه','نفس','اصل','ساريه','لازم','تكون','بخصوص','صحيح','كلامه','العميل','الزبون','قال','وراني','بعمل','اقدر','ينفع','المسموح','fel','rad','da','de','el','wel','kaman','mablagh','a2al','nesbet','la2'}
        ignored.update({'wallet','service','محفظة','خدمة','عميل','جنيه','جنيها','pounds','kol','taree2','kam','kaam','do','this','was','we'})
        ignored={f for value in ignored for f in forms(value)}
        def functional(t):
            return bool(forms(t)&ignored) or len(t)>2 and t[0] in 'وبفل' and t[1:] in ignored
        return not any(not functional(t) and not t.isdigit() for t in tokens(''.join(chars)))
    def goals(self,text,masked):
        h=self.hits(masked)
        from linguistic_spans import financial_ordinal_spans
        h['initial']=unique(h.get('initial',[])+financial_ordinal_spans(masked,h.get('deposit',[])))
        has=lambda k:bool(h.get(k));out=[]
        def add(i,*features):
            ss=unique(x for k in features for x in h.get(k,[]))
            if ss:out.append({'intent_id':i,'predicate_spans':ss,'head_spans':h.get(features[0],ss),'support_features':list(features),'commit_basis':'current_clause_predicate_components'})
        image=has('image')
        if image:add('image_permission','image','permission')
        if has('code'):add('transaction_code','code')
        if image:
            if has('identity') and not any_span(masked,['transaction ID','reference ID','complaint ID']):add('identity','identity')
            explicit_phone_owner=bool(any_span(masked,[
                'mobile-line ownership','line ownership','whose name','registered in the customer',
                'registered in the applicant','registered to the customer','registered to the applicant',
                'line being in the customer','line being in the applicant','line must be in',
                'الخط باسم','الرقم باسم','ملكية الخط','صاحب الخط','الخط مسجل باسم',
                'el khat b esm','el raqam b esm','mobile line be in']))
            if has('phone_owner') and explicit_phone_owner:add('phone_ownership','phone_owner')
            if has('existing_wallet'):add('existing_wallet','existing_wallet')
        if not image:
            if has('identity') and not any_span(masked,['transaction ID','reference ID','complaint ID']):add('identity','identity')
            if has('phone_owner'):add('phone_ownership','phone_owner')
            if has('existing_wallet'):add('existing_wallet','existing_wallet')
            if has('documents'):add('documents','documents')
            compound_code=has('code') and any(wb<=ca and not tokens(masked[wb:ca]) for wa,wb in h.get('workflow',[]) for ca,cb in h.get('code',[]))
            if has('workflow') and not compound_code:add('workflow','workflow')
            if compound_code:h['code_subject_context']=h['workflow']
            branch=(has('branch') or has('visit')) and (has('branch_condition') or has('visit')) and not(has('deposit') or has('withdrawal'))
            if branch:add('branch_condition','branch','branch_condition','visit')
        if not(image or has('code')):
            initial=has('initial') or has('activation')
            explicit_charge=bool(any_span(masked,['fee','fees','charge','cost','subscription','رسوم','اشتراك','مصاريف','عمولة']))
            opening_inventory=bool(any_span(masked,[
                'opening checklist','full opening checklist','entire opening checklist','KYC checklist',
                'opening documents','opening paperwork','opening papers',
                'قائمة فتح المحفظة','قائمة مستندات الفتح'
            ]))
            eligibility_bundle=(has('opening') and has('requirements') and not explicit_charge) or bool(any_span(masked,[
                'opening requirements','opening conditions','wallet opening requirements',
                'شروط فتح','ضوابط فتح']))
            opening_checklist=opening_inventory or eligibility_bundle
            withdrawal_amount_minimum=bool(any_span(masked,[
                'minimum cash-out amount','smallest withdrawal','minimum withdrawal amount',
                'أقل مبلغ أسحبه','اقل مبلغ اسحبه','الحد الأدنى لمبلغ السحب','الحد الادنى لمبلغ السحب',
                'a2al mablagh as7abo'
            ]))
            if eligibility_bundle:
                add('eligibility','requirements','opening')
            if has('opening') and not has('workflow') and not opening_checklist:add('opening_fee','opening')
            if initial:add('initial_funding','initial','activation')
            funding_subject=has('balance') or has('initial') or has('activation') or bool(any_span(masked,[
                'amount','sum','money','funds','cash','مبلغ','فلوس','أموال','اموال','نقود','mablagh','floos']))
            if has('balance_disposition') and funding_subject:
                add('balance_treatment','balance_disposition')
                add('initial_funding','balance_disposition')
            if has('deposit') and not initial and not has('balance_disposition') and not has('workflow'):add('deposit_tariff','deposit','fee')
            if has('withdrawal') and not has('workflow') and not withdrawal_amount_minimum:add('withdrawal_tariff','withdrawal','fee')
            minimum_funding=bool(any_span(masked,['minimum deposit','minimum initial','minimum funding','least funding','اقل مبلغ','اقل ايداع','حد ادنى للتفعيل','التمويل الادنى']))
            activation_fee=bool(re.search(
                r'\b(?:activation|activate)\s+(?:fee|charge|cost)\b|\b(?:fee|charge|cost)\s+(?:for\s+)?activation\b'
                r'|(?:رسوم|مصاريف|عمولة)\s+(?:التفعيل|تفعيل)|(?:التفعيل|تفعيل)\s+(?:رسوم|مصاريف|عمولة)',
                shadow(masked)[0],re.I))
            activation_price=(has('activation') and not (has('deposit') or has('withdrawal'))
                              and bool(any_span(masked,['بكام','price','cost'])
                                       or re.search(r'\bhow\s+much\s+(?:(?:is|does|for)\s+)?(?:the\s+)?activation\b',masked,re.I)))
            if initial and (activation_fee or activation_price) and not minimum_funding:add('opening_fee','fee','activation')
            if initial and has('balance') and has('fee') and any_span(masked,['or','whether','ولا','أم','ام','wala']):
                spans_balance=h.get('balance',[])
                out.append({'intent_id':'balance_treatment','predicate_spans':spans_balance,
                            'head_spans':spans_balance,'support_features':['initial_funding_balance_classification'],
                            'commit_basis':'current_clause_predicate_components'})
        if not out:
            heads=any_span(masked,['pay','paying','payment','ادفع','سداد','adfa3'])
            if heads:out.append({'intent_id':'payment','predicate_spans':heads,'support_features':['explicit_payment_head'],'commit_basis':'current_clause_operation_head'})
        # Catalog cues must occur in the current clause. A bare canonical
        # nominal head is also an information request when entity masking
        # leaves no competing predicate (e.g. a product followed by "refund").
        known=set(self.p.adapter)
        for row in self.p.intents:
            iid=row['intent_id']
            if iid in {'other_or_unknown','permission','explanation'} or self.p.adapter.get(iid,{}).get('topic'):continue
            if iid=='general_service_fee' and out:continue
            # A minimum *fee/charge* is an attribute of the requested tariff,
            # not a second synthetic withdrawal-minimum policy. A minimum
            # transaction amount remains a distinct (possibly unsupported)
            # request and is not collapsed into the tariff.
            if iid=='withdrawal_minimum' and has('fee'):continue
            nominal_proof=nominal_catalog_heads(masked,[iid]).get(iid,[])
            proof=list(nominal_proof)
            for key in ['ar_eg_cues','ar_msa_cues','en_cues','franco_eg_cues']:
                for cue in row.get(key,[]):
                    cue_tokens=tokens(cue)
                    nominal=(len(cue_tokens)==1
                             and cue_tokens==tokens(iid.replace('_',' '))
                             and set(tokens(masked))<=set(cue_tokens)|{
                                 'what','about','the','please','explain','tell','me'})
                    if len(cue_tokens)>1 or nominal:
                        proof.extend(spans(masked,cue))
            if proof:out.append({'intent_id':iid,'predicate_spans':unique(proof),
                                 'support_features':['current_nominal_catalog_head' if nominal_proof else 'current_multiword_cue'],
                                 'commit_basis':'current_clause_nominal_catalog_head' if nominal_proof else 'current_clause_multiword_cue'})
        record_fields=transaction_reference_spans(masked)
        if record_fields:
            out.append({'intent_id':'transaction_reference','predicate_spans':record_fields,
                        'support_features':['relational_record_field'],
                        'commit_basis':'current_clause_record_field_composition'})
        merged={}
        for g in out:
            if g['intent_id'] in merged:merged[g['intent_id']]['predicate_spans']=unique(merged[g['intent_id']]['predicate_spans']+g['predicate_spans'])
            else:merged[g['intent_id']]=g
        semantic=infer_clause(text,masked,self.features,self.p.intents,self.p.operators)
        for suppression in semantic['subsumption_spans']:
            goal=merged.get(suppression['intent_id'])
            if not goal:continue
            points=goal.get('head_spans',goal['predicate_spans'])
            keep=[(a,b) for a,b in points if not any(a<y and x<b for x,y in suppression['spans'])]
            if not keep:merged.pop(goal['intent_id'],None)
            else:goal['head_spans']=keep
        for goal in semantic['supplemental_goals']:
            if goal['intent_id'] not in merged:merged[goal['intent_id']]=goal
            else:merged[goal['intent_id']].update(mode=goal.get('mode','information'))
        for intent,mode in semantic['mode_by_intent'].items():
            if intent in merged:merged[intent]['mode']=mode
        # A procedural phrase such as "full cash-out method" asks how to do
        # the operation. It is not also a tariff request without a fee head.
        if 'workflow' in merged and not h.get('fee'):
            merged.pop('deposit_tariff',None);merged.pop('withdrawal_tariff',None)
        # A question about what triggers a branch visit does not request the
        # branch address. The source-bound condition remains its own slot.
        if 'branch_condition' in merged:merged.pop('branch_location',None)
        if 'branch_condition' in merged and 'workflow' in merged:
            markers=any_span(masked,['according to','as per','حسب','وفق','وفقا ل','ضمن'])
            workflow_points=h.get('workflow',[])
            contextual=[point for point in workflow_points if any(
                right <= point[0] and not tokens(masked[right:point[0]]) for left,right in markers)]
            if workflow_points and len(contextual)==len(workflow_points):
                merged.pop('workflow',None)
                h['workflow_purpose_context']=contextual
        # In a requirement question, activation governed by a purpose
        # preposition supplies context. It does not independently ask for
        # funding. Explicit monetary heads keep their separate meaning.
        requirement_intents={'identity','phone_ownership','existing_wallet','documents','image_permission'}
        purpose=bool(re.search(
            r'\b(?:for|during|to)\s+(?:the\s+)?(?:activation|activate|activating)\b'
            r'|(?<!\w)(?:ل(?:تفعيل|لتفعيل)|عند\s+(?:تفعيل|التفعيل))',shadow(masked)[0],re.I))
        monetary=bool(h.get('fee') or any_span(masked,[
            'deposit','funding','amount','money','balance','cash','EGP','إيداع','ايداع','تمويل','مبلغ','فلوس','رصيد','جنيه']))
        if purpose and requirement_intents.intersection(merged) and not monetary:
            merged.pop('initial_funding',None)
            h['activation_purpose_context']=h.get('activation',[])
        if record_fields and 'payment' in merged:
            points=merged['payment'].get('head_spans',merged['payment']['predicate_spans'])
            if points and all(any(a<=x and y<=b for a,b in record_fields) for x,y in points):
                merged.pop('payment')
        valued_fields=valued_record_fields(text,record_fields,semantic['references'])
        if valued_fields and 'transaction_reference' in merged and len(merged)>1:
            points=merged['transaction_reference'].get('head_spans',merged['transaction_reference']['predicate_spans'])
            if points and all(any(a<=x and y<=b for a,b in valued_fields) for x,y in points):
                merged.pop('transaction_reference')
                h['supplied_record_field_context']=valued_fields
        from linguistic_spans import process_context_scope,image_object_identity_spans
        process=process_context_scope(masked,h)
        if process:
            merged.pop('opening_fee',None);merged.pop('initial_funding',None)
            h['explicit_process_context']=[(process['start'],process['end'])]
        attached=image_object_identity_spans(masked,h)
        if attached and h.get('identity') and all(point in attached for point in h['identity']):
            merged.pop('identity',None);h['image_object_context']=attached
        h['_semantic']=semantic
        for goal in semantic['supplemental_goals']:
            if goal['intent_id']=='balance_treatment' and 'semantic_atom:funds_balance_destination' in goal.get('support_features',[]):
                h['balance_disposition']=unique(h.get('balance_disposition',[])+goal['predicate_spans'])
        # Overlapping aliases of the same nominal operation do not create a
        # separate tariff request when its bound head is transaction principal.
        minimum_proofs=[] if any(h.get(key) for key in ['code','image','workflow']) else principal_minimum_proofs(masked,h.get('withdrawal',[]))
        if minimum_proofs:
            tariff=merged.get('withdrawal_tariff')
            if tariff:
                heads=[point for point in tariff.get('head_spans',tariff['predicate_spans']) if not any(
                    proof['span'][0]<=point[0] and point[1]<=proof['span'][1] for proof in minimum_proofs)]
                if not heads:merged.pop('withdrawal_tariff',None)
                else:tariff.update(head_spans=heads,predicate_spans=heads)
            if 'withdrawal_minimum' not in merged:
                points=sorted({point for proof in minimum_proofs for point in [proof['bound'],proof['amount'],proof['operation']]})
                merged['withdrawal_minimum']={'intent_id':'withdrawal_minimum','predicate_spans':points,
                    'head_spans':[proof['operation'] for proof in minimum_proofs],
                    'support_features':['transaction_principal_minimum'],'commit_basis':'current_clause_quantity_head_binding'}
        if not merged:
            for iid,proof in catalog_nominal_proofs(masked,self.p.intents).items():
                if iid=='withdrawal_minimum' and has('fee'):continue
                merged[iid]={'intent_id':iid,'predicate_spans':proof,'head_spans':proof,
                             'support_features':['current_nominal_catalog_head'],
                             'commit_basis':'current_clause_nominal_catalog_head'}
        return list(merged.values()),h
    def role(self,text,h):
        # Omission instructions govern the response scope.  They are distinct
        # from negative business propositions ("the line must not already have
        # a wallet"), which remain requested facts to evaluate.
        if response_exclusion(text):return 'excluded'
        if h.get('additive_negation'):return 'requested'
        # Response-scope nouns can carry a postfix necessity denial:
        # “workflow steps are not required”. This excludes only the adjacent
        # recognized scope. It is deliberately not a general business-policy
        # negation rule (for example, “identity is not required” is a claim).
        postfix_denial=bool(re.search(
            r'(?:\b(?:is|are|was|were)\s+not\s+(?:required|needed|requested)\b|'
            r'\b(?:mesh|msh)\s+(?:matloob|matlooba|laazem|lazem)\b|'
            r'(?<!\w)(?:غير\s+مطلوب[ةه]?|ليست?\s+مطلوب[ةه]?|مش\s+(?:مطلوب[ةه]?|لازم[ةه]?))(?!\w))',
            shadow(text)[0],re.I))
        if postfix_denial and any(h.get(key) for key in ('workflow','documents','code','image')):return 'excluded'
        # A negative business requirement is a requested proposition, not an
        # instruction to omit that topic from the answer.
        if h.get('existing_wallet') and any_span(text,['without','من غير','بدون']) and not any_span(text,['leave out','exclude','استبعد','من غير ما','without explaining']):return 'requested'
        if nominal_scope_omission(text,h.get('fee',[])):return 'excluded'
        if re.match(r'^\s*لا\s+من\b',shadow(text)[0]):return 'excluded'
        # A recognized procedural noun phrase can be excluded without a verb
        # ("No full walkthrough" / "لا شرح كامل للخطوات"). Keep this
        # bounded to the recognized workflow predicate; unknown negative
        # nominals remain unresolved rather than becoming silent exclusions.
        if h.get('workflow') and re.match(r'^\s*(?:no\b|لا\b|بدون\b|دون\b|من\s+غير\b)',shadow(text)[0]):return 'excluded'
        if h.get('exclude') or h.get('exclusion_tail'):return 'excluded'
        value=shadow(text)[0].strip(' ,،:؛;')
        if re.match(r'^(?:(?:this is|i am|please|but)\s+)?(?:no\b|not\b|neither\b|rather than\b|instead of\b|do not\b|ليس\b|وليس\b|بدل\b|لا\s+(?:اسال|اريد|احتاج|اطلب)|ما\s+\S+ش\b|mat[a-z0-9]+sh\b)',value):return 'excluded'
        if re.match(r'^(?:no\b|not\b|neither\b|mesh\b|msh\b|مش\b|بدل\b|لا\b(?=.*\bولا\b)|la\b(?=.*\bwala\b)|دون\b|من غير\b)',value):return 'excluded'
        return 'requested'
    def bound_services(self,frame,goal):
        entities=frame['entities'];heads=goal.get('head_spans',goal['predicate_spans'])
        if len(set(e['service_id'] for e in entities))<2 or len({g['intent_id'] for g in frame['goals']})<2 or not heads:return frame['services']
        center=frame['a']+sum(a+b for a,b in heads)/(2*len(heads));distances={}
        for e in entities:
            distance=min(abs(center-e['start']),abs(center-e['end']))
            distances[e['service_id']]=min(distance,distances.get(e['service_id'],float('inf')))
        return [s for s,d in distances.items() if d==min(distances.values())]

    def bind_operation_procedure_modifiers(self,question,masked,frames,context):
        """Bind a pure distributive procedure modifier to current operations.

        Only declared operation modes and nominal current-clause titles may
        supply antecedents. Status questions, unknown scope and policy nouns
        cannot be silently converted into procedural questions.
        """
        titles={row['intent_id']:[row['intent_id'],row.get('label_en','')]
                for row in self.p.intents}
        joins={'versus','vs','and','و','attached_additive',',','،'}
        for index,frame in enumerate(frames):
            if (frame['role']!='requested' or frame['entities'] or not frame['goals']
                    or any(goal['intent_id']!='workflow' for goal in frame['goals'])):continue
            a,b=frame['a'],frame['b'];text=masked[a:b]
            refs=any_span(text,['each','every','both','كل','لكل','الاتنين'])
            if not refs:continue
            chars=list(text)
            for left,right in refs+frame['hits'].get('workflow',[]):
                chars[left:right]=' '*(right-left)
            grammar={'explain','describe','show','tell','me','please','the','for','of','all',
                     'اشرح','وضح','اذكر','كل','لكل','واحد','واحدة','واحده'}
            if not set(tokens(''.join(chars)))<=grammar:continue
            antecedents=[];cursor=index-1
            while cursor>=0:
                previous=frames[cursor]
                if previous['role']!='requested' or not previous['goals']:break
                antecedents.insert(0,previous)
                if previous['join'].strip().casefold() not in joins:break
                cursor-=1
            bindings={(service,goal['intent_id']) for previous in antecedents
                      for goal in previous['goals'] for service in self.bound_services(previous,goal)}
            if len(bindings)<2:continue
            eligible=True
            for previous in antecedents:
                local=masked[previous['a']:previous['b']]
                for goal in previous['goals']:
                    entry=self.p.adapter.get(goal['intent_id'],{})
                    if (entry.get('mode_routes',{}).get('procedure_query')!='source_evidence'
                            or goal.get('mode') not in {None,'information','procedure_query'}
                            or not nominal_catalog_heads(local,titles.get(goal['intent_id'],[]))):
                        eligible=False
            if not eligible:continue
            proof=mark(question,a,b,'procedure_mode_modifier')
            for previous in antecedents:
                for goal in previous['goals']:
                    goal['mode']='procedure_query'
                    goal['mode_evidence_spans']=[proof]
            frame['goals']=[]
            context.append({'feature':'distributive_operation_procedure_modifier','span':proof,
                            'bindings':[{'service_id':service,'intent_id':intent} for service,intent in sorted(bindings)]})
    def comparison_groups(self,question,masked,frames,requests,cues):
        """A comparison head governs operands, not every later matching intent."""
        groups=[];active=None;prior=None
        connectors=['with','versus','vs','against','compared with','compared to','مع','مقابل','بالمقارنة','مقارنه مع']
        for frame in frames:
            if frame['role']!='requested':active=None;continue
            a,b=frame['a'],frame['b'];text=question[a:b]
            heads=[mark(question,a+x,a+y,'comparison_head') for x,y in unique(any_span(masked[a:b],cues))]
            gap_start=prior['b'] if prior else 0
            if not heads and not independent_request_head(text) and not re.search(r'[.;؛?!؟]',question[gap_start:a]):
                heads=[mark(question,gap_start+x,gap_start+y,'comparison_head') for x,y in unique(any_span(masked[gap_start:a],cues))]
            joined_contrast=frame['join'].strip().casefold() in {'versus','vs'}
            starts_connector=joined_contrast or any(x==len(text)-len(text.lstrip()) for x,y in any_span(text,connectors))
            hard_boundary=frame['join'] in {';','؛','.','?','؟'}
            continuation=(starts_connector or not hard_boundary and not independent_request_head(text))
            if heads:
                trailing=bool(re.match(r'^\s*(?:i\s+am\s+comparing|انا\s+بقارن|انا\s+اقارن)\b',shadow(text)[0]))
                compatible=prior and {g['intent_id'] for g in prior['goals']} & {g['intent_id'] for g in frame['goals']}
                if trailing and not (compatible and len({binding_subject_key(s) for s in prior['services']})>1):
                    active=None;prior=frame;continue
                if active is not None and continuation and starts_connector:
                    active['frames'].append(frame);active['heads'].extend(heads)
                else:
                    members=([prior,frame] if prior and (joined_contrast or trailing and compatible
                             and len({binding_subject_key(s) for s in prior['services']})>1) else [frame])
                    active={'frames':members,'heads':heads};groups.append(active)
            elif active is not None and continuation:
                active['frames'].append(frame)
            else:active=None
            prior=frame
        committed=[]
        for group in groups:
            members=[]
            for request in requests:
                supports=request.get('supporting_clause_spans',[request['clause_span']])
                if any(s['start']==f['a'] and binding_subject_key(binding)==subject_key(request)
                       for s in supports for f in group['frames'] for binding in f['services']):members.append(request)
            if len({subject_key(r) for r in members})<2:continue
            spans_=unique((f['a'],f['b']) for f in group['frames'])
            spans_+=unique(tuple(s) for f in group['frames'] for s in f.get('list_continuation_spans',[]))
            spans_+=unique(tuple(s) for f in group['frames'] for s in f.get('binding_prefix_spans',[]))
            spans_=sorted(set(spans_))
            left=min([x for x,y in spans_]+[s['start'] for s in group['heads']]);right=max(y for x,y in spans_)
            committed.append({'group_id':'C'+str(len(committed)+1),'span':mark(question,left,right,'comparison_group'),
                              'head_spans':group['heads'],'operand_spans':[mark(question,x,y,'comparison_operand') for x,y in spans_],
                              'request_ids':[r['request_id'] for r in members],
                              'subject_keys':unique(subject_key(r) for r in members)})
        return committed
    def assumed_operation_only(self,raw,frame,goal,start,stop):
        """The requested action is not an extra customer-policy condition.

        Only known operation/entity/channel words and grammatical material are
        removed. Numeric, negative and unrecognized restrictions remain literal.
        Source/version/channel eligibility is still checked independently.
        """
        if goal['intent_id'] not in TARIFFS|{'opening_fee','initial_funding','balance_treatment'}:return False
        if not any(start<=a<stop for a,b in goal.get('head_spans',goal['predicate_spans'])):return False
        fragment=raw[start:stop]
        if re.search(r'(?<!\w)[0-9٠-٩]+(?:[.,٫][0-9٠-٩]+)?(?!\w)',fragment):return False
        if any_span(fragment,self.features['negation_proposition']+['not','never','without','لا','ليس','ما','مش','بدون','من غير','mesh','msh']):return False
        chars=list(raw)
        points=goal['predicate_spans']+any_span(raw,['money','funds','cash','wallet','account','فلوس','اموال','نقود','محفظة','حساب','if','لو','law','اذا','إذا','to','from','into','through','via','then','more','now','would','will','could','can','want','just','fe','fel'])
        points += [(r['start']-frame['a'],r['end']-frame['a']) for r in frame['entities']+frame['channels']]
        if goal.get('antecedent_clause'):points+=any_span(raw,['after that','afterwards','بعدها'])
        for a,b in points:
            left,right=max(start,a),min(stop,b)
            if left<right:chars[left:right]=' '*(right-left)
        return self.modifier_only(''.join(chars[start:stop]))
    def operator_commitments(self,question,semantic,requests,excluded,claims,context,edges):
        """Lexical operator matches are proposals, not committed meanings."""
        intents={r['intent_id'] for r in requests}
        references=semantic['references']
        live={'transaction_status','transaction_cancel','refund_status','refund','complaint_create','complaint_status','callback'}
        guards={
            'O01':bool(excluded),
            'O03':any(r.get('basis')=='current_discontinuous_negative_operation' for r in semantic['operator_annotations']) or bool(re.search(r'(?<!\w)(?:مش|mesh|msh)(?!\w)',question,re.I)),
            'O08':len({(subject_key(r),r['intent_id'],tuple(r['channels'])) for r in requests})>1,
            'O10':any(e['type']=='comparison' for e in edges),
            'O11':any(e['type'] in {'alternative','alternative_outcome'} for e in edges) or any(r['mode']=='compare_alternatives' and len(r['channels'])>1 for r in requests),
            'O13':bool(context),
            'O14':bool(claims),
            'O15':any(r['hypothetical'] for r in requests),
            'O20':'workflow' in intents,
            'O21':'branch_condition' in intents,
            'O22':any('resolved' in r['commit_basis'] or r.get('channel_antecedent_requests') for r in requests+excluded),
            'O23':any(r.get('antecedent_turn') or r.get('antecedent_clause') for r in requests+excluded),
            'O28':any(r['intent_id'] in TARIFFS and r['channels'] for r in requests),
            'O35':'response_draft' in intents and bool(claims),
            'O37':bool(intents&live),
            'O38':'complaint_resolution_confirmation' in intents,
            'O39':'complaint_resolution_confirmation' in intents,
            'O40':any(o.get('kind')=='customer_desired_time' for o in semantic['obligations']),
            'O41':bool(references),
            'O42':any(r.get('domain_id')=='retail_operations' for r in requests+excluded),
            'O43':bool(any_span(question,['cache','cached','كاش ميموري'])) and bool(any_span(question,['cash','كاش نقدي'])),
            'O45':'response_draft' in intents and any(o.get('kind')=='response_constraint' for o in semantic['obligations']),
        }
        kept={};rejected=[]
        for row in semantic['operator_annotations']:
            row=dict(row)
            iid=row['operator_id'];s=row['span']
            inside_claim=any(c['span']['start']<=s['start'] and s['end']<=c['span']['end'] for c in semantic.get('reported_assertions',claims))
            accept=guards.get(iid,True) and (not inside_claim or iid in {'O14','O27','O41'})
            # Egyptian بس before an interrogative is a contrastive connector,
            # rather than an instruction to narrow the answer to one topic.
            if iid=='O05' and shadow(s['text'])[0]=='بس' and re.match(r'\s*(?:هل|هو|هي)\b',question[s['end']:]):accept=False
            if iid=='O05' and any(a<=s['start'] and not re.search(r'[.;؛?!؟]',question[b:s['start']]) for a,b in any_span(question,self.features['additive_negation'])):accept=False
            if iid=='O13' and accept:
                # A context cue cannot absorb the intervening employee request
                # or a separate exclusion merely because all occur in one turn.
                proved=[c['span'] for c in context if c.get('span') and c['span']['start']<s['end'] and s['start']<c['span']['end']]
                if not proved:accept=False
                else:s={**min(proved,key=lambda v:(v['start'],v['end'])),'role':'operator'};row['span']=s;row['basis']='bounded_current_context_frame'
            if not accept:rejected.append({**row,'disposition':'candidate_not_entailed_by_current_graph'});continue
            if iid not in kept:kept[iid]={**row,'support_spans':[s]}
            elif s not in kept[iid]['support_spans']:kept[iid]['support_spans'].append(s)
        if excluded and 'O01' not in kept:
            row=next(r for r in self.p.operators if r['operator_id']=='O01');s=excluded[0]['clause_span']
            kept['O01']={'operator_id':'O01','meaning':row['name'],'span':s,'support_spans':[s],'basis':'typed_excluded_request'}
        derived=[]
        if any(e['type']=='coordination' for e in edges):derived.append(('O08','typed_requested_coordination'))
        if 'workflow' in intents and any_span(question,['بالترتيب','in order','step by step']):derived.append(('O19','current_ordered_procedure_request'))
        for iid,basis in derived:
            if iid not in kept:
                row=next(r for r in self.p.operators if r['operator_id']==iid)
                s=next(r['clause_span'] for r in requests if iid!='O19' or r['intent_id']=='workflow')
                kept[iid]={'operator_id':iid,'meaning':row['name'],'span':s,'support_spans':[s],'basis':basis}
        return list(kept.values()),rejected
    def plan(self,question,cid,sid):
        p=self.p;previous=p.store.get_business_context(cid,sid) or {};p.turn+=1
        entities,entity_context=filter_predicate_entity_mentions(question,p.entities(question),self.features)
        foreign_entities=[]
        for name in p.catalog['qualifiers']['unsupported_named_service']:
            for a,b in spans(question,name):
                if any(e['start']<=a and b<=e['end'] for e in entities):continue
                foreign_entities.append({'service_id':'unsupported_named:'+name,'provider_name':name,**mark(question,a,b,'unsupported_named_provider'),'entity_role':'unsupported_named_provider'})
        channels=[c for c in p.channel_hits(question) if not any(e['start']<=c['start'] and c['end']<=e['end'] for e in entities)]
        prior_channels=unique(channel for row in previous.get('request_references',[])
                              for channel in row.get('channels',[]))
        other_channel_reference=bool(any_span(question,[
            'the other channel','other channel','channel el tany','el channel el tany',
            'القناة التانية','القناة الأخرى']))
        if other_channel_reference and len(prior_channels)==1:
            prior_refs=[row for row in previous.get('request_references',[])
                        if row.get('service_id') and row.get('intent_id') and row.get('channels')]
            alternatives=set()
            if len({(row['service_id'],row['intent_id']) for row in prior_refs})==1:
                service,intent=prior_refs[-1]['service_id'],prior_refs[-1]['intent_id']
                topic=p.adapter.get(intent,{}).get('topic')
                alternatives={f.get('required_channel') for f in p.definition.get('facts',[])
                              if f.get('service_id')==service and topic in f.get('selection_tags',[])
                              and f.get('required_channel') and f.get('required_channel') not in prior_channels}
            if len(alternatives)==1:
                start,end=(any_span(question,['the other channel','other channel','channel el tany','el channel el tany',
                                               'القناة التانية','القناة الأخرى']) or [(0,len(question))])[0]
                channels.append({'channel':next(iter(alternatives)),**mark(question,start,end,'channel'),
                                 'match_basis':'typed_other_channel_complement'})
        if len(prior_channels)==1:
            for a,b in any_span(question,['the machine','that machine','the counter','counter',
                                          'the prior route','the old route','الماكينة','الشباك','شباك',
                                          'المسار السابق','المسار القديم']):
                prefix=shadow(question[max(0,a-24):a])[0]
                if re.search(r'\b(?:instead\s+of|rather\s+than|not\s+from)\b|(?<!\w)(?:بدل|مش\s+من|ليس\s+من)(?!\w)',prefix,re.I):
                    channels.append({'channel':prior_channels[0],**mark(question,a,b,'channel'),
                                     'match_basis':'typed_same_session_channel_antecedent'})
        quotations=[mark(question,m.start(),m.end(),'claim') for m in QUOTE_RE.finditer(question)]
        numeric_groups=numeric_field_groups(question)
        masked=list(question)
        for e in entities+foreign_entities:
            for i in range(e['start'],e['end']):masked[i]=' '
        for q in quotations:
            for i in range(q['start'],q['end']):masked[i]=' '
        masked=''.join(masked)
        global_semantics=infer_clause(question,masked,self.features,p.intents,p.operators)
        temporal_scopes=exclusive_temporal_scopes(question,excluded_spans=(
            [] if global_semantics.get('claim_verification') else [(q['start'],q['end']) for q in quotations]))
        unresolved=[];context=[];claims=global_semantics['user_claims']
        actor_frames=global_semantics['actor_frames'];obligations=global_semantics['obligations']
        context.extend({'feature':'predicate_subject','span':dict(e,role='context_only')} for e in entity_context)
        context.extend(global_semantics['context_mentions'])
        event_foreign=[e for e in foreign_entities if any(
            q['event_span']['start']<=e['start'] and e['end']<=q['event_span']['end'] for q in temporal_scopes)]
        context.extend({'feature':'temporal_condition_entity','entity_id':e['service_id'],
                        'span':dict(e,role='condition_context')} for e in event_foreign)
        foreign_entities=[e for e in foreign_entities if e not in event_foreign]
        # A platform can identify a procedure owner only when the current turn
        # actually asks for a procedure and the source-bound procedure metadata
        # maps that platform to exactly one service.  The platform itself stays
        # contextual and cannot become a financial provider.
        procedural_turn=bool(any_span(masked,self.features.get('workflow',[])+
                                      self.features.get('registration_context',[])+
                                      ['source order','sequence','التسلسل','الترتيب']))
        resolved_platforms=[];regions={};local_goals={}
        named_products=[entity for entity in entities if entity.get('entity_role')=='service']
        temporal_entities={(e['start'],e['end'],e['service_id']) for e in entities
                           if any(q['event_span']['start']<=e['start'] and e['end']<=q['event_span']['end']
                                  for q in temporal_scopes)}
        named_products=[e for e in named_products if (e['start'],e['end'],e['service_id']) not in temporal_entities]
        for entity in entities:
            if (entity['start'],entity['end'],entity['service_id']) in temporal_entities:continue
            key=(entity['start'],entity['end'],entity['service_id'])
            regions[key]=self.entity_clause_region(question,entity,entities+foreign_entities)
        if procedural_turn:
            for entity in entities:
                if entity.get('entity_role')=='service':continue
                peers={row['service_id'] for row in entities
                       if (row['start'],row['end'])==(entity['start'],entity['end'])}
                if len(peers)>1:continue
                owner=self.procedure_service_for_platform(entity['service_id'])
                if owner:
                    key=(entity['start'],entity['end'],entity['service_id']);left,right=regions[key]
                    if (left,right) not in local_goals:
                        local_goals[left,right]=self.goals(question[left:right],masked[left:right])[0]
                    ids={goal['intent_id'] for goal in local_goals[left,right]}
                    if 'workflow' not in ids:continue
                    if any(intent not in {'workflow','branch_condition'} and not p.adapter.get(intent,{}).get('topic')
                           for intent in ids):continue
                    explicit={row['service_id'] for row in named_products if left<=row['start']<right}
                    if explicit and explicit!={owner}:continue
                    if (not explicit and any_span(question,self.features.get('followup',[]))
                            and len(previous.get('services',[]))==1 and owner not in previous['services']):continue
                    resolved_platforms.append({**entity,'service_id':owner,'entity_role':'service',
                                               'source_platform_id':entity['service_id'],
                                               'match_basis':'source_bound_procedure_mapping'})
                    context.append({'feature':'procedure_platform_context','entity_id':entity['service_id'],
                                    'span':dict(entity,role='context_only')})
        products=named_products+resolved_platforms
        replacements={(row['start'],row['end'],row['source_platform_id']):row for row in resolved_platforms}
        active_entities=[]
        for e in entities:
            key=(e['start'],e['end'],e['service_id'])
            if key in temporal_entities:
                context.append({'feature':'temporal_condition_entity','entity_id':e['service_id'],'span':dict(e,role='condition_context')})
                continue
            if key in replacements:
                active_entities.append(replacements[key]);continue
            reason=self.catalog_entity_is_context(question,e,regions[key],products) if e['entity_role']!='service' else None
            if reason:
                context.append({'feature':reason,'entity_id':e['service_id'],'span':dict(e,role='context_only')})
            else:active_entities.append(e)
        global_services=unique(e['service_id'] for e in active_entities)
        # Ambiguous aliases retain every candidate until actual clause context or
        # a same-session antecedent resolves one. Never use output fact success.
        for e in active_entities:
            peers={x['service_id'] for x in active_entities if x['start']==e['start'] and x['end']==e['end']}
            if len(peers)>1:
                prior=set(previous.get('services',[]))&peers
                if len(prior)==1:
                    active_entities=[x for x in active_entities if (x['start'],x['end'])!=(e['start'],e['end']) or x['service_id'] in prior]
                else:
                    clause_left,clause_right=regions[(e['start'],e['end'],e['service_id'])]
                    local_text=question[clause_left:e['start']]+' '*(e['end']-e['start'])+question[e['end']:clause_right]
                    fits={service:self.service_linguistic_fit(service,local_text) for service in peers}
                    best=max(fits.values()) if fits else 0
                    capable={service for service,score in fits.items() if score==best and score>0}
                    # Observed topic coverage is not proof of service identity.
                    # Missing catalog evidence cannot disqualify another owner
                    # of an unqualified brand name.
                    if len(capable)==1:
                        active_entities=[x for x in active_entities if (x['start'],x['end'])!=(e['start'],e['end']) or x['service_id'] in capable]
                        continue
                    unresolved.append({'kind':'ambiguous_service_name','span':mark(question,e['start'],e['end'],'alternative'),'alternatives':sorted(peers)})
        ambiguous_spans={(x['span']['start'],x['span']['end']) for x in unresolved
                         if x.get('kind')=='ambiguous_service_name' and x.get('span')}
        active_entities=[x for x in active_entities if (x['start'],x['end']) not in ambiguous_spans]
        global_services=unique(e['service_id'] for e in active_entities)
        foreign=unique(e['provider_name'] for e in foreign_entities)
        # Operators cut scopes BEFORE ellipsis/channel inheritance. This is the
        # shared correction for the previous positive-frame mutation defect.
        breaks=[]
        pattern=r';|؛|:|[؟?]|(?<!\d)[.,،](?!\d)|\b(?:and|but|alongside|whereas|also)\b|\bas well as\b|(?:^|\s)(?:لكن|ولكن)(?=\s)|\s+w\s+|\sو\s+'
        for m in re.finditer(pattern,question,re.I):
            if not any(q['start']<=m.start()<q['end'] for q in quotations):breaks.append((m.start(),m.end(),m.group()))
        # Contrast joins independently specified service-operation operands.
        # Keep an entity list with one shared predicate intact; split only
        # when BOTH adjacent operands have their own current-clause predicate.
        contrasts=[m for m in re.finditer(r'\b(?:versus|vs)\b',question,re.I)
                   if not any(e['start']<=m.start()<e['end'] for e in entities)
                   and not any(q['start']<=m.start()<q['end'] for q in quotations)]
        for index,contrast in enumerate(contrasts):
            left=max([0]+[stop for start,stop,_ in breaks if stop<=contrast.start()]
                     +([contrasts[index-1].end()] if index else []))
            right=min([len(question)]+[start for start,stop,_ in breaks if start>=contrast.end()]
                      +([contrasts[index+1].start()] if index+1<len(contrasts) else []))
            operands=[(left,contrast.start()),(contrast.end(),right)]
            if all(any(start<=e['start']<stop for e in active_entities)
                   and self.goals(question[start:stop],masked[start:stop])[0]
                   for start,stop in operands):
                breaks.append((contrast.start(),contrast.end(),contrast.group()))
        # Franco ``bas`` is ambiguous between “only” and contrastive “but”.
        # Treat it as a polarity reset only when a negative left channel and a
        # distinct right channel make the contrast explicit.
        for m in re.finditer(r'\bbas\b|(?<!\w)بس(?!\w)',masked,re.I):
            left=[c for c in channels if c['end']<=m.start()]
            right=[c for c in channels if c['start']>=m.end()]
            left_bound=max([x for x,y,label in breaks if x<m.start()]+[0])
            negative=bool(re.search(r'\b(?:not|mesh|msh)\b|(?<!\w)مش(?!\w)',masked[left_bound:m.start()],re.I))
            if negative and left and right and not any(q['start']<=m.start()<q['end'] for q in quotations):
                breaks.append((m.start(),m.end(),'contrast_reset'))
        comparison_cues=self.features['comparison']+p.catalog['qualifiers']['comparison_reference']+['comparing']
        comparison_heads=any_span(masked,comparison_cues)
        if comparison_heads:
            first_head=min(x for x,y in comparison_heads)
            independent=r'(?:(?:separately|then|also|now)\s+)?(?:explain\b|tell\s+me\b|show\s+me\b|give\s+me\b|check\b|describe\b|what\s+(?:is|are|does)\b|how\s+(?:much|does|do)\b|اشرح\b|وضح\b|هل\b)'
            for m in re.finditer(independent,masked,re.I):
                if m.start()>first_head and any(e['end']<=m.start() for e in active_entities+foreign_entities):
                    breaks.append((m.start(),m.start(),'independent_request_head'))
        # Attached waw is a conjunction only before a recognized linguistic
        # head/entity.  It is not a universal removable word prefix (وراني).
        for m in re.finditer(r'\sو(?!لا\b)(?=\S)',question):
            tail=masked[m.end():]
            normalized=shadow(tail)[0].lstrip()
            aliases=[shadow(v)[0] for pp in self.features.values() for v in pp]
            starts_feature=any(normalized==v or normalized.startswith(v+' ') or normalized.startswith(v+'،') for v in aliases if v)
            starts_entity=any(e['start']==m.end() for e in active_entities)
            # A recognized full verb is atomic too (وصلت is not و + صلت).
            whole=shadow(question[m.start()+1:])[0].split()
            atomic_words={shadow(v)[0] for key in ['status','display_event'] for v in ATOMS[key] if len(tokens(v))==1}
            atomic_verb=bool(whole and whole[0].strip('،,;؛؟?') in atomic_words)
            if (starts_feature or starts_entity) and not atomic_verb and not any(q['start']<=m.start()<q['end'] for q in quotations):breaks.append((m.start(),m.end(),'attached_additive'))
        for key in ['exclude','correction']:
            for a,b in any_span(masked,self.features[key]):
                if key=='exclude' and shadow(masked[a:b])[0].strip() in {'not','mesh','msh','mish','مش'}:continue
                if a>0:breaks.append((a,a,'scope_operator'))
        distributive_alternatives=any_span(masked,[
            'each route','each channel','each one','both routes','both channels','both of them',
            'كل طريق','كل قناة','كل قناه','كل واحد','كل واحدة','كل واحده','الطريقين','القناتين','الاتنين'
        ])
        for a,b in any_span(masked,['rather than','instead of','بدل','without','دون','من غير','لا أسأل','لا اسال','لا أطلب','لا اطلب','not asking','not requesting','not about','mesh bas2al 3an','msh bas2al 3an']):
            operator=shadow(masked[a:b])[0].strip()
            if operator in {'rather than','instead of','بدل'} and any(x>=b for x,y in distributive_alternatives):
                continue
            if a>0:breaks.append((a,a,'scope_operator'))
        for m in re.finditer(r'\b(?:not|mesh|msh)\b|(?<!\w)مش(?!\w)',masked,re.I):
            if any_span(masked[m.start():],self.features['additive_negation']):continue
            tail_goals=self.goals(question[m.end():],masked[m.end():])[0]
            after_channels=[c for c in channels if c['start']>=m.end()]
            if not tail_goals and not after_channels:continue
            breaks.append((m.start(),m.start(),'polarity_operator'))
        ranges=[];start=0;join='start'
        for a,b,label in sorted(set(breaks)):
            if a<start:continue
            if question[start:a].strip():ranges.append((start,a,join))
            start=b;join=label
        if question[start:].strip():ranges.append((start,len(question),join))
        frames=[];pending=[];pending_spans=[];last_services=[];considered=[];pending_channel_scopes=[];intent_focus={}
        nonrestrictive_modifiers=[]
        task_services=[];pending_task_goals=None;reported_projection=None
        quoted_projections=[]
        for claim in global_semantics.get('reported_assertions',[]):
            span=claim.get('span',{})
            if not span or not claim.get('envelope'):continue
            value=span.get('text','')
            projected,_=self.goals(value,value)
            claim_entities=[e for e in active_entities if span['start']<=e['start']<span['end']]
            quoted_projections.append({'claim':claim,'goals':projected,
                                       'services':unique(e['service_id'] for e in claim_entities)})
        references=previous.get('mentioned_services',previous.get('services',[]))
        all_history=previous.get('comparison_services',references)
        provider_ellipsis=additive_provider_reference(question,[(e['start'],e['end']) for e in active_entities])
        fronted_contexts=fronted_process_contexts(question,[(e['start'],e['end']) for e in active_entities+foreign_entities],
                                                 [(c['start'],c['end']) for c in channels],self.features)
        head_context=None
        for a,b,join in ranges or [(0,len(question),'start')]:
            text=question[a:b];localmasked=masked[a:b];h=self.hits(localmasked)
            binding_prefix_spans=[]
            comparison=bool(any_span(localmasked,comparison_cues))
            role=self.role(text,h)
            ee=[e for e in active_entities+foreign_entities if a<=e['start']<b];ss=unique(e['service_id'] for e in ee)
            cc=[c for c in channels if a<=c['start']<b]
            if not ee and any(a<=left<b for left,right in ambiguous_spans):
                # An explicitly named but unresolved subject cannot inherit
                # an unrelated provider from the rest of the question.
                context.append({'feature':'unresolved_named_subject','span':mark(question,a,b,'unresolved_subject')})
                continue
            parents=[f for f in frames if f['role']=='requested' and f['goals']]
            preservation=binding_preservation_directive(text)
            bound_scopes={(service,g['intent_id']) for parent in parents
                          for service in parent['services'] for g in parent['goals']}
            if preservation and len(bound_scopes)>=2:
                obligations.append({'kind':'request_binding_preservation','span':mark(question,a,b,'constraint'),
                                    'bound_scopes':sorted(bound_scopes)})
                context.append({'feature':'request_binding_preservation','span':mark(question,a,b,'context_only')})
                continue
            if (entity_nonrestriction(text,[(e['start']-a,e['end']-a) for e in ee])
                    and ss and parents and set(ss)<=set(parents[-1]['services'])):
                context.append({'feature':'nonrestrictive_entity_reference','span':mark(question,a,b,'context_only')})
                continue
            comparison_context=bool(any_span(question[:a],self.features.get('comparison',[]))
                                    or parents and len(set(parents[-1]['services']))>1)
            if entity_omission(text,[(e['start']-a,e['end']-a) for e in ee],comparison_context):
                if parents:
                    target_group=task_group(question,parents[-1]['a'])
                    goals=[]
                    for parent in parents:
                        if task_group(question,parent['a'])!=target_group:continue
                        for source_goal in parent['goals']:
                            if any(g['intent_id']==source_goal['intent_id'] for g in goals):continue
                            goals.append({'intent_id':source_goal['intent_id'],'predicate_spans':[],
                                          'support_features':['current_task_service_exclusion'],
                                          'commit_basis':'resolved_current_task_service_exclusion',
                                          'antecedent_clause':[parent['a'],parent['b']],
                                          'exclusion_scope_groups':[target_group]})
                    frames.append({'a':a,'b':b,'services':ss,'entities':ee,'channels':[],
                                   'goals':goals,'role':'excluded','hits':h,'join':join,'shared_scope':False})
                context.append({'feature':'current_task_service_exclusion','span':mark(question,a,b,'excluded_service')})
                continue
            if any(span['start']<=a and b<=span['end'] for span in fronted_contexts):
                pending=unique(pending+ss);pending_spans.append([a,b]);last_services=pending[:]
                context.append({'feature':'fronted_process_context','span':mark(question,a,b,'context_only')})
                for span in fronted_contexts:
                    if span['start']<=a and b<=span['end'] and span['unresolved_context_tokens']:
                        unresolved.append({'kind':'fronted_context_dimension_unresolved',
                                           'span':mark(question,a,b,'unresolved_context'),
                                           'tokens':span['unresolved_context_tokens']})
                continue
            goals,h=self.goals(text,localmasked)
            if not ee and response_layout_directive(text):
                context.append({'feature':'response_layout_directive','span':mark(question,a,b,'response_constraint')})
                continue
            kept_goals=[]
            for goal in goals:
                if not temporal_scopes:
                    kept_goals.append(goal)
                    continue
                heads=goal.get('head_spans') or goal['predicate_spans']
                if not heads:
                    unresolved.append({'kind':'predicate_scope_unresolved','span':mark(question,a,b,'requested_predicate')})
                    continue
                outside=[point for point in heads if not any(
                    a+point[0]<q['event_span']['end'] and q['event_span']['start']<a+point[1]
                    for q in temporal_scopes)]
                if outside:
                    goal['head_spans']=outside
                    goal['predicate_spans']=[point for point in goal['predicate_spans'] if not any(
                        a+point[0]<q['event_span']['end'] and q['event_span']['start']<a+point[1]
                        for q in temporal_scopes)] or outside
                    kept_goals.append(goal)
                else:context.append({'feature':'temporal_condition_event','span':mark(question,a,b,'condition_context')})
            goals=kept_goals
            if not goals and not ee and nonrestrictive_scalar_focus(localmasked):
                proof=mark(question,a,b,'response_scope_modifier')
                nonrestrictive_modifiers.append(proof)
                context.append({'feature':'nonrestrictive_scalar_modifier','span':proof})
                continue
            if not goals and temporal_context_fragment(localmasked,a,temporal_scopes):
                context.append({'feature':'temporal_condition_context','span':mark(question,a,b,'condition_context')})
                continue
            context.extend({'feature':'activation_requirement_purpose','span':mark(question,a+x,a+y,'context_only')}
                           for x,y in h.get('activation_purpose_context',[]))
            context.extend({'feature':'condition_procedure_context','span':mark(question,a+x,a+y,'context_only')}
                           for x,y in h.get('workflow_purpose_context',[]))
            local_semantics=h['_semantic']
            if role=='excluded' and any(g['intent_id']=='balance_treatment' for g in goals) \
                    and not (h.get('initial') or h.get('activation')):
                goals=[g for g in goals if g['intent_id']!='initial_funding']
            shell=task_envelope(text,goals) or ('numeric_field_envelope'
                                                  if numeric_field_envelope(text) else None)
            shell_spans=any_span(text,TASK_OBJECTS+TASK_ACTIONS) if shell else []
            if shell_spans:
                # Remove only predicates whose linguistic head is the
                # administrative shell itself (paper/file/name/instruction).
                # Substantive heads such as national ID survive for typed
                # distribution to explicitly named providers.
                goals=[goal for goal in goals if any(not any(overlaps(point,shell_span)
                      for shell_span in shell_spans)
                      for point in goal.get('head_spans',goal['predicate_spans']))]

            verification=global_semantics.get('claim_verification')
            verification_here=bool(verification and a<=verification['span']['start']<b)
            projection_points=any_span(localmasked,TASK_REFERENCE)+(
                [(verification['span']['start']-a,verification['span']['end']-a)]
                if verification_here else [])
            projection_requested=bool(projection_points or any_span(localmasked,
                ['verify','correct','check','populate','fill','replace','تحقق','تحقّق','صحح','صحّح','راجع','املأ','املا','استبدل']))

            if projection_requested:
                projected=[];projected_services=[];projected_channels=[]
                if verification_here:
                    quoted_text=' '.join(row['claim']['span'].get('text','') for row in quoted_projections)
                    bound=list(verification.get('bound_intents',[]))
                    if 'opening_fee' in bound and not any_span(quoted_text,self.features.get('fee',[])):
                        bound.remove('opening_fee')
                    projected=[{'intent_id':intent,'predicate_spans':projection_points,
                                'head_spans':projection_points,
                                'support_features':['explicit_claim_verification'],
                                'commit_basis':'explicit_verification_of_bounded_claim','mode':'verify_claim'}
                               for intent in bound]
                    projected_services=unique(service for row in quoted_projections for service in row['services'])
                    projected_channels=unique(channel for row in quoted_projections for channel in row.get('channels',[]))
                if not projected:
                    label=next((row for row in reversed(quoted_projections) if row['goals']),None)
                    if label:
                        projected=[{**goal,'predicate_spans':projection_points or goal['predicate_spans'],
                                    'head_spans':projection_points or goal.get('head_spans',goal['predicate_spans']),
                                    'support_features':['explicit_reference_to_bounded_label'],
                                    'commit_basis':'explicit_reference_to_bounded_label'}
                                   for goal in label['goals']]
                        projected_services=label['services']
                if not projected and reported_projection:
                    projected=[{**goal,'predicate_spans':projection_points or goal['predicate_spans'],
                                'head_spans':projection_points or goal.get('head_spans',goal['predicate_spans']),
                                'support_features':['explicit_correction_of_bounded_claim'],
                                'commit_basis':'explicit_correction_of_bounded_claim'}
                               for goal in reported_projection['goals']]
                    projected_services=reported_projection['services']
                    projected_channels=reported_projection['channels']
                    reported_projection=None
                # A source-order correction for a uniquely mapped platform is
                # a workflow projection, irrespective of the faulty order that
                # happened to be written in the reported card.
                procedure_services=unique(e['service_id'] for e in resolved_platforms
                                          if a<=e['start']<b or any_span(localmasked,['source order','registration','التسجيل','الترتيب']))
                if procedure_services and any_span(localmasked,['source order','sequence','registration','التسجيل','التسلسل','الترتيب']):
                    projected=[{'intent_id':'workflow','predicate_spans':projection_points or [(0,len(text))],
                                'head_spans':projection_points or [(0,len(text))],
                                'support_features':['source_bound_procedure_signature'],
                                'commit_basis':'explicit_source_order_projection'}]
                    projected_services=procedure_services
                if projected:
                    existing={goal['intent_id'] for goal in goals}
                    goals.extend(goal for goal in projected if goal['intent_id'] not in existing)
                    if not ss:ss=projected_services[:]
                    if not cc and projected_channels:cc=projected_channels[:]

            if shell:
                context.append({'feature':'task_envelope','span':mark(question,a,b,'context_only')})
                if ss:task_services=unique(task_services+ss);last_services=ss[:]
                unknown_label=bool(quoted_projections and not any(row['goals'] for row in quoted_projections)
                                   and goals and all(goal['intent_id']=='response_draft' for goal in goals))
                if unknown_label:
                    unresolved.append({'kind':'claim_reference_unresolved',
                                       'span':mark(question,a,b,'requested_predicate'),
                                       'services':ss[:]})
                    continue
                reported=bool(re.search(r'\b(?:says|states|wrote|reported|puts|makes)\b|(?<!\w)(?:كتب|ورد|يقول)(?!\w)',shadow(text)[0],re.I))
                if reported and goals:
                    report_start=next((m.end() for m in re.finditer(r'\b(?:says|states|wrote|reported|puts|makes)\b|(?<!\w)(?:كتب|ورد|يقول)(?!\w)',text,re.I)),0)
                    report_span=mark(question,a+report_start,b,'claim')
                    if not any(c.get('span',{}).get('start')==report_span['start'] and c.get('span',{}).get('end')==report_span['end'] for c in claims):
                        claims.append({'source':'structural_reported_claim','verified':False,
                                       'verified_business_fact':False,'speaker_role':'reported_record',
                                       'span':report_span})
                    reported_projection={'goals':goals,'services':ss[:],'channels':cc[:]}
                    continue
                if not goals:
                    continue
                if not ss and len(references)==1:
                    ss=references[:]
                if not ss:
                    pending_task_goals={'goals':goals,'a':a,'b':b,'hits':h,'role':role}
                    continue

            if pending_task_goals and ss:
                source=pending_task_goals
                frames.append({'a':source['a'],'b':source['b'],'services':ss[:],
                               'entities':ee,'channels':[],'goals':source['goals'],
                               'role':source['role'],'hits':source['hits'],'join':'task_projection',
                               'shared_scope':len(ss)>1,'binding_prefix_spans':[[a,b]]})
                task_services=unique(task_services+ss);pending_task_goals=None
                context.append({'feature':'task_predicate_distribution','span':mark(question,a,b,'context_only')})
                if not goals:
                    continue
            context.extend({'feature':'transaction_code_subject','span':mark(question,a+x,a+y,'context_only')} for x,y in h.get('code_subject_context',[]))
            # An adjacent price-only clause may supply the dimension of an
            # explicit action.  Its example/global candidates cannot contribute
            # a different provider, channel or operation to this clause.
            dimension_proposals=list(global_semantics.get('unbound_dimensions',[]))
            range_index=next((i for i,r in enumerate(ranges) if r[0]==a and r[1]==b),None)
            if range_index is not None and range_index+1<len(ranges) and not local_semantics.get('unbound_dimensions'):
                left,right,_=ranges[range_index+1]
                if self.hits(masked[left:right]).get('fee'):
                    adjacent=infer_clause(question[a:right],masked[a:right],self.features,p.intents,p.operators)
                    for proposed in adjacent.get('unbound_dimensions',[]):
                        dimension_proposals.append({**proposed,**{key:[(a+x,a+y) for x,y in proposed.get(key,[])]
                                                                  for key in ('spans','action_spans','fee_question_spans')}})
            for proposed in dimension_proposals:
                if proposed['dimension']!='financial_addition' or any(d['dimension']=='financial_addition' for d in local_semantics.get('unbound_dimensions',[])):continue
                actions=proposed.get('action_spans',[])
                if not actions or not all(a<=x and y<=b for x,y in actions):continue
                index=next((i for i,r in enumerate(ranges) if r[0]==a and r[1]==b),None)
                if index is None or index+1>=len(ranges):continue
                left,right,_=ranges[index+1]
                if any(e['start']>=left and e['start']<right for e in active_entities+channels):continue
                fee=proposed.get('fee_question_spans',[])
                if not fee or not all(left<=x and y<=right for x,y in fee):continue
                tail=list(masked[left:right])
                for x,y in fee:tail[x-left:y-left]=' '*(y-x)
                if self.role(question[left:right],self.hits(masked[left:right]))!='requested' or not self.modifier_only(''.join(tail)):continue
                local_semantics['unbound_dimensions'].append({**proposed,'spans':[(x-a,y-a) for x,y in proposed['spans']],'action_spans':[(x-a,y-a) for x,y in actions],'fee_question_spans':[(x-a,y-a) for x,y in fee],'price_query_clause':[left,right]})
            attribution=any_span(localmasked,['according to the customer','according to the employee','على حد قول العميل'])
            if not goals and attribution:
                context.append({'feature':'speaker_attribution','span':mark(question,a,b,'context_only')});continue
            physical_context=any_span(localmasked,ATOMS['item']+ATOMS['stock']) and re.match(r'^\s*(?:for\b|about\b|بخصوص\b)',shadow(localmasked)[0])
            if not goals and physical_context:
                context.append({'feature':'physical_object_frame','span':mark(question,a,b,'context_only')});continue
            if not goals and (h.get('list_preamble') or h.get('coverage_disclosure')):
                feature='list_preamble' if h.get('list_preamble') else 'coverage_disclosure'
                context.append({'feature':feature,'span':mark(question,a,b,'context_only')});continue
            future_followup=(any_span(localmasked,['وهسألك','وهنسألك','هسألك',"I'll ask",'I will ask'])
                             and any_span(localmasked,['بعدها','بعدين','next','afterwards']))
            if not goals and future_followup:
                context.append({'feature':'future_followup_scope','span':mark(question,a,b,'context_only')});continue
            if not goals and re.match(r'^\s*(?:someone\s+(?:wrote|said|claimed|stated|reported)|the\s+customer\s+(?:wrote|said|claimed|stated|reported)|كتب\s+شخص|قال\s+شخص|ادعى\s+شخص|العميل\s+(?:قال|ادعى))\b',shadow(localmasked)[0]):
                context.append({'feature':'reported_claim_envelope','span':mark(question,a,b,'context_only')});continue
            substitution=any_span(localmasked,['replace','substitute','confuse','mix up','mix them','تبدل','تخلط','أخلط','اخلط','تستبدل','akhlat']) or re.search(r'(?<!\w)(?:ما\s+)?(?:تبدل|تخلط|أخلط|اخلط|تستبدل)ش?(?!\w)',shadow(localmasked)[0])
            misclassification=re.search(r'\b(?:do\s+not\s+)?treat\b.*?\bas\b|(?<!\w)(?:لا\s+)?تعامل\b.*?(?:كأنه|كانه|كأنها|كانها)',shadow(localmasked)[0],re.I)
            if role=='excluded' and misclassification:
                delimiter=re.search(r'\bas\b|(?:كأنه|كانه|كأنها|كانها)',shadow(localmasked)[0],re.I)
                split=delimiter.end() if delimiter else misclassification.start()
                goals=[goal for goal in goals if any(left>=split for left,right in goal.get('head_spans',goal['predicate_spans']))]
                context.append({'feature':'predicate_misclassification_constraint','span':mark(question,a,b,'context_only')})
            if role=='excluded' and substitution:
                obligations.append({'kind':'predicate_separation','span':mark(question,a,b,'constraint')})
                context.append({'feature':'response_constraint','span':mark(question,a,b,'context_only')});continue
            if role=='excluded' and h.get('fee') and not misclassification:
                # A broad “not asking about fees” clause is an exclusion
                # constraint, not a request and not an unresolved predicate.
                # Preserve all fee families only when the noun is genuinely
                # broad; a named opening/deposit/withdrawal head stays narrow.
                points=h['fee']
                named=[]
                explicit_opening=(re.search(r'\b(?:opening|subscription)\b',localmasked,re.I)
                                  or any_span(localmasked,[
                                      'wallet creation','فتح','اشتراك','إنشاء المحفظة','انشاء المحفظة']))
                if h.get('opening') and explicit_opening:named.append('opening_fee')
                if h.get('deposit') and not (h.get('initial') or h.get('activation')):named.append('deposit_tariff')
                if h.get('withdrawal'):named.append('withdrawal_tariff')
                existing={goal['intent_id'] for goal in goals}
                goals.extend({'intent_id':intent,'predicate_spans':points,'head_spans':points,
                              'support_features':['excluded_broad_fee_scope'],
                              'commit_basis':'current_clause_excluded_object'}
                             for intent in (unique(named) or ['opening_fee','deposit_tariff','withdrawal_tariff'])
                             if intent not in existing)
                context.append({'feature':'excluded_fee_scope','span':mark(question,a,b,'context_only')})
            if role=='excluded' and not goals and h.get('balance'):
                goals=[{'intent_id':'balance_treatment','predicate_spans':h['balance'],'head_spans':h['balance'],'support_features':['excluded_wallet_balance'],'commit_basis':'current_clause_excluded_object'}]
            if role=='excluded' and any_span(localmasked,['second','another','again','مرة تانية','تاني']):
                for goal in goals:
                    if goal['intent_id']=='payment':goal['intent_id']='repeat_payment'
            past_event=any_span(localmasked,['came out','took the payment','was requested','was shown','طلع','ظهر','اتبعث'])
            asks=any_span(localmasked,['what','which','how','explain','is it','has it','was it','هل','اشرح','ايه','إيه','كيف'])
            if past_event and not asks:
                context.append({'feature':'reported_event_outcome','span':mark(question,a,b,'context_only')});last_services=ss or last_services;continue
            # A reported prior event is context, never a fresh command.
            # Explicit business-claim verification retains its own predicate.
            reports=global_semantics.get('reported_assertions',[])
            content_start=a+len(text)-len(text.lstrip())
            content_end=a+len(text.rstrip())
            reported=next((r for r in reports if r['span']['start']<=content_start and content_end<=r['span']['end']),None)
            if reported and not global_semantics.get('claim_verification'):
                context.append({'feature':'reported_assertion_context','span':reported['span']});last_services=ss or last_services;continue
            # A current dimension may take an explicit object from a preceding
            # clause; no example annotation can supply that object.
            for global_goal in global_semantics['supplemental_goals']:
                points=global_goal.get('head_spans',global_goal['predicate_spans'])
                current_points=[(x,y) for x,y in global_goal['predicate_spans'] if a<=x<b]
                if not goals and current_points and any(x<a for x,y in global_goal['predicate_spans']) and (not local_semantics.get('unbound_dimensions') or not frames):
                    points=current_points
                    inherited={**global_goal,'predicate_spans':[(x-a,y-a) for x,y in global_goal['predicate_spans']],'head_spans':[(x-a,y-a) for x,y in points],'antecedent_clause':[min(x for x,y in global_goal['predicate_spans']),a],'commit_basis':'current_dimension_with_explicit_prior_object'}
                    goals.append(inherited)
            image_antecedents=[f for f in actor_frames if f.get('event')=='display_or_supply_image' and f['span']['end']<=a]
            permission_heads=any_span(localmasked,self.features.get('permission',[])+['may I use','can I use','هل يجوز','يجوز','use it','استخدامها'])
            if not goals and image_antecedents and permission_heads:
                parent=image_antecedents[-1]['span']
                goals=[{'intent_id':'image_permission','predicate_spans':permission_heads,'head_spans':permission_heads,'support_features':['permission_image_antecedent'],'commit_basis':'resolved_object_dimension','antecedent_clause':[parent['start'],parent['end']],'mode':'permission'}]
            if any(g['intent_id']=='refund_eligibility' for g in goals) and frames and any(g['intent_id']=='product_return' for g in frames[-1]['goals']):
                for goal in goals:
                    if goal['intent_id']=='refund_eligibility':goal['domain_id']='retail_operations';goal['antecedent_clause']=[frames[-1]['a'],frames[-1]['b']]
            # A dimension-only clause can refer to the nearest typed object,
            # e.g. a transaction followed by "not its status".  The current
            # dimension supplies the predicate; the preceding frame supplies
            # only the explicitly established object, never an answer fact.
            families={
                'transaction':{'members':{'payment','transaction_cancel','transaction_status'},'dimensions':{'status':'transaction_status','cancel':'transaction_cancel'}},
                'refund':{'members':{'refund','refund_status','refund_eligibility'},'dimensions':{'status':'refund_status','eligibility':'refund_eligibility'}},
                'complaint':{'members':{'complaint_create','complaint_status','complaint_resolution_confirmation'},'dimensions':{'status':'complaint_status','resolution':'complaint_resolution_confirmation'}},
                'item':{'members':{'inventory_count','stock_availability','product_return'},'dimensions':{'return':'product_return','eligibility':'product_return'}},
                'financial_subject':{'members':{'initial_funding','balance_treatment'},'dimensions':{'financial_addition':'deposit_tariff'}},
            }
            if local_semantics.get('unbound_dimensions') and frames:
                parent=frames[-1]
                if any(d['dimension']=='financial_addition' for d in local_semantics['unbound_dimensions']):
                    current_services=ss or last_services or global_services
                    compatible=[f for f in frames if f['role']=='requested' and set(f['services'])&set(current_services) and any(g['intent_id'] in families['financial_subject']['members'] for g in f['goals'])]
                    if compatible:parent=compatible[-1]
                matches=[v for v in families.values() if any(g['intent_id'] in v['members'] for g in parent['goals'])]
                if len(matches)==1:
                    for dim in local_semantics['unbound_dimensions']:
                        iid=matches[0]['dimensions'].get(dim['dimension'])
                        if iid and not any(g['intent_id']==iid for g in goals):
                            if dim['dimension']=='financial_addition' and not set(parent['services'])&set(ss or last_services or global_services):continue
                            mode='information' if dim['dimension']=='financial_addition' else 'ask_status' if dim['dimension'] in {'status','resolution'} else 'policy_query' if dim['dimension']=='eligibility' else 'action_request_or_capability'
                            domain=next((g.get('domain_id') for g in parent['goals'] if g.get('domain_id')),None)
                            goals.append({'intent_id':iid,'predicate_spans':dim['spans'],'head_spans':dim.get('action_spans',dim['spans']),'support_features':['typed_object_antecedent'],'commit_basis':'new_action_with_resolved_financial_object' if dim['dimension']=='financial_addition' else 'resolved_object_dimension','antecedent_clause':[parent['a'],parent['b']],'mode':mode,'domain_id':domain,'price_query_clause':dim.get('price_query_clause')})
            if not goals and any(d['dimension']=='financial_addition' for d in local_semantics.get('unbound_dimensions',[])):
                target=ss or last_services or (references if len(references)==1 else [])
                if not target and len(previous.get('unsupported_named_providers',[]))==1:
                    target=['unsupported_named:'+previous['unsupported_named_providers'][0]]
                target_keys={binding_subject_key(binding) for binding in target}
                prior=[r for r in previous.get('request_references',[]) if subject_key(r) in target_keys and r['intent_id'] in families['financial_subject']['members']]
                if len({subject_key(r) for r in prior})==1:
                    parent=prior[-1]
                    ss=target[:]
                    for dim in local_semantics['unbound_dimensions']:
                        if dim['dimension']=='financial_addition':
                            goals.append({'intent_id':'deposit_tariff','predicate_spans':dim['spans'],'head_spans':dim['action_spans'],'support_features':['same_session_financial_object'],'commit_basis':'new_action_with_resolved_financial_object','antecedent_turn':previous.get('turn_id'),'object_antecedent':{'request_id':parent['request_id'],'service_id':parent['service_id'],'unsupported_named_provider':parent.get('unsupported_named_provider',[]),'intent_id':parent['intent_id'],'turn_id':previous.get('turn_id')},'mode':'information','price_query_clause':dim.get('price_query_clause')})
            if not goals and local_semantics['actor_frames']:
                context.append({'feature':'reported_actor_frame','span':mark(question,a,b,'context_only')});last_services=ss or last_services;continue
            if any(g['intent_id']=='image_permission' for g in goals):
                for key in ['opening','phone_owner','registration_context','identity']:
                    context.extend({'feature':key,'span':mark(question,a+x,a+y,'context_only')} for x,y in h.get(key,[]))
            # Fee/amount heads separated by coordination remain a modifier;
            # they cannot create a source policy or erase another operation.
            if not goals and h.get('fee'):head_context=(a,b,h)
            fee_floor_modifier=any_span(localmasked,[
                'minimum fee','fee floor','minimum charge','a2al rosoom','min lel 3omoola',
                'الحد الأدنى لرسوم','الحد الادنى لرسوم','الحد الأدنى للعمولة','الحد الادنى للعمولة',
                'أقل رسوم','اقل رسوم'
            ])
            if not goals and not cc and fee_floor_modifier and any(
                    frame['role']=='requested' and any(goal['intent_id'] in TARIFFS for goal in frame['goals'])
                    for frame in frames):
                context.append({'feature':'requested_fee_floor_attribute','span':mark(question,a,b,'attribute')})
                continue
            if not goals and not cc and h.get('fee') and any(
                    frame['role']=='requested' and any(goal['intent_id'] in TARIFFS for goal in frame['goals'])
                    for frame in frames):
                context.append({'feature':'requested_tariff_attribute','span':mark(question,a,b,'attribute')})
                continue
            contextual_start=bool(any_span(localmasked,self.features['context_start']))
            if not goals and (h.get('quote') or h.get('registration_context') and contextual_start):
                context.append({'feature':'reported_or_process_context','span':mark(question,a,b,'context_only')});last_services=ss or last_services;continue
            if h.get('registration_context') and not goals and re.match(r'^\s*(?:for\b|during\b|while\b|اثناء\b|خلال\b)',shadow(localmasked)[0]):
                context.append({'feature':'process_context','span':mark(question,a,b,'context_only')});last_services=ss or last_services;continue
            if contextual_start and goals and all(g['intent_id']=='workflow' for g in goals):
                context.append({'feature':'process_context','span':mark(question,a,b,'context_only')});last_services=ss or last_services;continue
            same_requirement=bool(any_span(localmasked,[
                'keep the same requirement','same requirement','retain the same requirement',
                'نفس الشرط','احتفظ بنفس الشرط','خلي نفس الشرط']))
            if not goals and same_requirement and any(
                    frame.get('role')=='requested' and any(
                        goal.get('commit_basis')=='resolved_typed_service_replacement'
                        for goal in frame.get('goals',[])) for frame in frames):
                context.append({'feature':'same_requirement_restatement',
                                'span':mark(question,a,b,'context_only')})
                continue
            if not goals and ss:
                service_replacement=bool(any_span(localmasked,[
                    'switch only the provider','switch the provider','change only the provider',
                    'replace only the provider','keep the same requirement','same requirement',
                    'غيّر مقدم الخدمة فقط','غير مقدم الخدمة فقط','بدّل مقدم الخدمة فقط']))
                if (role=='excluded' and response_exclusion(text) or service_replacement) and len(set(previous.get('requested_topics',[])))==1:
                    inherited=previous['requested_topics'][0]
                    goals=[{'intent_id':inherited,'predicate_spans':[],
                            'support_features':['explicit_service_replacement'],
                            'commit_basis':'resolved_typed_service_replacement',
                            'antecedent_turn':previous.get('turn_id')}]
                if goals:
                    pass
                else:
                    process_scope=bool(re.match(
                        r'^\s*(?:(?:while|when|during)\s+(?:checking|reviewing)|عند\s+(?:مراجعة|فحص)|أثناء\s+(?:مراجعة|فحص)|اثناء\s+(?:مراجعة|فحص))\b',
                        shadow(localmasked)[0],re.I))
                    if process_scope:
                        pending=unique(pending+ss);pending_spans.append([a,b]);last_services=ss
                        context.append({'feature':'service_process_context','span':mark(question,a,b,'context_only')})
                        continue
                if goals:
                    # Continue below with the inherited typed exclusion.
                    pass
                else:
                    presentation_tokens={token for phrase in self.features.get('presentation',[]) for token in tokens(phrase) if len(tokens(phrase))==1}
                    remaining=set(tokens(localmasked))-{'for','the','compare','and','what','about','please','regarding','case','بالنسبه','في','حاله','حالة','ما','عن','وماذا','ماذا'}-presentation_tokens
                    follow=bool(any_span(localmasked,self.features['followup']) or provider_ellipsis and references and not frames)
                    pure_entity=not remaining or self.modifier_only(localmasked)
                    if pure_entity and task_services and not follow:
                        task_services=unique(task_services+ss)
                        last_services=task_services[:]
                        if frames and frames[-1]['role']=='requested':
                            frames[-1]['services']=unique(frames[-1]['services']+ss)
                            frames[-1]['shared_scope']=len(frames[-1]['services'])>1
                        context.append({'feature':'task_service_scope','span':mark(question,a,b,'context_only')})
                        continue
                    if remaining and not pure_entity and not follow and not h.get('fee'):
                        unresolved.append({'kind':'predicate_unresolved','span':mark(question,a,b,'requested_predicate'),'services':ss})
                    attached_to_request=False
                    if pure_entity and frames and join not in {';','؛','start'} and not follow:
                        frames[-1]['services']=unique(frames[-1]['services']+ss)
                        frames[-1].setdefault('list_continuation_spans',[]).append([a,b])
                        for f in frames:
                            if f.get('shared_scope'):f['services']=unique(f['services']+ss)
                        attached_to_request=True
                    elif not follow:pending=unique(pending+ss);pending_spans.append([a,b])
                    if role=='requested':last_services=ss
                    if pure_entity and not follow and not attached_to_request:
                        context.append({'feature':'service_scope_preamble','span':mark(question,a,b,'context_only')})
                    if pure_entity and not follow:
                        continue
            if not ss:
                if pending:
                    ss=pending[:];binding_prefix_spans=pending_spans[:]
                    if goals:pending=[];pending_spans=[]
                elif task_services:ss=task_services[:]
                elif last_services:ss=last_services[:]
                elif len(global_services)==1:ss=global_services[:]
                elif comparison and global_services:ss=global_services[:]
                elif references:
                    if comparison:ss=unique(all_history)
                    elif len(references)==1:ss=references[:]
                    else:unresolved.append({'kind':'service_reference_ambiguous','span':mark(question,a,b,'referent'),'alternatives':references})
            elif pending and goals:
                ss=unique(pending+ss);binding_prefix_spans=pending_spans[:];pending=[];pending_spans=[]
            bound_by_topic=False
            distributive=distributive_subject_reference(localmasked)
            if role=='excluded' and not ee and distributive:
                # A plural provider pronoun is licensed only by explicit
                # current-turn subjects.  Do not use history, retrieved
                # examples or answer facts to create the set.
                if (distributive=='pair' and len(global_services)==2) or (distributive=='all' and len(global_services)>=2):
                    ss=global_services[:]
                    last_services=ss[:]
            # An explicit exclusion tail binds to the immediately active
            # service. A same-intent focus from an earlier provider must not
            # pull “not minimum funding” back across a service boundary.
            if not ee and goals and all(g['intent_id'] in intent_focus for g in goals) and not (role=='excluded' and last_services):
                ss=unique(s for g in goals for s in intent_focus[g['intent_id']]);bound_by_topic=True
            if not goals and cc and frames:
                # A channel ellipsis creates a separate typed scope. Excluded
                # mentions are never appended to the positive channel list.
                parent=frames[-1]
                inherited=[dict(g,predicate_spans=[],commit_basis='resolved_clause_ellipsis',antecedent_clause=[parent['a'],parent['b']]) for g in parent['goals'] if g['intent_id'] in TARIFFS]
                if inherited:
                    frames.append({'a':a,'b':b,'services':ss or parent['services'],'entities':ee,'channels':cc,'goals':inherited,'role':role,'hits':h,'join':join,'shared_scope':False});continue
            unresolved_financial=any(d['dimension']=='financial_addition' for d in local_semantics.get('unbound_dimensions',[]))
            if not goals and cc and not frames and previous.get('requested_topics') and ss and not unresolved_financial:
                by=previous.get('requests_by_service',{})
                inherited=unique(t for service in ss for t in by.get(service,[]))
                if not inherited and len(previous.get('services',[]))==1:inherited=previous['requested_topics']
                goals=[{'intent_id':t,'predicate_spans':[],'support_features':['channel_followup'],'commit_basis':'resolved_typed_reference','antecedent_turn':previous.get('turn_id')} for t in inherited]
            if not goals and cc and not frames:
                pending_channel_scopes.append({'a':a,'b':b,'services':ss,'entities':ee,'channels':cc,'role':role,'hits':h,'join':join})
                context.append({'feature':'forward_channel_scope','span':mark(question,a,b,role)});continue
            if not goals and h.get('permission') and frames and any(g['intent_id']=='image_permission' for g in frames[-1]['goals']):
                goals=[{'intent_id':'image_permission','predicate_spans':h['permission'],'support_features':['permission_coreference'],'commit_basis':'resolved_clause_ellipsis','antecedent_clause':[frames[-1]['a'],frames[-1]['b']]}]
            if not goals and not unresolved_financial and (h.get('followup') or ss and ee and references):
                by=previous.get('requests_by_service',{})
                inherited=unique(t for service in ss for t in by.get(service,[]))
                if not inherited and len(previous.get('services',[]))==1:inherited=previous.get('requested_topics',[])
                for intent in inherited:goals.append({'intent_id':intent,'predicate_spans':[],'support_features':['same_session_antecedent'],'commit_basis':'resolved_typed_reference','antecedent_turn':previous.get('turn_id')})
            if not goals:
                # Referent-only amount questions can resolve a typed funding
                # antecedent, never invent a default product.
                if projection_requested and frames:
                    context.append({'feature':'request_projection_reference','span':mark(question,a,b,'context_only')})
                elif self.modifier_only(localmasked):
                    context.append({'feature':'elliptic_modifier','span':mark(question,a,b,'attribute')})
                    if frames and any(g['intent_id']=='identity' for g in frames[-1]['goals']):
                        frames[-1].setdefault('attribute_modifiers',[]).append((a,b))
                elif set(tokens(localmasked)) <= {'i','ana','أنا','انا'}:
                    context.append({'feature':'speaker_preamble','span':mark(question,a,b,'context_only')})
                elif tokens(localmasked):unresolved.append({'kind':'predicate_unresolved','span':mark(question,a,b,'requested_predicate')})
                continue
            shared=not ee and bool(global_services) and not last_services and comparison
            if role=='requested' and not ee and not bound_by_topic and not references and not binding_prefix_spans and not last_services and len(global_services)>1 and not any(x[2] in {';','؛'} for x in breaks):ss=global_services[:];shared=True
            if not ss and goals and (role=='excluded' or any(g.get('domain_id') for g in goals) or all(g.get('mode') in {'ask_status','action_request_or_capability','procedure_query','policy_query'} for g in goals)):
                domains=unique(g['domain_id'] for g in goals if g.get('domain_id'))
                ss=domains if len(domains)==1 else ['unspecified_service']
            if not ss:unresolved.append({'kind':'service_unresolved','span':mark(question,a,b,'referent')})
            if ss and role=='requested':last_services=ss[:]
            considered.extend({**r,'clause_span':mark(question,a,b,'candidate')} for r in lexical_candidates(text,p.proposals,limit=3))
            if pending_channel_scopes and any(g['intent_id'] in TARIFFS for g in goals):
                for earlier in pending_channel_scopes:
                    if earlier['services'] and set(earlier['services'])!=set(ss):
                        unresolved.append({'kind':'channel_reference_ambiguous','span':mark(question,earlier['a'],earlier['b'],'channel')});continue
                    if earlier['role']=='requested':cc+=earlier['channels']
                    else:
                        inherited=[dict(g,predicate_spans=[],commit_basis='resolved_forward_scope',antecedent_clause=[a,b]) for g in goals if g['intent_id'] in TARIFFS]
                        frames.append({**earlier,'services':ss,'goals':inherited,'shared_scope':False})
                pending_channel_scopes=[]
            frames.append({'a':a,'b':b,'services':ss,'entities':ee,'channels':cc,'goals':goals,'role':role,'hits':h,'join':join,'shared_scope':shared,'binding_prefix_spans':binding_prefix_spans})
            if role=='requested':
                for goal in goals:intent_focus[goal['intent_id']]=self.bound_services(frames[-1],goal)
        self.bind_operation_procedure_modifiers(question,masked,frames,context)
        # Resolve channel exclusions by exact provider/predicate tuple, then
        # remove those channels from the positive request before any retrieval.
        for frame in frames:
            if frame['role']!='requested':continue
            preserved=[o for o in obligations if o.get('kind')=='preserve_source_condition']
            if preserved and any(g['intent_id']=='branch_condition' for g in frame['goals']):
                if any(g['intent_id']=='workflow' for g in frame['goals']):
                    frame['goals']=[g for g in frame['goals'] if g['intent_id']!='branch_condition']
                    continue
                prior=[f for f in frames if f is not frame and f['role']=='requested' and set(f['services'])&set(frame['services']) and any(g['intent_id']=='workflow' for g in f['goals'])]
                if prior and any(o['span']['start']<frame['b'] and frame['a']<o['span']['end'] for o in preserved):
                    frame['goals']=[g for g in frame['goals'] if g['intent_id']!='branch_condition']
        requests=[];excluded=[];relations=[]
        for frame in frames:
            a,b=frame['a'],frame['b'];raw=question[a:b]
            for binding in frame['services'] or [None]:
                for goal in frame['goals']:
                    if binding is not None and binding not in self.bound_services(frame,goal):continue
                    provider=next((f for f in foreign_entities if f['service_id']==binding),None)
                    if provider is None and isinstance(binding,str) and binding.startswith('unsupported_named:'):
                        provider={'provider_name':binding.split(':',1)[1]}
                    service=None if provider else binding
                    intent=goal['intent_id'];topic=p.adapter.get(intent,{}).get('topic') or 'unmapped:'+intent
                    if service not in p.definition['service_profiles'] and service is not None:
                        service=goal.get('domain_id') or 'unspecified_service'
                    evidence=[mark(question,a+x,a+y,'requested_predicate') for x,y in goal['predicate_spans']]
                    antecedent=goal.get('antecedent_turn') or goal.get('antecedent_clause')
                    if antecedent:evidence.append(mark(question,a,b,'referent'))
                    ch=unique(c['channel'] for c in frame['channels']);context_ch=[]
                    if intent in CONTEXT_CHANNEL_INTENTS:context_ch=ch;ch=[]
                    role=frame['role']
                    known_procedure=any(f['service_id']==service and f.get('atomic_group') and 'workflow' in f['selection_tags'] for f in p.definition.get('facts',[]))
                    family=p.definition['service_profiles'].get(service,{}).get('family')
                    workflow_scope=('MyFawry app navigation' if known_procedure and not any_span(raw,self.features['full_kyc']) else 'complete remittance cash-out' if family=='remittance' else 'full_procedure') if intent=='workflow' else ('branch-visit condition only' if intent=='branch_condition' else None)
                    if intent=='workflow' and workflow_scope=='MyFawry app navigation' and role=='requested':ch=['myfawry_app']
                    period=next((name for name,pp in [('daily',['daily','يومي','يوميا','كل يوم']),('monthly',['monthly','شهري','شهريا','كل شهر'])] if any_span(raw,pp)),None)
                    # Temporal process context and interrogative "when" are
                    # not customer-case predicates. Explicit if/unless cases
                    # remain unresolved conditions rather than invented policy.
                    conditions=[]
                    scenario_heads=any_span(raw,['لو','law','if','unless','إذا','اذا'])
                    scenario_spans=[]
                    for x,y in unique(scenario_heads):
                        # Franco law is an antecedent cue when followed by an
                        # operation, not the English noun in "tax law".
                        if shadow(raw[x:y])[0]=='law' and not any_span(raw[y:],self.features['deposit']+self.features['withdrawal']+self.features['activation']+self.features['action']):continue
                        before=shadow(raw[:x])[0]
                        if re.search(r'(?:^|\s)و?ما\s*$',before) or re.search(r'\b(?:know|check|verify|wonder|see|ask)\s*$',before):continue
                        # The interrogative consequence is outside its scenario.
                        tails=any_span(raw[y:],self.features['fee']+['what','how much','كام','قد إيه','بيتاخد','بتتاخد','بيتخصم','بيخصم','بيكلف','بتكلف'])
                        ends=[y+left for left,right in tails if any(x<=head<y+left for head,stop in goal.get('head_spans',goal['predicate_spans']))]
                        end=a+min(ends) if ends else b
                        scenario_spans.append(mark(question,a+x,end,'hypothetical_antecedent'))
                    if intent=='identity':
                        attribute_text=raw+' '+' '.join(question[x:y] for x,y in frame.get('attribute_modifiers',[]))
                        for name,aliases in [('original',['original','اصل','أصل','أصلية','اصليه','originale']),('valid',['valid','current ID','سارية','ساريه','ساري'])]:
                            if any_span(attribute_text,aliases):conditions.append({'type':'requested_attribute','name':name})
                    for x,y in frame['hits'].get('conditional',[]):
                        cue=shadow(raw[x:y])[0]
                        if re.search(r'(?:^|\s)و?ما\s*$',shadow(raw[:x])[0]):continue
                        if intent not in {'branch_condition','image_permission'} and cue in {'if','unless','provided','اذا','الا اذا','بشرط'}:
                            antecedent=next((s for s in scenario_spans if s['start']==a+x),None)
                            if antecedent and cue in {'if','اذا'} and self.assumed_operation_only(raw,frame,goal,x,antecedent['end']-a):continue
                            conditions.append({'operator':'user_condition','text':raw[x:],'evidence_span':mark(question,a+x,b,'condition')})
                    if intent=='workflow' and any(o.get('kind')=='preserve_source_condition' for o in obligations):conditions.append({'type':'preserve_source_condition','name':'app_directed_branch_visit'})
                    floor_requested=any_span(raw,['minimum fee','fee floor','minimum charge','minimum withdrawal fee','a2al rosoom','min lel 3omoola','الحد الأدنى لرسوم','الحد الادنى لرسوم','الحد الأدنى للعمولة','الحد الادنى للعمولة','اقل رسوم','أقل رسوم'])
                    tail_floor=any_span(question,['minimum fee','fee floor','minimum charge','a2al rosoom','min lel 3omoola','الحد الأدنى لرسوم','الحد الادنى لرسوم','الحد الأدنى للعمولة','الحد الادنى للعمولة'])
                    if intent in TARIFFS and (floor_requested or tail_floor and intent=='withdrawal_tariff' or any(c.get('claim_type')=='fee_floor' for c in claims)):
                        conditions.append({'type':'requested_attribute','name':'fee_floor'})
                    refs=[ref for ref in global_semantics['references'] if a<=ref['span']['start']<b]
                    if not refs and goal.get('antecedent_clause'):
                        left,right=goal['antecedent_clause'];refs=[ref for ref in global_semantics['references'] if left<=ref['span']['start']<right]
                    if not refs and goal.get('mode')=='ask_status' and len(global_semantics['references'])==1:
                        ref=global_semantics['references'][0]
                        if ref['span']['start']<a:refs=[ref]
                    if goal.get('mode') in {'ask_status','action_request_or_capability'}:
                        conditions.extend({'type':'synthetic_record_reference' if ref['value'].upper().startswith('TEST-') else 'unverified_record_reference','value':ref['value']} for ref in refs)
                    if intent=='transaction_status' and any_span(raw,['cancelled','canceled','اتلغت','ملغاة']):
                        conditions.insert(0,{'type':'state_under_question','value':'cancelled'})
                    if intent=='response_draft' and any(o.get('kind')=='response_constraint' for o in obligations):
                        conditions.append({'type':'response_constraint','value':'no_unverified_refund_or_deadline_promise'})
                    if intent=='callback':
                        for obligation in obligations:
                            if obligation.get('kind')=='customer_desired_time':
                                head=obligation['span']['end'];tail=question[head:frame['b']].strip(' ,،;؛')
                                # Raw desired time is a preference, never a
                                # confirmed appointment or documented SLA.
                                value='after noon; not confirmed appointment' if any_span(question[obligation['span']['start']:frame['b']],['after noon','ba3d el dohr','بعد الظهر']) else question[obligation['span']['start']:frame['b']]+'; not confirmed appointment'
                                conditions.append({'type':'customer_desired_time','value':value})
                    scope_entities=[(entity['start']-a,entity['end']-a) for entity in frame['entities']]
                    scalar_scope=nominal_scalar_focus(raw,scope_entities) if intent=='initial_funding' else []
                    amount_only=bool(scalar_scope)
                    numeric_group=any(left<=a and b<=right for left,right in numeric_groups)
                    numeric_amount=bool(intent=='initial_funding' and numeric_group and
                                        set(goal.get('support_features',[]))&{'initial','activation'})
                    req={'request_id':'R'+str(len(requests)+len(excluded)+1),'service_id':service,'intent_id':intent,'topic':topic,'role':role,'channels':ch,'context_channel_mentions':context_ch,'conditions':conditions,'requested_facets':['amount_only'] if amount_only or numeric_amount else [],'requested_facet_basis':'explicit_amount_only' if amount_only else 'numeric_field_envelope' if numeric_amount else None,'period':period,'procedure_scope':workflow_scope,'evidence_spans':evidence,'clause_span':mark(question,a,b,role),'commit_basis':goal['commit_basis'],'support_features':goal.get('support_features',[]),'antecedent_turn':goal.get('antecedent_turn'),'antecedent_clause':goal.get('antecedent_clause'),'hypothetical':bool(scenario_spans) or any(c.get('operator')=='user_condition' for c in conditions),'scenario_antecedents':scenario_spans,'mode':'permission' if intent=='image_permission' else 'full_sequence' if intent=='workflow' else 'evaluate_condition' if intent=='branch_condition' else 'information','condition_query':intent=='branch_condition'}
                    if provider_ellipsis and goal.get('antecedent_turn') and role=='requested':
                        inherited_scope=antecedent_scope(previous,intent,service)
                        if inherited_scope is None:
                            unresolved.append({'kind':'request_scope_antecedent_ambiguous','intent_id':intent,'service_id':service})
                            continue
                        req.update(inherited_scope['scope'])
                        req['inherited_scope']=inherited_scope
                    req['scope_group']=task_group(question,a)
                    if goal.get('exclusion_scope_groups') is not None:req['exclusion_scope_groups']=goal['exclusion_scope_groups']
                    if goal.get('mode'):req['mode']=goal['mode']
                    if goal.get('mode_evidence_spans'):req['mode_evidence_spans']=goal['mode_evidence_spans']
                    if scalar_scope:
                        req['requested_facet_spans']=[mark(question,a+span['start'],a+span['end'],span['role'])
                                                     for proof in scalar_scope for span in proof.values()]
                    if provider:
                        req['unsupported_named_provider']=[provider['provider_name']]
                        req['unsupported_subject_spans']=[mark(question,provider['start'],provider['end'],'unsupported_named_provider')] if 'start' in provider else []
                    if goal.get('object_antecedent'):req['object_antecedent']=goal['object_antecedent']
                    if goal.get('price_query_clause'):req['price_query_clause']=goal['price_query_clause']
                    if intent=='branch_condition':req['mode']='information'
                    if intent in TARIFFS and len(ch)>1 and any_span(question,['instead of','بدل','rather than','versus']):req['mode']='compare_alternatives'
                    if goal.get('domain_id'):req['domain_id']=goal['domain_id'];req['service_namespace']='linguistic_domain_only' if service not in p.definition['service_profiles'] else 'canonical'
                    reports=global_semantics.get('reported_assertions',claims)
                    claim_services={e['service_id'] for claim in reports for e in entities if claim['span']['start']<=e['start']<claim['span']['end']}
                    if service in claim_services and global_semantics['mode_by_intent'].get(intent)=='verify_claim':req['mode']='verify_claim'
                    if role=='requested' and intent in TARIFFS and not req['channels']:
                        quoted_route=quoted_channel_reference(question,req['clause_span'],service,
                            self.features['deposit' if intent=='deposit_tariff' else 'withdrawal'],
                            active_entities+foreign_entities,channels,
                            [(q['start'],q['end']) for q in quotations],p.catalog.get('channel_parents',{}))
                        if quoted_route:
                            req['quoted_channel_reference']=quoted_route
                            if not quoted_route['resolved']:
                                unresolved.append({'kind':'channel_reference_ambiguous','service_id':service,
                                                   'intent_id':intent,'span':quoted_route['reference_spans'][0],
                                                   'alternatives':quoted_route['candidate_channels'],'reference':quoted_route})
                            else:
                                req['channels']=[quoted_route['channel']]
                                if quoted_route['claim_scope_requested'] and quoted_route['unverified_scope_spans']:
                                    req['conditions'].append({'type':'user_condition',
                                        'operator':'quoted_scope_requires_source_verification',
                                        'value':'unverified quoted scope',
                                        'source_spans':quoted_route['unverified_scope_spans'],
                                        'claim_spans':[row['claim_span'] for row in quoted_route['antecedents']]})
                    req['references']=refs
                    (excluded if role=='excluded' else requests).append(req)
        # Normalize an explicit route replacement after clause roles have been
        # built.  The current route is requested and the replaced route is an
        # exclusion of the same service/predicate.  This uses only current
        # channel spans and a typed same-session antecedent.
        for positive,negative,left,right in self.channel_replacements(question,channels):
            candidates=[row for row in requests+excluded if row['intent_id'] in TARIFFS
                        and (positive in row['channels'] or negative in row['channels'])]
            if not candidates:continue
            base=dict(candidates[0])
            if base.get('service_id') in {None,'unspecified_service'} and len(references)==1:
                base['service_id']=references[0]
            key=subject_key(base);intent=base['intent_id']
            requests=[row for row in requests if not (subject_key(row)==key and row['intent_id']==intent)]
            excluded=[row for row in excluded if not (subject_key(row)==key and row['intent_id']==intent)]
            clause=mark(question,left,right,'requested')
            requested={**base,'request_id':'R'+str(len(requests)+len(excluded)+1),
                       'role':'requested','channels':[positive],'clause_span':clause,
                       'commit_basis':'explicit_channel_replacement'}
            omitted={**base,'request_id':'R'+str(len(requests)+len(excluded)+2),
                     'role':'excluded','channels':[negative],
                     'clause_span':dict(clause,role='excluded'),
                     'commit_basis':'explicit_replaced_channel'}
            requests.append(requested);excluded.append(omitted)

        # An explicit balance-disposition omission narrows the paired funding
        # request to its amount.  This is an answer facet, not a new policy or
        # a mutation of the ordinary initial-funding evidence bundle.
        funding=[row for row in requests if row['intent_id']=='initial_funding']

        # A response-narrowing clause such as "I only need the amount" often
        # follows the substantive funding question.  Attach it to only the
        # nearest same-subject funding clause; never broadcast it across all
        # services or every funding request in the question.
        for modifier in [row for row in funding
                         if row.get('requested_facet_basis')=='explicit_amount_only']:
            peers=[row for row in funding if row is not modifier and
                   subject_key(row)==subject_key(modifier)]
            if not peers:continue
            span=modifier['clause_span']
            def modifier_distance(row):
                other=row['clause_span']
                return max(0,span['start']-other['end'],other['start']-span['end'])
            target=min(peers,key=lambda row:(modifier_distance(row),row['clause_span']['start']))
            target['requested_facets']=unique(target.get('requested_facets',[])+['amount_only'])
            target['requested_facet_basis']='explicit_amount_only'

        def nearest_funding(balance):
            """Bind a balance qualifier to its nearest same-subject funding clause."""
            candidates=[row for row in funding if subject_key(row)==subject_key(balance)]
            if not candidates:return None
            span=balance['clause_span']
            def distance(row):
                other=row['clause_span']
                return max(0,span['start']-other['end'],other['start']-span['end'])
            return min(candidates,key=lambda row:(distance(row),row['clause_span']['start']))

        for balance in excluded:
            if balance['intent_id']!='balance_treatment':continue
            request=nearest_funding(balance)
            if request:
                request['requested_facets']=unique(request.get('requested_facets',[])+['amount_only'])
                request['requested_facet_basis']=request.get('requested_facet_basis') or 'explicit_balance_omission'
        for balance in requests:
            if balance['intent_id']!='balance_treatment':continue
            request=nearest_funding(balance)
            if request and request.get('requested_facet_basis')!='explicit_amount_only':
                request['requested_facets']=[name for name in request.get('requested_facets',[]) if name!='amount_only']
                request['requested_facet_basis']=None
        for request in requests+excluded:
            request.pop('requested_facet_basis',None)

        # One requested predicate may be restated without becoming two tasks.
        # Merge only exactly matching scopes; preserve every supporting span.
        distinct={}
        collapsed_channel_children=set()
        for request in requests:
            key=json.dumps({k:request.get(k) for k in ['service_id','unsupported_named_provider','intent_id','channels','conditions','requested_facets','period','procedure_scope','mode','scope_group']},sort_keys=True,ensure_ascii=False)
            if key not in distinct:distinct[key]=request;continue
            parent=distinct[key]
            parent.setdefault('supporting_clause_spans',[parent['clause_span']]).append(request['clause_span'])
            for span in request['evidence_spans']:
                if span not in parent['evidence_spans']:parent['evidence_spans'].append(span)
        requests=list(distinct.values())
        # Demonstrative financial subjects bind to an actual prior request of
        # the same service, never a fixture default or retrieved example.
        for request in requests:
            if request['intent_id']!='balance_treatment':continue
            text=request['clause_span']['text'];a=request['clause_span']['start']
            subjects=any_span(text,['amount','funding','deposit','مبلغ','فلوس','تمويل','mablagh','floos'])
            determiners=any_span(text,['this','that','the','ده','دي','هذا','هذه','نفس','el','wel'])
            for x,y in subjects:
                definite=bool(re.match(r'^[وفبلك]?ال',shadow(text[x:y])[0])) or any(abs(left-y)<8 or abs(x-right)<8 for left,right in determiners)
                if not definite:continue
                prior=[r for r in requests if r is not request and subject_key(r)==subject_key(request) and r['intent_id']=='initial_funding' and r['clause_span']['end']<=a+x]
                if prior:
                    parent=max(prior,key=lambda r:r['clause_span']['end'])
                    request.setdefault('subject_references',[]).append({'kind':'financial_subject','span':mark(question,a+x,a+y,'referent'),'antecedent_request_id':parent['request_id'],'antecedent_clause':parent['clause_span']})
                    if not request.get('antecedent_clause'):request['antecedent_clause']=[parent['clause_span']['start'],parent['clause_span']['end']]
        # A balance-outcome clause can refer to an already requested principal.
        # Its disposition head does not request that principal a second time.
        # Preserve independently stated funding heads and all new task groups.
        referenced_funding=[]
        by_id={r['request_id']:r for r in requests}
        for request in requests:
            if (request['intent_id']!='initial_funding'
                    or set(request.get('support_features',[]))!={'balance_disposition'}):
                continue
            for balance in requests:
                if (balance['intent_id']!='balance_treatment'
                        or subject_key(balance)!=subject_key(request)
                        or balance['clause_span']!=request['clause_span']):
                    continue
                for reference in balance.get('subject_references',[]):
                    parent=by_id.get(reference.get('antecedent_request_id'))
                    if not parent or any(request.get(k)!=parent.get(k)
                                         for k in ['channels','conditions','period','procedure_scope','requested_facets']):
                        continue
                    referenced_funding.append(request['request_id'])
        requests=[r for r in requests if r['request_id'] not in referenced_funding]
        # Carry an explicit exclusion across a simple coordinated predicate
        # list ("exclude identity and existing-wallet checks").  The scope
        # ends at punctuation or an explicit polarity reset.
        moved=[]
        for request in list(requests):
            start=request.get('clause_span',{}).get('start',0)
            prior=[row for row in excluded if row.get('clause_span',{}).get('end',0)<=start]
            if not prior:continue
            parent=max(prior,key=lambda row:row['clause_span']['end'])
            between=question[parent['clause_span']['end']:start]
            if re.fullmatch(r'\s*(?:and|or|و|أو)\s*',between,re.I) and not re.search(r'[.;!?؟؛]',between):
                requests.remove(request)
                moved.append({**request,'role':'excluded',
                              'clause_span':dict(request['clause_span'],role='excluded'),
                              'commit_basis':'coordinated_exclusion_scope'})
        excluded.extend(moved)
        # A pure referent clause establishes the subject for a later explicit
        # current-turn request.  Apply this only after coordinated exclusions
        # have been moved out of the positive set.
        explicit_pairs={(row.get('service_id'),row.get('request_id')) for row in requests
                        if any(span.get('role')=='requested_predicate'
                               for span in row.get('evidence_spans',[]))}
        requests=[row for row in requests if not (
            row.get('antecedent_turn') and row.get('evidence_spans') and not row.get('channels')
            and all(span.get('role')=='referent' for span in row['evidence_spans'])
            and any(service==row.get('service_id') and request_id!=row.get('request_id')
                    for service,request_id in explicit_pairs))]
        # Reject cross-predicate leakage inside a coordinated exclusion before
        # exclusions are applied to positive requests.
        scoped_excluded=[]
        for exclusion in excluded:
            clause=exclusion.get('clause_span',{}).get('text','')
            intent=exclusion.get('intent_id')
            # A typed channel exclusion ("not ATM", "not Fawry Plus")
            # legitimately inherits the predicate from its coordinated
            # request.  The leakage filter below is only for predicate-only
            # exclusions accidentally proposed from unrelated words.
            if (exclusion.get('exclusion_scope_groups') is not None or exclusion.get('channels')
                    or 'excluded_broad_fee_scope' in exclusion.get('support_features',[])):
                scoped_excluded.append(exclusion)
                continue
            if intent=='opening_fee' and not any_span(
                    clause,self.features.get('opening',[])+['subscription','اشتراك']):
                continue
            if intent=='withdrawal_tariff' and not any_span(clause,self.features.get('withdrawal',[])):
                continue
            if intent=='deposit_tariff' and not any_span(clause,self.features.get('deposit',[])):
                continue
            scoped_excluded.append(exclusion)
        excluded=scoped_excluded
        for exclusion in excluded:
            for request in requests:
                if subject_key(exclusion)==subject_key(request) and exclusion['intent_id']==request['intent_id']:
                    if exclusion.get('exclusion_scope_groups') is not None and request.get('scope_group') not in exclusion['exclusion_scope_groups']:continue
                    if exclusion['channels']:
                        if not request['channels']:
                            # A broad tariff remains unbounded except for its
                            # exclusion; available-source channel filtering is
                            # applied separately in evidence selection.
                            request['excluded_channels']=unique(request.get('excluded_channels',[])+exclusion['channels'])
                        else:request['channels']=[c for c in request['channels'] if c not in exclusion['channels']]
                    else:request['excluded_by']=exclusion['request_id']
                    relations.append({'type':'excludes','from':exclusion['request_id'],'to':request['request_id'],'channels':exclusion['channels']})
        requests=[r for r in requests if not r.get('excluded_by')]
        # "Opening requirements/conditions" is an eligibility bundle, not a
        # request for the opening price merely because the word "opening" is
        # present.  Keep a fee request only when the current clause contains a
        # charge/cost predicate.  This is clause- and service-scoped.
        eligibility_scopes={(r.get('service_id'),r.get('clause_span',{}).get('start'),r.get('clause_span',{}).get('end'))
                            for r in requests if r.get('intent_id')=='eligibility'}
        filtered=[]
        for request in requests:
            key=(request.get('service_id'),request.get('clause_span',{}).get('start'),request.get('clause_span',{}).get('end'))
            clause=request.get('clause_span',{}).get('text','')
            explicit_price=bool(any_span(clause,self.features.get('fee',[])+['cost','charge','price','تكلفة','رسوم','عمولة']))
            if request.get('intent_id')=='opening_fee' and key in eligibility_scopes and not explicit_price:
                continue
            filtered.append(request)
        requests=filtered
        for request in requests:
            if request.get('mode')=='ask_status' and request.get('references'):
                keys={r['value'] for r in request['references']}
                peers=[r for r in requests if r is not request and subject_key(r)==subject_key(request) and r['intent_id']==request['intent_id'] and {v['value'] for v in r.get('references',[])}==keys]
                if not any(c.get('type')=='state_under_question' for c in request['conditions']):
                    states=[c for peer in peers for c in peer['conditions'] if c.get('type')=='state_under_question']
                    if len({c['value'] for c in states})==1:request['conditions']=states[:1]+request['conditions']
            if request['intent_id'] in TARIFFS and not request['channels']:
                peers=[r for r in requests if r is not request and subject_key(r)==subject_key(request) and r['intent_id']==request['intent_id']]
                inherited=unique(c for r in peers for c in r['channels'])
                if inherited:
                    request['channels']=inherited
                    request['channel_antecedent_requests']=[r['request_id'] for r in peers if r['channels']]
                    collapsed_channel_children.update(request['channel_antecedent_requests'])
            parents=p.catalog.get('channel_parents',{})
            request['channels']=[c for c in request['channels'] if c not in {parents.get(x) for x in request['channels']}]
            if request['intent_id'] in TARIFFS and len(request['channels'])>1 and any_span(question,['instead of','بدل','rather than','versus','or','aw']):request['mode']='compare_alternatives'
        requests=[request for request in requests if request['request_id'] not in collapsed_channel_children]
        for issue in bind_dimension_channel_references(question,requests,p.adapter):
            unresolved.append({'kind':'channel_reference_ambiguous',**issue})
        # Resolve a narrow "step after/before X" query from the registered
        # ordered procedure metadata.  This is source-driven and generic: no
        # service, wording, or fact identifier is embedded in the parser.
        projection_services=unique(global_services + (previous.get('services',[]) if len(previous.get('services',[]))==1 else []))
        projections=[project_procedure_members(question,service,p.definition) for service in projection_services]
        projections=[row for row in projections if row]
        if len(projections)==1:
            projection=projections[0];service=projection['service_id']
            scope_span=projection['request_span']
            if not projection_covers_span(question,scope_span,projection):
                unresolved.append({'kind':'procedure_scope_remainder_unresolved',
                                   'service_id':service,'span':dict(scope_span,role='unresolved_procedure_scope')})
            # A fully certified sequence clause can supersede rough lexical
            # proposals (such as opening a named app). Substantive fee heads,
            # another provider or unknown conditions fail the whole-span proof.
            requests=[row for row in requests if not
                      projection_covers_span(question,row.get('clause_span'),projection)]
            entry=p.adapter.get('workflow',{});contract=projection.get('procedure_contract')
            scope=next((name for name,values in entry.get('procedure_scope_bindings',{}).items()
                        if contract in values),contract)
            channels=[name for name,values in entry.get('procedure_channel_bindings',{}).items()
                      if contract in values]
            support=[dict(span,role='requested_predicate') for span in projection['support_spans']]
            requests.append({'request_id':'R'+str(len(requests)+len(excluded)+1),'service_id':service,
                             'intent_id':'workflow','topic':entry.get('topic','workflow'),'role':'requested',
                             'channels':channels,'context_channel_mentions':[],'conditions':[],
                             'requested_facets':[],'period':None,'procedure_scope':scope,
                             'procedure_member_ids':projection['fact_ids'],'evidence_spans':support,
                             'clause_span':dict(scope_span,role='requested'),
                             'commit_basis':'source_order_member_projection','support_features':['ordered_procedure_metadata'],
                             'antecedent_turn':previous.get('turn_id') if service in previous.get('services',[]) else None,
                             'antecedent_clause':None,'hypothetical':False,'scenario_antecedents':[],
                             'mode':'information','condition_query':False,'references':[]})
            unresolved=[row for row in unresolved if not (
                row.get('kind') in {'predicate_unresolved','service_unresolved'}
                and projection_covers_span(question,row.get('span'),projection))]
        remaining_temporal=[q for q in temporal_scopes if not any(
            projection_covers_span(question,q['span'],projection) for projection in projections)]
        assignments,unbound_temporal=temporal_scope_bindings(remaining_temporal,requests)
        for index,qualifiers in assignments.items():
            requests[index]['conditions'].extend(temporal_condition(q) for q in qualifiers)
            for qualifier in qualifiers:
                if qualifier['event_missing']:
                    unresolved.append({'kind':'condition_operand_unresolved','span':qualifier['span']})
        unresolved.extend({'kind':'condition_target_unresolved','span':q['span']} for q in unbound_temporal)
        for modifier in nonrestrictive_modifiers:
            parents=[r for r in requests if r['intent_id'] in {'initial_funding','balance_treatment'}]
            if parents:
                distance=lambda r:max(0,modifier['start']-r['clause_span']['end'],r['clause_span']['start']-modifier['end'])
                nearest=min(distance(r) for r in parents)
                parents=[r for r in parents if distance(r)==nearest]
            if not parents:unresolved.append({'kind':'scope_reference_unresolved','span':modifier})
            elif any('amount_only' in r.get('requested_facets',[]) for r in parents):
                unresolved.append({'kind':'answer_scope_conflict','span':modifier})
        comparison_groups=self.comparison_groups(question,masked,frames,requests,comparison_cues)
        for group in comparison_groups:
            for request in requests:
                if request['request_id'] in group['request_ids']:
                    request.setdefault('comparison_group_ids',[]).append(group['group_id'])
                    if request['mode']=='information':request['mode']='compare'
        # Scoped heads default only to independently established business
        # predicates. No example or answer fact-ID provides an interpretation.
        explicit=unique(e['service_id'] for e in active_entities)
        services=unique(r['service_id'] for r in requests if r['service_id'])
        for i,r in enumerate(requests):
            if r.get('price_query_clause'):
                left,right=r['price_query_clause']
                relations.append({'type':'requested_dimension','request':r['request_id'],'dimension':'fee','clause_span':mark(question,left,right,'requested_dimension')})
            for other in requests[i+1:]:
                shared_comparisons=set(r.get('comparison_group_ids',[]))&set(other.get('comparison_group_ids',[]))
                if shared_comparisons and subject_key(r)!=subject_key(other):relations.append({'type':'comparison','left':r['request_id'],'right':other['request_id'],'comparison_group_ids':sorted(shared_comparisons)})
                elif r['clause_span']['start']==other['clause_span']['start']:
                    choice=any_span(r['clause_span']['text'],['or','ولا','aw'])
                    relations.append({'type':'alternative' if choice else 'coordination','left':r['request_id'],'right':other['request_id']})
                elif r['intent_id']!=other['intent_id']:
                    relations.append({'type':'coordination','left':r['request_id'],'right':other['request_id']})
            if r['intent_id'] in {'balance_treatment','transaction_status','refund_status','complaint_resolution_confirmation'}:
                choices=any_span(r['clause_span']['text'],['or','ولا','aw','wala'])
                if choices:
                    a=r['clause_span']['start'];left,right=choices[0]
                    relations.append({'type':'alternative_outcome','request':r['request_id'],'operator_span':mark(question,a+left,a+right,'alternative_operator'),'options':[mark(question,a,a+left,'user_outcome_alternative'),mark(question,a+right,r['clause_span']['end'],'user_outcome_alternative')],'verified_business_facts':False})
        foreign=unique(foreign+[name for r in requests for name in r.get('unsupported_named_provider',[])])
        mentioned=explicit or services or references
        if foreign and not explicit and not services:mentioned=[]
        if mentioned or foreign:
            per={s:unique(r['intent_id'] for r in requests if r['service_id']==s) for s in mentioned}
            for s in mentioned:
                if not per[s] and len(previous.get('services',[]))==1:per[s]=previous.get('requested_topics',[])
            p.store.set_business_context(cid,sid,{'services':mentioned,'mentioned_services':mentioned,'unsupported_named_providers':foreign,'requested_topics':unique(r['intent_id'] for r in requests),'requests_by_service':per,'turn_id':str(p.turn),'comparison_services':unique(previous.get('comparison_services',[])+mentioned),'raw_question':question,'referent_ambiguity':[u for u in unresolved if u['kind'] in {'ambiguous_service_name','service_reference_ambiguous'}],'new_topic':bool(foreign or explicit and set(explicit)!=set(previous.get('services',[]))),'request_references':[{k:r.get(k) for k in ['request_id','service_id','intent_id','channels','conditions','period','procedure_scope','requested_facets','inherited_scope','evidence_spans','clause_span','subject_references','object_antecedent','unsupported_named_provider']} for r in requests]})
        language=reply_language(question)
        if franco_reply_language(question):language='ar'
        if not re.search(r'[\u0621-\u064a]',question) and len(set(tokens(question))&{'what','which','how','when','is','are','do','does','the','for','from','and','can','through'})>=2:language='en'
        operator_annotations=global_semantics['operator_annotations']
        normalization=[r for r in context if r.get('feature') in {'predicate_subject','elliptic_modifier','forward_channel_scope'}]
        context=[r for r in context if r not in normalization]
        operators,rejected_operators=self.operator_commitments(question,global_semantics,requests,excluded,claims,context,relations)
        contract={'contract_revision':'scope_graph_2','raw_question':question,'requests':requests,'excluded_requests':excluded,'context_mentions':context,'hypothetical_mentions':[r for r in requests if r['hypothetical']],'user_claims':claims,'actor_frames':actor_frames,'obligations':obligations,'references':global_semantics['references'],'alternatives':[r for r in relations if r['type'] in {'alternative','alternative_outcome'}],'relations':operators,'graph_edges':relations,'unresolved_spans':unresolved,'decision':'interpret_then_retrieve' if any(r['service_id'] or r.get('unsupported_named_provider') for r in requests) else 'clarify','turn_id':str(p.turn),'trace':{'comparison_groups':comparison_groups,'considered':considered,'committed_count':len(requests),'excluded_count':len(excluded),'example_scope_imported':False,'entity_name_spans_protected':entities+foreign_entities,'whole_question_span_is_entailment':False,'role_before_ellipsis':True,'prior_context':previous,'discourse_normalization':normalization,'considered_operators':operator_annotations,'rejected_operator_candidates':rejected_operators}}
        slots=unique((r['service_id'],r['topic']) for r in requests if r['service_id'])
        scope={s+'|'+t:unique(c for r in requests if r['service_id']==s and r['topic']==t for c in r['channels']) for s,t in slots}
        periods={s+'|'+t:next((r['period'] for r in requests if r['service_id']==s and r['topic']==t),None) for s,t in slots}
        return {'services':services,'topics':unique(r['topic'] for r in requests),'slots':slots,'slot_conditions':scope,'slot_periods':periods,'conditions':unique(c for r in requests for c in r['channels']),'foreign':unique(foreign),'ambiguous':[],'context_used':any(r.get('antecedent_turn') for r in requests),'language':language,'request_contract':contract,'planning':'role-first clause scope graph; current spans and typed antecedents only'}
