from .core.logging_config import setup_logging

setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .core.config import settings

from .db.session import get_async_session, engine, init_db
from .api.v1.router import api_router
from .api.v2.router import api_router as api_router_v2


@asynccontextmanager
async def lifespan(app: FastAPI):
      #Startup
      
      
      
      await init_db()

      print(f"🚀 {settings.PROJECT_NAME} started in {settings.ENVIRONMENT} mode")
      yield

      #Shutdown
      await engine.dispose()
      print("👋 Application shutdown complete")

def create_app() -> FastAPI:
      app = FastAPI(
            title=settings.PROJECT_NAME,
            version="0.1.0",
            openapi_url=f"{settings.API_V1_STR}/openapi.json",
            lifespan=lifespan
      )

      app.add_middleware(
            CORSMiddleware, 
            allow_origins=[
                  "http://localhost:5173",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
      )

      app.include_router(api_router, prefix = settings.API_V1_STR)
      app.include_router(api_router_v2, prefix= settings.API_V2_STR)

      return app

