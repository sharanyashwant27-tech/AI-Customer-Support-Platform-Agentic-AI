"""Async SQLAlchemy database session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables if they do not exist and seed reference data."""
    from app.db import models  # noqa: F401
    from app.db.repositories.entities import agent_repo, product_repo

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        try:
            await agent_repo.ensure_defaults(session)
            for sku, name, price in (
                ("SKU-WH-01", "Wireless Headphones Pro", 129.99),
                ("SKU-KB-02", "Mechanical Keyboard", 89.0),
                ("SKU-MS-03", "Ergonomic Mouse", 49.0),
                ("SKU-LT-01", "Laptop", 999.0),
            ):
                await product_repo.upsert_sku(
                    session, sku=sku, name=name, unit_price=price
                )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
