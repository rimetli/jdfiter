from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import email_hash
from app.core.auth import password_hash
from app.db.models import Organization, User
from app.db.session import get_db

router = APIRouter(prefix="/setup", tags=["setup"])


class BootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)


class AdminSetupRequest(BaseModel):
    email: str
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=128)


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict[str, bool]:
    count = await db.scalar(select(func.count()).select_from(Organization))
    users = await db.scalar(select(func.count()).select_from(User))
    return {"initialized": bool(count), "needs_admin_setup": bool(count) and not bool(users)}


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
async def bootstrap(payload: BootstrapRequest, db: AsyncSession = Depends(get_db)) -> dict:
    count = await db.scalar(select(func.count()).select_from(Organization))
    if count:
        raise HTTPException(status_code=409, detail="系统已经初始化")
    organization = Organization(name=payload.organization_name, status="ACTIVE")
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return {"organization_id": organization.id, "name": organization.name}


@router.post("/admin", status_code=status.HTTP_201_CREATED)
async def setup_admin(payload: AdminSetupRequest, db: AsyncSession = Depends(get_db)) -> dict:
    existing = await db.scalar(select(func.count()).select_from(User))
    if existing:
        raise HTTPException(status_code=409, detail="管理员已创建")
    organization = await db.scalar(select(Organization).order_by(Organization.id).limit(1))
    if organization is None:
        raise HTTPException(status_code=409, detail="请先初始化组织")
    admin = User(organization_id=organization.id, email_ciphertext=payload.email.strip().lower(), email_hash=email_hash(payload.email), display_name=payload.name.strip(), role="ADMIN", status="ACTIVE", password_hash=password_hash(payload.password))
    db.add(admin)
    await db.flush()
    await db.commit()
    return {"id": admin.id, "email": admin.email_ciphertext}
