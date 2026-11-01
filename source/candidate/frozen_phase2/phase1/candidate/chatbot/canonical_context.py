"""Generation-local service/topic planning. Catalog labels are discovery, not facts."""
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from contextvars import ContextVar
import re
import unicodedata

REQUEST = ContextVar('canonical_request', default=None)


@contextmanager
def canonical_request(value):
    token = REQUEST.set(value)
    try:
        yield
    finally:
        REQUEST.reset(token)


def norm(value):
    value = unicodedata.normalize('NFKC', str(value)).casefold()
    value = value.translate(str.maketrans('أإآٱىةؤئ', 'اااايهوي'))
    value = ''.join(c for c in value if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', value).strip()


TOPICS = {
    'deposit': ('إيداع', 'ايداع', 'deposit', 'deposits', 'cash in'),
    'withdrawal': ('سحب', 'السحب', 'withdrawal', 'withdrawals', 'withdraw', 'cash out'),
    'activation': ('تفعيل', 'التفعيل', 'activation', 'activate'),
    'registration': ('تسجيل', 'فتح حساب', 'فتح محفظة', 'registration', 'register'),
    'documents': ('اوراق', 'الاوراق', 'مستندات', 'المستندات', 'paperwork', 'documents', 'document', 'form'),
    'fees': ('رسوم', 'الرسوم', 'مصاريف', 'عمولة', 'fees', 'fee', 'charges', 'cost'),
    'limits': ('حدود', 'الحدود', 'الحد', 'حد اقصى', 'حد ادنى', 'limits', 'limit', 'maximum', 'minimum'),
    'eligibility': ('شروط', 'الشروط', 'eligibility', 'requirements', 'prerequisites'),
    'workflow': ('خطوات', 'الخطوات', 'اجراءات', 'الاجراءات', 'steps', 'procedure', 'process'),
    'transaction_codes': ('كود', 'الكود', 'اكواد', 'codes', 'code'),
    'kyc_identity': ('kyc', 'هوية', 'الهويه', 'رقم قومي', 'identity', 'national id'),
    'risk_compliance': ('fatca', 'aml', 'مخاطر', 'امتثال', 'compliance', 'high risk'),
    'promotions': ('خصم', 'الخصم', 'خصومات', 'discount', 'discounts', 'offers', 'عرض'),
    'transfer': ('تحويل', 'transfer'),
    'exceptions': ('استثناء', 'exceptions', 'exception'),
    'timeline': ('مدة', 'فترة', 'duration', 'period', 'timeline'),
    'overview': ('تعريف', 'يعني ايه', 'ما هو', 'what is', 'overview', 'meaning'),
}
CONDITIONS = {
    'atm': ('atm', 'صراف الي'), 'branch': ('branch', 'branches', 'فرع', 'فروع'),
    'monthly': ('monthly', 'each month', 'per month', 'شهري', 'كل شهر', 'في الشهر'),
    'daily': ('daily', 'per day', 'يومي'), 'high_risk': ('high risk', 'عالي المخاطر'),
}


def mentions(text, phrase):
    phrase = norm(phrase)
    # Egyptian writing commonly attaches Arabic conjunctions to Latin brands
    # (وQNB / وAXIS). These prefixes must not hide a second named service.
    prefix = r'(?:و|ب|لل|ال|وال)?'
    return list(re.finditer(r'(?<!\w)' + prefix + re.escape(phrase) + r'(?!\w)', text))


@dataclass
class QueryPlan:
    services: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    slots: list[dict] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    inherited: bool = False
    oversized: bool = False
    language: str = 'ar'
    has_explicit_topics: bool = False

    def to_dict(self):
        return asdict(self)


class Planner:
    def __init__(self, profiles, max_slots=24):
        self.profiles, self.max_slots = profiles, max_slots
        self.aliases = []
        extra = {'axis_pay': ['AXIS Pay Wallet', 'AXIS Wallet', 'اكسس باي', 'اكسس'],
                 'adib_wallet': ['محفظة ADIB', 'ADIB wallet'],
                 'adib_remittance': ['حوالة ADIB', 'حوالات ADIB', 'ADIB remittance'],
                 'qnb_wallet': ['QNB'], 'yellow_card': ['الكارت الاصفر']}
        for sid, spec in profiles.items():
            for alias in set(spec.get('aliases', []) + [spec['name']] + extra.get(sid, [])):
                if norm(alias) in ('adib', 'ابوظبي', 'ابو ظبي', 'wallet', 'محفظه', 'fawry'):
                    continue
                if len(norm(alias)) >= 3:
                    self.aliases.append((norm(alias), sid))
        self.aliases.sort(key=lambda pair: -len(pair[0]))

    def plan(self, question, previous=None, _associate=True):
        from .query_language import normalize_franco, reply_language
        q = norm(normalize_franco(question)); found = []; occupied = []
        for alias, sid in self.aliases:
            # An English request to contact support is not the Contact product.
            if alias == 'contact' and re.search(r'contact (?:support|us|the|customer)', q):
                continue
            for match in mentions(q, alias):
                if any(match.start() < b and a < match.end() for a, b in occupied):
                    continue
                occupied.append(match.span()); found.append((match.start(), sid))
        found = [sid for _, sid in sorted(found)]
        ambiguous = []
        adib = any(mentions(q, x) for x in ('adib', 'ابوظبي', 'ابو ظبي'))
        if adib and not any(s in found for s in ('adib_wallet', 'adib_remittance')):
            if not found and re.search(r'محفظ|wallet', q): found.append('adib_wallet')
            elif not found and re.search(r'حوال|remittance', q): found.append('adib_remittance')
            else: ambiguous = ['adib_wallet', 'adib_remittance']
        services = list(dict.fromkeys(found))
        if any(self.profiles[s]['family'] == 'wallets' and s != 'wallets_general' for s in services):
            services = [s for s in services if s != 'wallets_general']
        topic_chars = list(q)
        for a,b in occupied:
            topic_chars[a:b] = ' '*(b-a)
        topic_text = ''.join(topic_chars)
        topics = [t for t, aliases in TOPICS.items() if any(mentions(topic_text, a) for a in aliases)]
        modifiers = []
        if 'fees' in topics and set(topics) & {'deposit', 'withdrawal'}:
            topics.remove('fees'); modifiers.append('fees')
        if 'promotions' in topics and 'withdrawal' in topics:
            topics.remove('promotions'); modifiers.append('withdrawal_discount')
        if 'eligibility' in topics and set(topics) & {'activation','registration'}:
            topics.remove('eligibility'); modifiers.append('requirements')
        if len(topics)>1 and 'overview' in topics:
            topics.remove('overview')
        explicit_topics = bool(topics)
        if not topics: topics = ['overview']
        if services == ['wallets_general'] and topics != ['overview']:
            services = []
            ambiguous = [s for s,p in self.profiles.items() if p['family']=='wallets' and s!='wallets_general']
        conditions = [c for c, aliases in CONDITIONS.items() if any(mentions(q, a) for a in aliases)]
        if re.search(r'base fees?|standard fees?|normal fees?|رسوم.{0,15}(?:الاساسيه|العاديه)|قبل الخصم',q):
            modifiers.append('base_fees')
        if {'atm','branch'} <= set(conditions) and re.search(r'combined|total|together|اجمالي|المجموع|مع بعض',q):
            modifiers.append('aggregate_channel_rule')
        inherited = False
        # Explicit ambiguity never inherits a previous provider. An explicit
        # new provider replaces the previous service, transaction and conditions.
        if not services and not ambiguous and previous:
            services = list(previous.get('services', [])); inherited = bool(services)
            if not explicit_topics:
                topics = list(previous.get('topics', topics))
                modifiers = list(previous.get('modifiers',modifiers))
            if topics == previous.get('topics'):
                old = set(previous.get('conditions',[]))
                if set(conditions) & {'atm','branch'}: old -= {'atm','branch'}
                if set(conditions) & {'daily','monthly'}: old -= {'daily','monthly'}
                conditions = sorted(old | set(conditions))
        slots = [{'service_id':s, 'topic_id':t, 'conditions':list(conditions), 'modifiers':list(modifiers)}
                 for s in services for t in topics]
        if _associate and len(services)>1 and not ambiguous:
            # Bind asymmetric clauses independently. Shared lists such as
            # "QNB and AXIS: deposit, withdrawal and activation" remain a
            # Cartesian comparison; neither service silently loses a topic.
            parts=[p.strip() for p in re.split(r'\band\b|\bwhile\b|\bwhereas\b|[;؛]|\s+بينما\s+|\s+اما\s+|\s+و\s*',q) if p.strip()]
            if len(parts)>1:
                subplans=[self.plan(p,None,_associate=False) for p in parts]
                if (all(p.services and p.has_explicit_topics and not p.ambiguous for p in subplans)
                        and set(s for p in subplans for s in p.services)==set(services)):
                    slots=[];seen=set()
                    for p in subplans:
                        for slot in p.slots:
                            key=(slot['service_id'],slot['topic_id'],tuple(slot['conditions']),tuple(slot['modifiers']))
                            if key not in seen:slots.append(slot);seen.add(key)
        return QueryPlan(services, topics, slots, ambiguous, conditions, modifiers,
                         inherited, len(slots) > self.max_slots, reply_language(question),explicit_topics)
