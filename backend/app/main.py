import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app import auth, database
from backend.app.routers.auth_router import router as auth_api_router
from backend.app.routers.dashboard import router as dashboard_router
from backend.app.routers.inspection import router as inspection_router
from backend.app.routers.regulations import router as regulations_router
from backend.app.routers.review import router as review_router
from backend.app.services import legal

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create the schema and, if configured, the initial admin account."""
    database.init_db()
    created = auth.bootstrap_admin()
    if created:
        database.write_audit(
            action="ADMIN_BOOTSTRAPPED", actor="system", entity_id=created
        )
    yield


app = FastAPI(
    lifespan=lifespan,
    title="AI Legal Metrology Compliance Scanner",
    description=(
        "AI-assisted compliance screening. Package image -> quality gate -> OCR "
        "-> field extraction -> deterministic rule engine -> confidence-fused "
        "decision -> regulatory citation -> human sign-off.\n\n"
        + legal.DISCLAIMER
    ),
    version="1.1.0",
)

# CORS: locked to the configured origins. `*` stays the dev default so the
# local Gradio frontend works out of the box; set CORS_ORIGINS in production.
_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "*").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inspection_router, tags=["inspection"])
app.include_router(review_router, tags=["human-in-the-loop"])
app.include_router(dashboard_router, tags=["dashboard"])
app.include_router(regulations_router, tags=["regulations"])
app.include_router(auth_api_router, tags=["auth"])


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "legal-metrology-scanner",
        "version": app.version,
        "system_role": legal.SYSTEM_ROLE,
        "auth": auth.describe(),
    }
