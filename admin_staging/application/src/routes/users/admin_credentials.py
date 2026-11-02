"""File-backed administrator authentication; never log credential contents."""
import hashlib
import hmac
import json
import os
from pathlib import Path


def credential_path():
    target=Path(os.environ['STAGING_ADMIN_CREDENTIAL_PATH']).resolve()
    if target.parent!=Path(os.environ['STAGING_PRIVATE_ROOT']).resolve():
        raise RuntimeError('Staging credentials must be private and isolated')
    return target


def load_admin_credentials():
    try:
        data = json.loads(credential_path().read_text(encoding="utf-8-sig"))
        if data.get("iterations") != 600000:
            return {}
        if len(bytes.fromhex(data["salt"])) != 32 or len(bytes.fromhex(data["digest"])) != 32:
            return {}
        if not isinstance(data["username"], str) or not data["username"].strip():
            return {}
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def verify_admin_password(password):
    data = load_admin_credentials()
    if not data:
        return False
    calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(data["salt"]), data["iterations"])
    return hmac.compare_digest(calculated, bytes.fromhex(data["digest"]))
