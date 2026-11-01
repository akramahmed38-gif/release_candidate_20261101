"""Conservative claim audit for a recognized source workflow, never a fact store.

Unknown workflows require other grounding checks; this module does not certify them.
Reject the whole slot on missing, unsupported or reordered steps. Never repair
generated prose by deleting clauses and returning a misleading remainder.
"""
import re
from .canonical_context import norm

SOURCE_STEPS=[
 ('open_app','فتح تطبيق MyFawry',r'\b(?:open|launch|access|start)\s+(?:the\s+)?(?:my\s*fawry)(?:\s+app)?\b'),
 ('enter_wallet','الدخول إلى المحفظة',r'\b(?:enter|go\s+to|access|select|open)\s+(?:the\s+)?wallet\b'),
 ('my_savings','مدخراتي',r'\b(?:(?:select|choose|open|tap|go\s+to)\s+)?my\s+savings\b'),
 ('add_fund','إضافة صندوق',r'\b(?:(?:select|choose|tap)\s+)?add\s+(?:a\s+)?fund\b'),
 ('follow_registration','اتباع خطوات التسجيل',r'\bfollow\s+(?:the\s+)?registration\s*(?:steps|instructions|process)?\b'),
 ('conditional_branch','زيارة أقرب فرع فوري بلس عند توجيه التطبيق للعميل',r'\bvisit\s+(?:the\s+)?(?:nearest\s+)?fawry\s+plus\s+branch\b'),
]
def audit_workflow(source,answer):
    normalized=norm(source)
    if not all(norm(span) in normalized for _,span,_ in SOURCE_STEPS):
        return {'applicable':False,'passed':False,'reason':'no_reviewed_workflow_contract','claims':[]}
    text=str(answer);claims=[];positions=[]
    for name,span,pattern in SOURCE_STEPS:
        match=re.search(pattern,text,re.I)
        supported=bool(match)
        if match and re.search(r'\b(?:not|never|avoid|skip|without)\b',text[max(0,match.start()-15):match.start()],re.I):supported=False
        claims.append({'step':name,'source_span':span,'status':'supported' if supported else 'missing_or_contradicted'})
        if match:positions.append(match.start())
    condition=re.search(r'(?:if|when|only when)\s+(?:the\s+)?(?:app|application)\s+(?:directs|prompts|instructs)\s+(?:you|the customer)',text,re.I)
    if not condition:claims.append({'step':'branch_condition','status':'missing_or_contradicted','source_span':SOURCE_STEPS[-1][1]})
    # Closed rendering vocabulary for this exact procedure. Any residual
    # substantive wording is unverified, even if it carries an allowed citation.
    residue=text
    for _,_,pattern in SOURCE_STEPS:residue=re.sub(pattern,' ',residue,flags=re.I)
    residue=re.sub(r'(?:if|when|only when)\s+(?:the\s+)?(?:app|application)\s+(?:directs|prompts|instructs)\s+(?:you|the customer)',' ',residue,flags=re.I)
    residue=re.sub(r'\b(?:then|and|next|finally|first|to|the|you|should|must|azimut|workflow|steps|for|are)\b',' ',residue,flags=re.I)
    residue=re.sub(r'\bE\d+\b',' ',residue)
    residue=re.sub(r'[\W_\d]+',' ',residue).strip()
    if residue:claims.append({'step':'unverified_residual_claim','status':'unsupported','diagnostic':'unmatched substantive wording; no automatic clause deletion'})
    ordered=positions==sorted(positions)
    if not ordered:claims.append({'step':'source_order','status':'contradicted'})
    return {'applicable':True,'passed':all(c['status']=='supported' for c in claims),
            'claims':claims,'policy':'reject whole slot; retain source as authoritative; no automatic prose repair'}
