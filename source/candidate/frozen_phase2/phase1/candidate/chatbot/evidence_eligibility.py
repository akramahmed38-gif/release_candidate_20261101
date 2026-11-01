"""Answer eligibility is separate from operational-policy approval.

Source-verified training evidence can support attributed RAG answers. It never
acquires a business-owner approval merely by passing extraction or retrieval.
"""
from dataclasses import dataclass, asdict
import re

from .canonical_context import norm
from .passage_quality import contains_interpretation_instructions, held_policy_instruction
from .sensitive_data import redact_text


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    tier: str
    reason: str
    operational_policy_approved: bool = False

    def to_dict(self):return asdict(self)


def unsafe_reason(unit):
    text=str(unit.get('body') or '');heading=str(unit.get('heading') or '')
    value=norm(heading+' '+text)
    if unit.get('sensitive_exclusion_reason'):return unit['sensitive_exclusion_reason']
    if unit.get('explicit_quarantine') or contains_interpretation_instructions(text):
        return 'source_directive_quarantined'
    if re.search(r'قواعد الاجابه|تعليمات.{0,30}(?:chatbot|للنموذج)|answering rules|question.routing',value,re.I):
        return 'source_directive_quarantined'
    if unit.get('requires_policy_review') or held_policy_instruction(text):
        return 'explicit_business_policy_hold'
    if (re.search(r'تاريخ ميلاد|date of birth|birth date',value) and
            re.search(r'(?:يتم تسجيله|يسجل|تسجيل|record|enter|set).{0,30}1980',value)):
        return 'unapproved_identity_value_substitution'
    if 'azimut' in unit.get('service_ids',[]) and re.search(
            r'اهداف الاستثمار المطلوبه|اجابات اجراءات الرقابه الداخليه|الدخل السنوي.{0,30}(?:اختيار|تحديد|ثابت)',value):
        return 'existing_azimut_preset_policy_hold'
    if redact_text(text,mask_email=True)!=text:
        return 'sensitive_values_or_personal_data_excluded'
    # A customer's instruction to choose their own PIN contains no credential.
    # Privileged device setup and actual labeled secret values remain excluded.
    secret_term=r'password|passphrase|\bPIN\b|\bOTP\b|الرقم\s+السري|كلم[ةه]\s*(?:المرور|السر)'
    if re.search(secret_term,text,re.I):
        privileged=(set(unit.get('service_ids',[])) & {'pos','pos_maintenance'} or
                    re.search(r'\badmin\b|default|افتراضي|اعاده ضبط|reset',value,re.I))
        if privileged:
            return 'privileged_credential_procedure_excluded'
        if re.search(r'(?:'+secret_term+r')\s*(?:هو|الحالي|الافتراضي|is|:|=)\s*[\w@!#$%]{3,}',text,re.I):
            return 'credential_value_excluded'
    if not text.strip():return 'empty_evidence'
    return None


def assess_unit(unit, slot, current, approved_scope=False):
    if not current:return Eligibility(False,'review_required','stale_or_removed_source')
    reason=unsafe_reason(unit)
    if reason:return Eligibility(False,'review_required',reason)
    if unit.get('verification') not in ('exact_source_lines','exact_source_segments','reviewed_repair','exact_source_and_explicit_owner_confirmation'):
        return Eligibility(False,'review_required','extraction_not_verified')
    if slot['service_id'] not in unit.get('service_ids',[]) or slot['topic_id'] not in unit.get('topic_ids',[]):
        return Eligibility(False,'review_required','service_topic_not_supported')
    if unit.get('scope_ambiguous'):
        return Eligibility(False,'review_required','ambiguous_service_or_fact_scope')
    if unit.get('conflict_group'):
        return Eligibility(False,'review_required','unresolved_same_scope_conflict')
    if approved_scope:return Eligibility(True,'approved_structured_fact','existing_scoped_owner_approval',True)
    return Eligibility(True,'source_verified_training_evidence','source_attributed_not_operational_policy_approval',False)
