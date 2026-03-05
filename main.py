from contextlib import asynccontextmanager
import os
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app_locks import MAINTENANCE_MODE
from app_runtime import STATIC_DIR
from database import init_db
from db.audit_context import reset_current_operator_ip, set_current_operator_ip
from db.migrations import upgrade_database_to_head
from routers.imports import router as imports_router
from routers.items import router as items_router
from routers.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时执行数据库迁移并初始化数据库。"""
    upgrade_database_to_head()
    await init_db()
    yield


app = FastAPI(title="办公用品采购系统", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _resolve_operator_ip(request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded_for:
        first = forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    client_host = getattr(getattr(request, "client", None), "host", None)
    return str(client_host or "unknown")


@app.middleware("http")
async def audit_operator_context(request, call_next):
    token = set_current_operator_ip(_resolve_operator_ip(request))
    try:
        return await call_next(request)
    finally:
        reset_current_operator_ip(token)


@app.middleware("http")
async def maintenance_mode_guard(request, call_next):
    if MAINTENANCE_MODE.is_set():
        path = request.url.path
        if path.startswith("/api") and path not in {"/api/restore", "/api/webdav/restore"}:
            return JSONResponse(
                status_code=503,
                content={"detail": "系统正在执行数据恢复，请稍后重试"},
            )
    return await call_next(request)


app.include_router(system_router)
app.include_router(items_router)
app.include_router(imports_router)


_FALLBACK_STREAM = None


def _ensure_standard_streams() -> None:
    """兼容 --noconsole 打包：确保 stdout/stderr 可用。"""
    global _FALLBACK_STREAM
    if sys.stdout is not None and sys.stderr is not None:
        return
    if _FALLBACK_STREAM is None or _FALLBACK_STREAM.closed:
        _FALLBACK_STREAM = open(os.devnull, "w", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _FALLBACK_STREAM
    if sys.stderr is None:
        sys.stderr = _FALLBACK_STREAM


if __name__ == "__main__":
    import uvicorn

    _ensure_standard_streams()
    uvicorn.run(app, host="0.0.0.0", port=8000)
