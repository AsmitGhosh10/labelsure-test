from fastapi import APIRouter

from .endpoints.ingest import router as ingest_router
from .endpoints.search import router as search_router
from .endpoints.rag import router as rag_router
from .endpoints.explain import router as explain_router
from .endpoints.health import router as health_router
from .endpoints.logs import router as logs_router

api_router = APIRouter()

api_router.include_router(ingest_router, prefix="/ingest")
api_router.include_router(search_router, prefix="/search")
api_router.include_router(rag_router, prefix="/rag")
api_router.include_router(explain_router, prefix="/explain")
api_router.include_router(health_router, prefix="/health")
api_router.include_router(logs_router, prefix="/logs")
