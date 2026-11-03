"""A signed session never substitutes for a current authorized account."""
def account_matches(payload,employee):
    if not payload or employee is None:return False
    subject=str(payload.get('sub') or '').strip()
    email=str(payload.get('email') or '').strip().lower()
    role=str(payload.get('role') or payload.get('department') or '').strip().lower()
    return bool(subject and email and role and
        subject==str(getattr(employee,'employee_id','')).strip() and
        email==str(getattr(employee,'email','')).strip().lower() and
        role==str(getattr(employee,'department','')).strip().lower())
