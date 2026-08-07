"""FastAPI dependency injection helpers."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import decode_token
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,
)


async def get_current_settings() -> Settings:
    return get_settings()


async def get_db_optional() -> AsyncGenerator[AsyncSession | None, None]:
    """Yield a DB session when PostgreSQL is reachable; otherwise None."""
    session: AsyncSession | None = None
    try:
        session = AsyncSessionLocal()
        await session.execute(text("SELECT 1"))
    except Exception:
        if session is not None:
            await session.close()
        yield None
        return

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_current_user_optional(
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User | None:
    """Return authenticated user when token + DB are available; else None."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        email = payload.get("sub")
        if not email:
            return None

        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
    except AuthenticationError:
        return None
    except Exception:
        return None


async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
