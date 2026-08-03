import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import User
from app.db.session import get_db

security = HTTPBearer(auto_error=False)
TOKEN_TTL_HOURS = 24


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + base64.urlsafe_b64encode(salt + digest).decode()


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not encoded.startswith("scrypt$"):
        return False
    raw = base64.urlsafe_b64decode(encoded.split("$", 1)[1])
    return hmac.compare_digest(raw[16:], hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1))


def issue_token(user_id: int) -> str:
    payload = {"sub": user_id, "exp": int((datetime.now(UTC) + timedelta(hours=TOKEN_TTL_HOURS)).timestamp())}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    key = get_settings().app_secret.get_secret_value().encode()
    signature = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        body, signature = credentials.credentials.split(".", 1)
        key = get_settings().app_secret.get_secret_value().encode()
        if not hmac.compare_digest(signature, hmac.new(key, body.encode(), hashlib.sha256).hexdigest()):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload["exp"]) < int(datetime.now(UTC).timestamp()):
            raise ValueError
        user = await db.get(User, int(payload["sub"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="登录已失效") from None
    if user is None or user.status != "ACTIVE":
        raise HTTPException(status_code=401, detail="账户不可用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return user
