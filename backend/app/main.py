# run : uvicorn app.main:app --reload

'''Note: Khi deploy lên server thìdùng --workers 1 thay vì --reload
# VÍ DỤ: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1'''

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db import Base, SessionLocal, engine
from app.api.routes.auth_routes import router as auth_router
from app.api.routes.omr_routes import router as omr_router
from app.api.routes.history_routes import router as history_router
from app.error_handlers import register_exception_handlers
from app.services.job_service import mark_processing_jobs_failed_after_restart
from src.core.config import OUTPUTS_DIR, ensure_runtime_dirs

load_dotenv()
ensure_runtime_dirs()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="My_OEMER API",
    description="Optical Music Recognition API — Upload score images and get MusicXML + MIDI output",
    version="1.0.0",
)

register_exception_handlers(app)

cors_origins_raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
cors_origins = [item.strip() for item in cors_origins_raw.split(",") if item.strip()]

# Wildcard "*" requires allow_credentials=False (CORS spec / Starlette enforcement).
# This is fine: auth uses JWT in Authorization header, not cookies.
_allow_all = "*" in cors_origins


class NgrokCorsPreflightMiddleware(BaseHTTPMiddleware):
    """Handle CORS preflight (OPTIONS) before ngrok's interstitial page can interfere.

    Ngrok free tier injects an HTML warning page on requests that lack the
    ``ngrok-skip-browser-warning`` header.  Browsers never attach custom
    headers to automatic preflight OPTIONS requests, so ngrok returns its
    HTML page — which has **no** CORS headers — causing the browser to block
    the subsequent real request.

    This middleware short-circuits OPTIONS requests with the correct CORS
    headers so the preflight always succeeds, regardless of ngrok.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            origin = request.headers.get("origin", "*")
            resp_origin = "*" if _allow_all else origin
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": resp_origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers": "Authorization, Content-Type, ngrok-skip-browser-warning",
                    "Access-Control-Max-Age": "600",
                },
            )
        return await call_next(request)


# NgrokCorsPreflightMiddleware must be added first so it runs outermost.
app.add_middleware(NgrokCorsPreflightMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else cors_origins,
    allow_credentials=not _allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(omr_router, prefix="/omr", tags=["OMR"])
app.include_router(history_router, prefix="/history", tags=["History"])

app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


@app.on_event("startup")
def fail_interrupted_processing_jobs():
    db = SessionLocal()
    try:
        mark_processing_jobs_failed_after_restart(db)
    finally:
        db.close()


@app.get("/")
def root():
    return {"message": "My_OEMER API v1.0 is running"}
