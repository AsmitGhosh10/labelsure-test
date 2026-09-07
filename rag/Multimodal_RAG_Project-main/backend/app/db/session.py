from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (create_async_engine, async_sessionmaker, AsyncSession)
from sqlalchemy import text
from .base import Base
from ..core.config import settings


engine = create_async_engine(
      settings.DATABASE_URL,
      echo=False,
      pool_pre_ping = True,
      pool_size = 10,
      max_overflow = 20,
)
AsyncSessionLocal = async_sessionmaker(
      bind = engine,
      expire_on_commit=False,
      autoflush=False,
      class_=AsyncSession,
)

# NOTE: Only for development. Use Alembic migrations in production.
async def init_db() -> None:
      """Initialize database (create tables)."""
      async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

#-----------FOR INTERNAL USAGE AND MANUAL CONTROL---------------------------------------------
@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
      async with AsyncSessionLocal() as session:
            try:
                  yield session
            except Exception:
                  await session.rollback()
                  raise
            finally:
                  await session.close()


#------FOR FASTAPI USAGE ----------------------------------------------------
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
      """Dependency generator for async session."""
      async with AsyncSessionLocal() as session:
            try:
                  yield session
            except Exception:
                  await session.rollback()
                  raise
            finally:
                  await session.close()