import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    get_current_user,
    issue_token,
    password_hash,
    require_admin,
    verify_password,
)
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


def email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def serialize(user: User) -> dict:
    return {"id": user.id, "email": user.email_ciphertext, "name": user.display_name, "role": user.role, "organization_id": user.organization_id, "status": user.status, "created_at": user.created_at, "updated_at": user.updated_at}


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict:
    users = list(await db.scalars(select(User).where(User.email_hash == email_hash(payload.email))))
    user = users[0] if len(users) == 1 else None
    if user is None or user.status != "ACTIVE" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    return {"access_token": issue_token(user.id), "user": serialize(user)}


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return serialize(user)


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 10,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    statement = select(User).where(User.organization_id == admin.organization_id)
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    users = list(await db.scalars(statement.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)))
    return {"items": [serialize(user) for user in users], "total": total, "page": page, "page_size": page_size}


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> dict:
    digest = email_hash(payload.email)
    exists = await db.scalar(select(User).where(User.organization_id == admin.organization_id, User.email_hash == digest))
    if exists:
        raise HTTPException(status_code=409, detail="该邮箱已存在")
    user = User(organization_id=admin.organization_id, email_ciphertext=payload.email.strip().lower(), email_hash=digest, display_name=payload.name.strip(), role="USER", status="ACTIVE", password_hash=password_hash(payload.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return serialize(user)
