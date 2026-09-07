from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import  AsyncSession

from .config import settings
from ..db.session import get_async_session

async def get_db() -> AsyncGenerator[AsyncSession, None]:
      """Dependency for database session."""
      async for session in get_async_session():
            yield session
