from fastapi import Depends, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ....core.dependencies import  get_db
from ....core.config import settings
from ....ml.retrieval.faiss_manager import FAISSManager

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
      """System health check endpoint."""

      status = "healthy"
      services: dict = {}

      #--------------
      #Database Check
      #--------------
      try:
            await db.execute(text("SELECT 1"))
            services["database"] = "ok"
      except Exception as e:
            services["database"] = f"error: {e}"
            status = "degraded"
      
      #--------------
      #Faiss Check
      #--------------
      try:
            faissManager = FAISSManager()
            await faissManager.ensure_loaded()

            total_vectors = faissManager.total_vectors

            services["faiss"] = {
                  "status" : "ok" if total_vectors > 0 else "empty",
                  "total_vectors": total_vectors
            }

            if total_vectors == 0:
                  status = "degraded"
      except Exception as e:
            services["faiss"] = f"error: {str(e)}"
            status = "degraded"
      
      #--------------
      #External API
      #--------------
      services["groq"] = "configured" if settings.GROQ_API_KEY else "missing"
      services["tavily"] = "configured" if settings.TAVILY_API_KEY else "missing"

      if not settings.GROQ_API_KEY:
            status = "degraded"
      
      return {
            "status" : status,
            "services" : services,
      }


      