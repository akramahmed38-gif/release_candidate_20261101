"""Source-bound non-numerical rejection checks; not a full entailment proof.

Numeric/channel/period guards remain independent and mandatory. Recognized
fields cannot migrate from a neighbouring slot merely because refs are valid.
"""
import re
from .canonical_context import norm
from .workflow_contract import audit_workflow

FIELDS=[
 ('customer_name',r'اسم العميل|اسم المستفيد|\bالاسم\b',r"(?:customer|client|recipient)(?:'s)?\s+name|name.{0,20}(?:their|the)\s+(?:id|identity)"),
 ('address',r'العنوان|عنوان العميل|محل السكن',r'\baddress\b'),
 ('country',r'\bالدوله\b|\bدوله\b|بلد الاقامه',r'\bcountry\b'),
 ('residence',r'الاقامه|محل السكن|السكن',r'\bresiden(?:ce|t|cy)\b'),
 ('nationality',r'الجنسيه',r'\bnationality\b'),
 ('passport',r'باسبور|جواز السفر',r'\bpassport\b'),
 ('employment_letter',r'\bhr\s*letter\b|خطاب.{0,20}عمل',r'\bhr\s*letter\b|employment letter'),
 ('utility_bill',r'ايصال مرافق',r'\butility\s+bills?\b'),
 ('document_requirement',r'مستند|اوراق|استماره|طلب الصرف|بطاقه|تحقيق الشخصيه|جواز السفر|باسبور',r'(?:required|necessary)\s+documents?|provid(?:e|ing).{0,20}documents?'),
]
WORKFLOW=[
 ('myfawry_app',r'my\s*fawry',r'my\s*fawry'),
 ('savings_navigation',r'مدخراتي|مدخراتى',r'\b(?:my\s+)?savings\b'),
 ('add_fund_navigation',r'اضافه صندوق',r'\badd(?:ing)?\s+(?:a\s+)?fund\b'),
]

def check_semantic_claims(source,answer,topic):
    original=norm(source);translated=str(answer or '')
    missing=[];unsupported=[]
    for name,arabic,english in FIELDS:
        source_supports=bool(re.search(arabic,original,re.I) or re.search(english,source,re.I))
        if re.search(english,translated,re.I) and not source_supports:unsupported.append(name)
    if 'جنيه' in original and not re.search(r'استرليني|\bgbp\b|غانا|\bghs\b|دولار|\busd\b|يورو|\beur\b',original,re.I):
        if re.search(r'\bghs\b|ghana|\bgbp\b|sterling|\busd\b|dollars?|\beur\b|euros?',translated,re.I):
            unsupported.append('currency_not_in_source')
    if 'ايداع' in original and 'رصيد' in original and re.search(r'يستقر|يضاف|اضافه',original):
        credited=bool(re.search(r'(?:deposit|amount).{0,100}(?:remain|credit|add|settle).{0,75}(?:wallet|account|balance)|(?:credit|add).{0,75}(?:wallet|account|balance)',translated,re.I))
        if not credited:missing.append('deposit_credited_to_customer_balance')
        if re.search(r'\b(?:without|no)\s+(?:a\s+)?deposit|deposit.{0,30}\bnot\s+(?:required|necessary|needed)\b',translated,re.I):
            unsupported.append('required_deposit_negated')
    if topic=='workflow':
        audit=audit_workflow(source,answer)
        if audit['applicable'] and not audit['passed']:
            unsupported.append('source_workflow_claim_contract_failed')
        for name,arabic,english in WORKFLOW:
            if re.search(arabic,original,re.I) and not re.search(english,translated,re.I):missing.append(name)
        if re.search(r'عند توجيه التطبيق|اذا وجه.{0,20}التطبيق',original) and not re.search(
                r'(?:if|when|only when).{0,65}(?:app|application).{0,35}(?:direct|prompt|instruct)|(?:if|when)\s+(?:you are\s+)?(?:directed|prompted|instructed)',translated,re.I):
            missing.append('branch_visit_only_when_app_directs')
    if re.search(r'توقيع.{0,30}ثلاثي',original):
        if re.search(r'\b(?:three|3)\s+times\b',translated,re.I):unsupported.append('signature_times_instead_of_name_parts')
        if not re.search(r'\b(?:three|3)[ -](?:part|name)|\b(?:three|3)\s+(?:name\s+)?(?:parts|components|names)\b|\btripartite\b',translated,re.I):
            missing.append('full_three_part_signature')
        if re.search(r'\bnot\s+(?:a\s+)?(?:three|3)[ -]part|(?:three|3)[ -]part.{0,30}\bnot required\b',translated,re.I):
            unsupported.append('required_signature_parts_negated')
    return {'passed':not (missing or unsupported),'missing_required_concepts':missing,
            'unsupported_claim_concepts':unsupported,'scope':'rejection filters, not complete semantic certification'}
