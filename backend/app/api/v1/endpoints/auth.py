"""Auth endpoints — tolerate missing DB during bootstrap."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_optional
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db.models.user import User
from app.db.repositories.entities import customer_repo
from app.schemas.auth import Token, UserCreate, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> User:
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    customer = await customer_repo.get_or_create(
        db,
        email=payload.email,
        full_name=payload.full_name,
    )
    user = User(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        customer_id=customer.id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> Token:
    if db is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return Token(
        access_token=create_access_token(user.email, extra_claims={"role": user.role.value}),
        refresh_token=create_refresh_token(user.email),
    )


@router.post("/login", response_model=Token)
async def login_json(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession | None, Depends(get_db_optional)],
) -> Token:
    return await login_for_access_token(form_data, db)
