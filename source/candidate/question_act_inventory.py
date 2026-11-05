"""Retain explicit additive interrogatives independently of business vocabulary.

This is a structural safety audit, not a semantic interpreter. It can detect an
unaccounted-for question act but cannot name its policy, resolve its role in all
forms of discourse, or infer an answer. Quotes are not employee instructions.
The closed-class grammar contains no service, business topic, amount or example.
"""
import re
from linguistic_spans import mark, shadow

_WORDS = re.compile(r"[a-z0-9]+|[\u0621-\u064a]+", re.I)
_QUOTES = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d|\u00ab[^\u00bb\n]*\u00bb|\u2018[^\u2019\n]*\u2019')
_BREAK = re.compile(r'(?<!\d)\.|\.(?!\d)|[;!?\u061b\u061f\n]')
# Interrogative heads and conjunctions are grammatical tokens. Auxiliary-only
# and nominal additions are intentionally outside this bounded audit's recall.
_HEADS = frozenset({'what','which','who','where','when','why','how','whether',
    '\u0647\u0644','\u0627\u064a\u0647','\u0645\u0627\u0630\u0627','\u0643\u064a\u0641','\u0641\u064a\u0646','\u0644\u064a\u0647',
    '\u0627\u0645\u062a\u064a','\u0627\u064a\u0646','\u0645\u062a\u064a','\u0645\u064a\u0646','emta','fein','ezay','leeh'})
_JOINS = frozenset({'and','also','w','we','\u0648'})


def additive_question_acts(raw):
    """Find intra-utterance question acts introduced by a conjunction.

    Attached Arabic waw is licensed only before a known interrogative particle;
    arbitrary nouns and entity names are never shortened to obtain a match.
    Original Unicode positions survive diacritics and normalization.
    """
    if not isinstance(raw,str):raise TypeError('Question must be text')
    masked=list(raw)
    for match in _QUOTES.finditer(raw):masked[match.start():match.end()]=' '*(match.end()-match.start())
    text,positions=shadow(''.join(masked));words=list(_WORDS.finditer(text));starts=[]
    for index,word in enumerate(words):
        value=word.group();left=word.start();join=None
        if value.startswith('\u0648') and value[1:] in _HEADS:
            join=(left,left+1);left+=1;value=value[1:]
        elif value in _HEADS and index and words[index-1].group() in _JOINS:
            previous=words[index-1]
            if text[previous.end():left].strip(' \t,:\u060c'):continue
            join=(previous.start(),previous.end())
        if join is None:continue
        # A turn-initial "and what about ..." is the first current-turn act,
        # not an extra question swallowed by an earlier current-turn predicate.
        # Leave it to the existing typed conversation/antecedent audit. This
        # audit must not invent a second obligation for a licensed follow-up.
        if not _WORDS.search(text[:join[0]]):continue
        start=positions[left];end=positions[word.end()-1]+1
        starts.append({'start':start,'head':mark(raw,start,end,'interrogative_head'),
                       'join':mark(raw,positions[join[0]],positions[join[1]-1]+1,'additive_join')})
    result=[]
    for index,item in enumerate(starts):
        stop=starts[index+1]['join']['start'] if index+1<len(starts) else len(raw)
        terminal=_BREAK.search(''.join(masked),item['start'],stop)
        if terminal:stop=terminal.start()
        while stop>item['start'] and raw[stop-1].isspace():stop-=1
        if stop<=item['head']['end']:continue
        result.append({'act_id':'A'+str(len(result)+1),'kind':'additive_interrogative',
                       'span':mark(raw,item['start'],stop,'question_act'),
                       'head_span':item['head'],'join_span':item['join']})
    return result


def audit_question_acts(raw,raw_demands):
    """A prior predicate or whole-clause span cannot discharge a later question.

    Input demands come from the separate original-question coverage enumerator,
    not the planner's committed request list or the assembler's selected facts.
    Narrow in-act predicate support or an explicit typed dialogue reference is
    required. This binding check is not semantic entailment or evidence approval.
    """
    acts=additive_question_acts(raw);unresolved=[]
    for act in acts:
        span=act['span'];bindings=[]
        for demand in raw_demands:
            if demand.get('role')!='requested':continue
            for proof in demand.get('evidence_spans',[]):
                a,b=proof.get('start'),proof.get('end')
                if type(a) is not int or type(b) is not int or not 0<=a<b<=len(raw):
                    raise ValueError('Invalid coverage proof span')
                if raw[a:b]!=proof.get('text'):raise ValueError('Coverage proof text mismatch')
                narrow=(span['start']<=a and b<=span['end'] and
                        (a>span['start'] or b<span['end']) and a>=act['head_span']['end'])
                predicate=proof.get('role')=='requested_predicate'
                reference=bool(demand.get('antecedent')) and proof.get('role') in {'referent','channel','dialogue_referent'}
                if narrow and (predicate or reference):
                    bindings.append({'raw_request_id':demand['request_id'],'proof_span':dict(proof),
                                     'basis':'current_act_predicate' if predicate else 'typed_dialogue_reference'})
        act['bindings']=bindings;act['resolved_meaning_established']=bool(bindings)
        if not bindings:
            unresolved.append({'code':'raw_uninterpreted_question_act','act_id':act['act_id'],
                               'span':dict(span),'head_span':dict(act['head_span']),
                               'reason':'Additional question has no narrow current-act meaning proof; source absence is not established.'})
    return {'schema_version':'question_act_inventory_1','acts':acts,'unresolved_acts':unresolved,
            'complete_permitted':not unresolved,'business_vocabulary_used':False,
            'planner_requests_used':False,'assembled_facts_used':False,
            'limitations':'Only intra-utterance explicit additive interrogative heads; initial follow-ups remain subject to existing typed context checks. Not exhaustive meaning or role recovery.'}
