"""Current-clause commitment, separated from role-qualified example proposals.

Uses selected authored linguistic features; no example scope, business answer,
fact ID or whole-question-only span can authorize a committed business request.
"""
from pathlib import Path
from functools import lru_cache
import json,re
from chatbot.query_language import reply_language
from annotation_candidates import lexical_candidates
ROOT=Path(__file__).resolve().parent
from linguistic_spans import shadow,forms,tokens,spans,mark
from session_context import scoped_business_context

class CurrentQueryPlanner:
    def __init__(self,definition,store):
        self.definition=definition;self.store=scoped_business_context(store);self.catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
        self.features=json.loads((ROOT/'resources/features.json').read_text(encoding='utf-8'))
        self.adapter=json.loads((ROOT/'resources/adapter.json').read_text(encoding='utf-8'))
        self.roles=json.loads((ROOT/'resources/entity_roles.json').read_text(encoding='utf-8'))
        self.entity_rules=json.loads((ROOT/'resources/entity_disambiguation.json').read_text(encoding='utf-8'))
        self.channels=json.loads((ROOT/'resources/channels.json').read_text(encoding='utf-8'))
        self.intents=json.loads((ROOT/'resources/intents.json').read_text(encoding='utf-8'))['intents']
        self.operators=json.loads((ROOT/'resources/operators.json').read_text(encoding='utf-8'))
        self.proposals=[json.loads(s) for s in (ROOT/'resources/role_qualified_candidates.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
        self.turn=0
    def feature_hits(self,text,masked=None):
        target=text if masked is None else masked
        return {k:[(a,b) for p in pp for a,b in spans(target,p)] for k,pp in self.features.items()}
    def entities(self,raw):
        from linguistic_spans import qualified_catalog_entities
        return qualified_catalog_entities(raw,self.definition['service_profiles'],self.roles,self.entity_rules)
    def channel_hits(self,raw):
        hits=[]
        for row in self.channels:
            if row['channel_id']=='other_unspecified':continue
            for aliases in row['aliases'].values():
                for alias in aliases:
                    for a,b in spans(raw,alias):hits.append({'channel':row['channel_id'],**mark(raw,a,b,'channel')})
        out=[]
        for h in sorted(hits,key=lambda h:-(h['end']-h['start'])):
            if any(h['start']>=p['start'] and h['end']<=p['end'] for p in out):continue
            out.append(h)
        return sorted(out,key=lambda h:h['start'])
    def predicate(self,text,masked):
        hits=self.feature_hits(text,masked);has=lambda k:bool(hits.get(k));goals=[];context=[]
        def add(i,*support):
            proof=sorted(set(x for key in support for x in hits.get(key,[])))
            if proof:goals.append({'intent_id':i,'predicate_spans':proof,'support_features':list(support),'commit_basis':'current_clause_predicate_components'})
        image=has('image') and (has('permission') or has('registration_context') or any(spans(text,p) for p in ['screenshot','external','صورة شاشة','صور الشاشات','صور خارجية']))
        if image:
            add('image_permission','image','permission')
            context.extend(k for k in ['registration_context','phone_owner','opening'] if has(k))
        if has('code'):add('transaction_code','code');context.extend(k for k in ['withdrawal'] if has(k))
        fee=has('fee') or any(spans(text,p) for p in ['free','مجاني','ببلاش'])
        initial=has('initial') or has('activation')
        if has('opening') and fee and not image:add('opening_fee','opening','fee')
        if initial and not image and not has('code'):add('initial_funding','initial','activation')
        if has('balance_disposition') and not image:add('balance_treatment','balance_disposition','balance')
        if has('deposit') and fee and not initial and not image:add('deposit_tariff','deposit','fee')
        if has('withdrawal') and fee and not image:add('withdrawal_tariff','withdrawal','fee')
        if has('identity') and not image and not any(spans(text,p) for p in ['transaction ID','complaint ID','reference ID']):add('identity','identity')
        owner_explicit=any(spans(text,p) for p in ['ownership','owner','registered','whose name','باسم','ملكية','مسجل','melkeyet'])
        if has('phone_owner') and owner_explicit and not image:add('phone_ownership','phone_owner')
        if has('existing_wallet') and not image:add('existing_wallet','existing_wallet')
        if has('documents') and not image:add('documents','documents')
        if has('workflow') and not image:add('workflow','workflow')
        if has('branch') and has('branch_condition') and not has('deposit') and not has('withdrawal'):add('branch_condition','branch','branch_condition')
        if not goals:
            # Explicit payment verb outside a protected brand remains an
            # operation even when its recipient/purpose still needs evidence.
            # These heads come from the payment meaning's authored cues; they
            # provide no payment policy or service availability.
            for word in ['pay','paying','payment','ادفع','دفع','سداد','adfa3','edfa3']:
                support=spans(masked,word)
                if support:
                    goals.append({'intent_id':'payment','predicate_spans':support,'support_features':['explicit_payment_head'],'commit_basis':'current_clause_operation_head'})
                    break
        # Other meanings require an explicit multiword cue in the current
        # clause. Similar examples can be considered, never imported as goals.
        core={k for k,v in self.adapter.items() if v.get('topic')}
        for row in self.intents:
            iid=row['intent_id']
            if iid in core or iid in {'other_or_unknown','permission','explanation','payment'}:continue
            for k in ['ar_eg_cues','ar_msa_cues','en_cues','franco_eg_cues']:
                for cue in row.get(k,[]):
                    if len(tokens(cue))<2:continue
                    for a,b in spans(masked,cue):goals.append({'intent_id':iid,'predicate_spans':[(a,b)],'support_features':['current_multiword_cue'],'commit_basis':'current_clause_multiword_cue'})
        merged={}
        for g in goals:
            if g['intent_id'] in merged:merged[g['intent_id']]['predicate_spans']+=g['predicate_spans']
            else:merged[g['intent_id']]=g
        return list(merged.values()),hits,context
    def plan(self,question,cid,sid):
        from scope_graph import ScopeGraph
        if not hasattr(self,'scope_graph'):self.scope_graph=ScopeGraph(self)
        return self.scope_graph.plan(question,cid,sid)
