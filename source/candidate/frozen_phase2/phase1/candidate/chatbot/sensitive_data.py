"""Sanitize at persistence/output boundaries; never inspect real credentials."""
import logging
import re
import unicodedata

_KEY = re.compile(r'password|passwd|passphrase|secret|api.?key|authorization|cookie|(?:access|refresh|session).?token|كلم[ةه]\s*(?:المرور|السر)|الرقم\s*السر[يى]|رمز\s*الدخول|مفتاح\s*api|^(?:pin|otp)$', re.I)
_ASSIGNMENT = re.compile(r'''(?ix)(["']?(?:password|passwd|passphrase|secret|api[_ -]?key|authorization|cookie|(?:access|refresh|session)[_ -]?token)["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}\r\n]+)''')
_BEARER = re.compile(r'\b(?:Bearer|Basic)\s+[^\s,;]+', re.I)
_JWT = re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b')
_EMAIL = re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b')


def _arabic_label(label):
    return ''.join(r'\s*' if ch.isspace() else re.escape(ch)+r'[\u064b-\u065f]*' for ch in label)


_ARABIC_LABELS='|'.join(_arabic_label(label) for label in ('كلمة المرور','كلمه المرور','كلمة السر','كلمه السر','الرقم السري','الرقم السرى','رمز الدخول','مفتاح API'))
_SECRET_LINE=re.compile(r'''(?im)((?:password|passwd|passphrase|secret|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|'''+_ARABIC_LABELS+r''')["']?\s*[:：=]\s*)[^\r\n]+''')


def sensitive_key(key):
    value=''.join(ch for ch in unicodedata.normalize('NFKD',str(key)) if not unicodedata.combining(ch))
    return bool(_KEY.search(value))


def redact_text(value, mask_email=True):
    value=_SECRET_LINE.sub(lambda match:match[1]+'[REDACTED]',str(value))
    value = re.sub(r'(?im)((?:authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+', r'\1[REDACTED]', str(value))
    value = _BEARER.sub('[REDACTED_AUTH]', str(value))
    value = _JWT.sub('[REDACTED_TOKEN]', value)
    value = _ASSIGNMENT.sub(lambda m: m[1] + '[REDACTED]', value)
    value = re.sub(r'''(?i)(\b(?:PIN|OTP)["']?\s*[:=]\s*["']?)\d{3,10}\b''',r'\1[REDACTED]',value)
    return _EMAIL.sub('[REDACTED_EMAIL]', value) if mask_email else value


def sanitize(value, mask_email=True):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if sensitive_key(key) else sanitize(item,mask_email) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [sanitize(item,mask_email) for item in value]
    return redact_text(value,mask_email) if isinstance(value, str) else value


class SafeLogFilter(logging.Filter):
    def filter(self, record):
        # Formatting first also covers structured arguments; never render exception messages.
        try:
            record.msg = redact_text(record.getMessage())
        except Exception:
            record.msg = 'Log formatting failed; details suppressed.'
        if re.search(r'''\b(?:(?:raw_|original_|normalized_|resolved_)?(?:question|answer)|user_identifier|username|employee_id|employee_name)["']?\s*[=:]''', record.msg,re.I):
            event = re.search(r'event="([a-z_]+)"', record.msg)
            record.msg = 'event=' + (event[1] if event else 'sensitive_diagnostic') + ' content_omitted=True'
        record.args = ()
        if record.exc_info:
            record.msg += ' error_type=' + record.exc_info[0].__name__
            record.exc_info = None
            record.exc_text = None
        record.stack_info = None
        return True
