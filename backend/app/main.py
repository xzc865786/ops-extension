import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.attachments.router import router as attachments_router
from app.auth.bridge import router as auth_router
from app.common.errors import AppError
from app.config import get_settings
from app.expenses.router import router as expenses_router
from app.reports.router import router as reports_router
from app.tickets.router import router as tickets_router

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
# Ensure access logs never print full Authorization / token (uvicorn still logs path; nginx should scrub)
logger = logging.getLogger("ops")

app = FastAPI(title="Ops Extension", version="1.0.0", docs_url="/ext/api/docs", openapi_url="/ext/api/openapi.json")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail, "code": getattr(exc, "code", None)},
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "code": "VALIDATION_ERROR"})


@app.get("/ext/api/health")
def health():
    return {"ok": True, "service": "ops-extension"}


app.include_router(auth_router)
app.include_router(tickets_router)
app.include_router(expenses_router)
app.include_router(reports_router)
app.include_router(attachments_router)
