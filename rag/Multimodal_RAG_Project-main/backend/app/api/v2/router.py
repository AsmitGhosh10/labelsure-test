from fastapi import APIRouter

from .endpoints.ingest import api_router as upload_router


api_router = APIRouter()

api_router.include_router(upload_router, prefix="/upload")