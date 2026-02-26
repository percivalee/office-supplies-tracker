from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app_runtime import STATIC_DIR
from database import init_db
from routers.imports import router as imports_router
from routers.items import router as items_router
from routers.system import router as system_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库。"""
    await init_db()
    yield


app = FastAPI(title="办公用品采购追踪系统", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(system_router)
app.include_router(items_router)
app.include_router(imports_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
