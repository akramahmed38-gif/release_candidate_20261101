"""Scoped rejection checks; independent answer review is still required."""
from collections import Counter,defaultdict
import re
from .canonical_context import norm
from .reply_language import _numbers


def business_numbers(text):
    text=re.sub(r'^\s*\d{1,2}[.)]\s+','',str(text),flags=re.M)
    text=re.sub(r'\bStep\s+\d{1,2}\s*[:.)-]?','',text,flags=re.I)
    values=_numbers(text)
    if re.search(r'\bfree\b|مجان',text,re.I):values['0']+=1
    for pattern,value in [(r'\b(?:two|اثنين|اثنان|اتنين|عمليتين|عمليتا)\b','2'),
                          (r'\b(?:three|ثلاث|ثلاثة)\b','3')]:
        if re.search(pattern,text,re.I):values[value]+=1
    return values


CHANNELS={
 'fawry_plus':r'فوري\s*بلس|fawry\s*plus',
 'atm':r'\batms?\b|الصراف\s*الالي',
 'axis_branch':r'فروع\s*(?:اكسس|اكسيس)|(?:axis|access)\s*(?:pay\s*)?branch(?:es)?',
 'instapay':r'انستاباي|انستا\s*باي|instapay',
}


def channel_bindings(text):
    text=norm(text);matches=[]
    for channel,pattern in CHANNELS.items():
        matches.extend((m.start(),m.end(),channel) for m in re.finditer(pattern,text,re.I))
    matches.sort();out=defaultdict(lambda:{'numbers':set(),'free':False})
    for i,(start,end,channel) in enumerate(matches):
        segment=text[end:matches[i+1][0] if i+1<len(matches) else len(text)]
        # Ignore heading-only channel mentions before the next explicit label.
        out[channel]['numbers'].update(business_numbers(segment))
        free=bool(re.search(r'مجان|\bfree\b|\b(?:no|without|zero)\b.{0,25}\b(?:fees?|charges?)\b',segment))
        denied=bool(re.search(r'\bnot\s+free\b',segment))
        out[channel]['free']|=free and not denied
    return dict(out)


def limit_bindings(text):
    text=norm(text);events=[]
    for rx,label in [(r'(?:اول|first|initial)\s+(?:3|three)\s*(?:شهور|اشهر|months?)','first_3_months'),
                     (r'(?:بعد|after)\s+(?:3|three)\s*(?:شهور|اشهر|months?)','after_3_months')]:
        events.extend((m.start(),m.end(),'period',label) for m in re.finditer(rx,text))
    for rx,label in [(r'اليومي|يوميا|\bdaily\b|\bper day\b|\beach day\b','daily'),
                     (r'الشهري|شهريا|\bmonthly\b|\bper month\b|\beach month\b','monthly'),
                     (r'العمليه الواحده|\bper (?:single )?(?:transaction|withdrawal)\b|\bsingle (?:transaction|withdrawal)\b','per_transaction'),
                     (r'لرصيد|رصيد الكارت|\b(?:maximum )?(?:wallet |card )?balance\b','balance')]:
        events.extend((m.start(),m.end(),'limit',label) for m in re.finditer(rx,text))
    events.sort();period='general';out=defaultdict(set)
    for i,(start,end,kind,label) in enumerate(events):
        if kind=='period':period=label;continue
        segment=text[end:events[i+1][0] if i+1<len(events) else len(text)]
        out[(period,label)].update(business_numbers(segment))
    return dict(out)


def scoped_numeric_checks(source, answer, topic):
    if set(business_numbers(source))!=set(business_numbers(answer)):
        return False,'numeric_values_codes_or_counts_changed'
    if topic in ('deposit','withdrawal','fees'):
        expected=channel_bindings(source);actual=channel_bindings(answer)
        for channel,facts in expected.items():
            if not facts['numbers'] and not facts['free']:continue
            candidate=actual.get(channel)
            if candidate is None:return False,'transaction_channel_missing'
            if not facts['numbers']<=candidate['numbers']:return False,'value_assigned_to_wrong_channel'
            if facts['free'] and not candidate['free']:return False,'free_channel_condition_missing'
    if topic=='limits':
        expected=limit_bindings(source);actual=limit_bindings(answer)
        for scope,values in expected.items():
            if values and not values<=actual.get(scope,set()):return False,'limit_period_or_type_changed'
    if topic=='activation' and re.search(r'ايداع.{0,30}20',norm(source)) and re.search(r'رصيد',source):
        if not re.search(r'\bdeposit\b',answer,re.I):return False,'minimum_deposit_misrepresented_as_fee'
        if not re.search(r'\bbalance\b|credited|remains|added to',answer,re.I):return False,'deposit_credit_condition_missing'
    return True,None
