"""Catalog matching and clause association; no question->answer rules."""
from pathlib import Path
import json,re
from chatbot.canonical_context import Planner,norm,mentions
from chatbot.query_language import normalize_franco,reply_language
ROOT=Path(__file__).resolve().parent
class CatalogPlanner:
    def __init__(self,definition,store):
        self.definition=definition;self.store=store;self.entities=Planner(definition['service_profiles'])
        self.catalog=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))
        self.facets={k:[norm(a) for a in v] for k,v in self.catalog['facets'].items()}
        self.qualifiers={k:[norm(a) for a in v] for k,v in self.catalog['qualifiers'].items()}
    def detect(self,text,table):
        # General English plural inflection, applied equally to all facets;
        # service aliases and original question/evidence stay unchanged.
        singular=re.sub(r'\b([a-z]{4,})s\b',lambda m:m.group(1),text)
        return [name for name,aliases in table.items() if any(mentions(text,alias) or mentions(singular,re.sub(r's$','',alias) if re.fullmatch(r'[a-z]{5,}s',alias) else alias) for alias in aliases)]
    def topics(self,text):
        topics=self.detect(text,self.facets);q=set(self.detect(text,self.qualifiers))
        if 'withdrawal' in topics:
            funding=[a for a in self.facets['initial_deposit'] if a not in ['minimum','اقل']]
            if not any(mentions(text,a) for a in funding):topics=[t for t in topics if t!='initial_deposit']
        if 'ongoing_balance_limit' in topics:
            topics=[t for t in topics if t not in ['initial_deposit','balance_treatment']]
        if 'deposit_tariff' in topics and 'initial_scope' not in q:topics=[t for t in topics if t!='initial_deposit']
        elif 'deposit_tariff' in topics and 'initial_scope' in q:topics.remove('deposit_tariff')
        if 'balance_treatment' in topics and 'initial_deposit' not in topics:topics.append('initial_deposit')
        if 'initial_deposit' in topics and 'balance_treatment' not in topics:topics.append('balance_treatment')
        if topics and 'fee' in q and not set(topics)&{'withdrawal','deposit_tariff','discounts','documents'}:
            if 'opening_fee' not in topics:topics.append('opening_fee')
        return list(dict.fromkeys(topics))
    def plan(self,question,cid,sid):
        text=norm(normalize_franco(question));previous=self.store.get_business_context(cid,sid) or {}
        entities=self.entities.plan(question);services=entities.services
        # Bare KYC qualifies the explicitly named product's topic. Other
        # explicit quality-service aliases keep their existing service role.
        if 'quality_kyc' in services and any(s!='quality_kyc' for s in services):
            aliases=self.definition['service_profiles']['quality_kyc']['aliases']
            if not any(mentions(text,norm(a)) for a in aliases if norm(a)!='kyc'):
                services=[s for s in services if s!='quality_kyc']
        qualifiers=set(self.detect(text,self.qualifiers));topics=self.topics(text)
        known=set(f['service_id'] for f in self.definition['facts']);foreign=[s for s in services if s not in known]
        if 'unsupported_named_service' in qualifiers:foreign.append('unsupported_named_service')
        inherited=False
        if entities.ambiguous:services=[];foreign.extend('ambiguous:'+s for s in entities.ambiguous)
        if not services and not foreign:
            if previous:
                services=previous['services'];inherited=True
                if 'comparison_reference' in qualifiers:services=previous.get('comparison_services',services)
                if not topics:topics=previous['topics']
            elif topics or not qualifiers&{'followup','comparison_reference'}:
                services=[self.definition['fixture_default_service']]
        elif services and not topics and previous:
            topics=previous['topics'];inherited=True
        # Related fact dependencies are not inherited as additional requested
        # topics after a service switch; only explicit or prior requested facets.
        if services!=previous.get('services') and inherited and 'initial_deposit' in topics:
            topics=[t for t in topics if t!='balance_treatment']
        available_services=[s for s in services if s in known]
        parts=[p.strip() for p in re.split(r';|؛|\band\b|\bwhile\b|\bwhereas\b|\sو\s*',text) if p.strip()]
        clauses=[];pending=[]
        for part in parts:
            ss=[s for s in self.entities.plan(part).services if s in known];tt=self.topics(part)
            if ss and not tt:
                if clauses:clauses[-1][0].extend(s for s in ss if s not in clauses[-1][0])
                else:pending.extend(ss)
            elif ss and tt:
                clauses.append((list(dict.fromkeys(pending+ss)),tt));pending=[]
            elif tt and clauses:clauses[-1][1].extend(t for t in tt if t not in clauses[-1][1])
        independent=len(available_services)>1 and len(clauses)>1 and all(ss and tt for ss,tt in clauses) and set(s for ss,tt in clauses for s in ss)==set(available_services)
        slots=[]
        if independent:
            for ss,tt in clauses:
                slots.extend((s,t) for s in ss for t in tt)
        else:slots=[(s,t) for s in available_services for t in topics or ['unspecified']]
        # Do not report a balance disposition when the request only asks about
        # activation funding: the fact bundle retains its condition itself.
        explicit_balance=bool(self.detect(text,{'balance':self.facets['balance_treatment']}))
        if not explicit_balance:slots=[(s,t) for s,t in slots if t!='balance_treatment']
        comparisons=list(dict.fromkeys(previous.get('comparison_services',[])+available_services))
        if available_services:self.store.set_business_context(cid,sid,{'services':available_services,'topics':topics,'comparison_services':comparisons})
        conditions=list(entities.conditions)
        for channel in ['atm','branch']:
            if channel in qualifiers and channel not in conditions:conditions.append(channel)
        language=reply_language(question)
        if not re.search(r'[\u0621-\u064a]',question):
            words=set(re.findall(r'[a-z]+',question.casefold()))
            english_function={'what','which','when','where','why','how','is','are','does','do','the','through','provided','whether','for','from','and'}
            if len(words&english_function)>=2:language='en'
        return {'services':available_services,'topics':topics,'slots':list(dict.fromkeys(slots)),'foreign':foreign,'context_used':inherited,'language':language,'conditions':conditions,'ambiguous':entities.ambiguous,'planning':'canonical aliases + catalog facets and fact scopes'}
