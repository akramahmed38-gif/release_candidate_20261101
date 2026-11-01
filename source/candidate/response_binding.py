"""Pure response-binding directives; no operational/business predicates."""
import re
from linguistic_spans import shadow,tokens,egyptian_negative_verbs


def binding_preservation_directive(raw):
    text,coords=shadow(raw)
    action=None
    for row in egyptian_negative_verbs(raw):
        if row['stem'] in {'تبدل','تستبدل','تخلط'}:
            action=(row['start'],row['end'])
            break
    if action is None:
        hit=re.match(r"^\s*(?:do\s+not|don't|never)\s+(?:swap|mix|confuse|interchange)\b",text,re.I)
        if hit:
            action=(coords[hit.start()],coords[hit.end()-1]+1)
    if action is None:
        return None
    masked=raw[:action[0]]+' '*(action[1]-action[0])+raw[action[1]:]
    words=set(tokens(masked))
    objects=set(tokens('requested answers answer information requirements requests meanings المطلوب المطلوبات الاجابات الاجابه الاجابة المعلومات الشروط الطلبات'))
    relations=set(tokens('them between among respective providers services بينهم بينهما بعض بعضها ببعض'))
    grammar=set(tokens('the these those their each for of with up please و ف'))
    if not words or not words <= objects|relations|grammar:
        return None
    if not words&relations:
        return None
    return {'operator_span':{'start':action[0],'end':action[1],'text':raw[action[0]:action[1]]}}
