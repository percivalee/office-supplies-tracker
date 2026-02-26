import asyncio
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api_utils import safe_unlink
from app_runtime import STATIC_DIR, UPLOAD_DIR
from backup_service import build_backup_archive, restore_from_archive

router = APIRouter()
BACKUP_RESTORE_LOCK = asyncio.Lock()


@router.get("/", response_class=HTMLResponse)
async def root():
    """返回主页。"""
    html_path = STATIC_DIR / "index.html"
    return FileResponse(html_path)


@router.get("/api/backup")
async def backup_data():
    """下载当前数据库与上传文件备份。"""
    async with BACKUP_RESTORE_LOCK:
        try:
            archive_buffer, filename = await run_in_threadpool(build_backup_archive)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")
    return StreamingResponse(
        archive_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/api/restore")
async def restore_data(file: UploadFile = File(...)):
    """从备份包恢复数据库与上传文件。"""
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="无效的备份文件名")
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="仅支持 .zip 备份文件")

    archive_path = UPLOAD_DIR / f"restore_{uuid4().hex}.zip"
    with open(archive_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    await file.close()

    async with BACKUP_RESTORE_LOCK:
        try:
            result = await run_in_threadpool(restore_from_archive, archive_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")
        finally:
            safe_unlink(archive_path)

    return {
        "message": f"恢复完成，已恢复数据库与 {result['restored_upload_files']} 个上传文件",
        "restored_upload_files": result["restored_upload_files"],
    }
