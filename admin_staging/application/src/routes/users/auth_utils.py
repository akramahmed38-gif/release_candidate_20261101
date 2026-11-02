import os
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET_KEY = os.environ["STAGING_JWT_SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("TRAINING_ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("TRAINING_REFRESH_TOKEN_EXPIRE_DAYS", "30"))
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def _encode_token(data: dict, expires_delta: timedelta, token_type: str):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + expires_delta
    to_encode.update({"exp": expire, "iat": now, "type": token_type})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(data: dict):
    return _encode_token(data, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES), ACCESS_TOKEN_TYPE)

def create_refresh_token(data: dict):
    return _encode_token(data, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS), REFRESH_TOKEN_TYPE)

def extract_auth_claims(payload: dict) -> dict:
    return {
        "sub": payload.get("sub"),
        "role": payload.get("role"),
        "email": payload.get("email"),
        "chatbot_test_access": payload.get("chatbot_test_access") is True,
    }

def decode_token(token: str, expected_token_type: Optional[str] = None):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    token_type = payload.get("type") or ACCESS_TOKEN_TYPE
    if expected_token_type and token_type != expected_token_type:
        raise JWTError("Invalid token type")
    return payload

security = HTTPBearer(auto_error=False)

def _get_cookie_access_token(request: Request) -> Optional[str]:
    return request.cookies.get("training_access_token") or request.cookies.get("access_token")

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    candidate_tokens = []
    if credentials and credentials.credentials:
        candidate_tokens.append(credentials.credentials)

    refreshed_access_token = getattr(request.state, "refreshed_access_token", None)
    if refreshed_access_token:
        candidate_tokens.append(refreshed_access_token)

    cookie_access_token = _get_cookie_access_token(request)
    if cookie_access_token:
        candidate_tokens.append(cookie_access_token)

    for token in candidate_tokens:
        try:
            payload = decode_token(token, expected_token_type=ACCESS_TOKEN_TYPE)
            return payload
        except Exception:
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token"
    )

if __name__ == "__main__":
    pass

# python -m src.routes.users.auth_utils
