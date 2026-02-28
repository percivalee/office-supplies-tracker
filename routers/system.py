import asyncio
import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api_utils import safe_unlink, save_upload_file_with_limit
from app_runtime import RUNTIME_DIR, STATIC_DIR, UPLOAD_DIR
from backup_service import MAX_BACKUP_TOTAL_SIZE, build_backup_archive, restore_from_archive
from schemas import WebDAVConfigRequest, WebDAVRestoreRequest
from webdav_service import (
    WebDAVError,
    download_backup,
    list_backups,
    normalize_webdav_config,
    test_connection,
    upload_bytes,
)

router = APIRouter()
BACKUP_RESTORE_LOCK = asyncio.Lock()
WEBDAV_CONFIG_PATH = RUNTIME_DIR / ".webdav_config.json"


def _load_webdav_config() -> dict:
    if not WEBDAV_CONFIG_PATH.exists():
        return {}
    try:
        raw = WEBDAV_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {
            "base_url": str(data.get("base_url") or "").strip(),
            "username": str(data.get("username") or "").strip(),
            "password": str(data.get("password") or ""),
            "remote_dir": str(data.get("remote_dir") or "").strip(),
        }
    except (OSError, json.JSONDecodeError):
        return {}


def _save_webdav_config(config: dict) -> None:
    WEBDAV_CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        WEBDAV_CONFIG_PATH.chmod(0o600)
    except OSError:
        pass


def _public_webdav_config(config: dict) -> dict:
    base_url = str(config.get("base_url") or "").strip()
    username = str(config.get("username") or "").strip()
    remote_dir = str(config.get("remote_dir") or "").strip()
    password = str(config.get("password") or "")
    return {
        "configured": bool(base_url),
        "base_url": base_url,
        "username": username,
        "remote_dir": remote_dir,
        "has_password": bool(password),
    }


def _require_webdav_config() -> dict:
    config = _load_webdav_config()
    if not config.get("base_url"):
        raise HTTPException(status_code=400, detail="请先配置 WebDAV")
    return config


def _handle_webdav_error(error: Exception) -> None:
    if isinstance(error, WebDAVError):
        raise HTTPException(status_code=error.status_code, detail=str(error))
    raise HTTPException(status_code=500, detail=f"WebDAV 操作失败: {str(error)}")


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
    try:
        save_upload_file_with_limit(
            file,
            archive_path,
            max_bytes=MAX_BACKUP_TOTAL_SIZE,
            file_label="备份文件",
        )
    except HTTPException:
        safe_unlink(archive_path)
        raise
    except Exception as e:
        safe_unlink(archive_path)
        raise HTTPException(status_code=500, detail=f"写入备份文件失败: {str(e)}")
    finally:
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


@router.get("/api/webdav/config")
async def get_webdav_config():
    """读取 WebDAV 配置（不返回明文密码）。"""
    return _public_webdav_config(_load_webdav_config())


@router.put("/api/webdav/config")
async def set_webdav_config(request: WebDAVConfigRequest):
    """保存 WebDAV 配置。"""
    existing = _load_webdav_config()
    payload = request.model_dump()
    # 前端不回显密码时，允许留空并沿用已有密码。
    if not payload.get("password") and existing.get("password"):
        payload["password"] = existing["password"]
    try:
        config = normalize_webdav_config(payload)
        _save_webdav_config(config)
    except Exception as e:
        _handle_webdav_error(e)
    return {
        "message": "WebDAV 配置已保存",
        "config": _public_webdav_config(config),
    }


@router.post("/api/webdav/test")
async def test_webdav():
    """测试 WebDAV 连通性。"""
    config = _require_webdav_config()
    try:
        await run_in_threadpool(test_connection, config)
    except Exception as e:
        _handle_webdav_error(e)
    return {"message": "WebDAV 连接测试通过"}


@router.get("/api/webdav/backups")
async def list_webdav_backups():
    """列出 WebDAV 远端备份。"""
    config = _require_webdav_config()
    try:
        items = await run_in_threadpool(list_backups, config)
    except Exception as e:
        _handle_webdav_error(e)
    return {"items": items}


@router.post("/api/webdav/backup")
async def backup_to_webdav():
    """创建本地备份并上传到 WebDAV。"""
    config = _require_webdav_config()
    async with BACKUP_RESTORE_LOCK:
        try:
            archive_buffer, filename = await run_in_threadpool(build_backup_archive)
            upload_name = f"{Path(filename).stem}_{uuid4().hex[:8]}.zip"
            remote_url = await run_in_threadpool(
                upload_bytes, config, upload_name, archive_buffer.getvalue()
            )
        except Exception as e:
            _handle_webdav_error(e)
    return {
        "message": f"备份已上传到 WebDAV：{upload_name}",
        "filename": upload_name,
        "remote_url": remote_url,
    }


@router.post("/api/webdav/restore")
async def restore_from_webdav(request: WebDAVRestoreRequest):
    """从 WebDAV 下载指定备份并恢复。"""
    config = _require_webdav_config()
    filename = request.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename 不能为空")

    archive_path = UPLOAD_DIR / f"restore_webdav_{uuid4().hex}.zip"
    async with BACKUP_RESTORE_LOCK:
        try:
            content = await run_in_threadpool(download_backup, config, filename)
            with open(archive_path, "wb") as buffer:
                buffer.write(content)
            result = await run_in_threadpool(restore_from_archive, archive_path)
        except Exception as e:
            _handle_webdav_error(e)
        finally:
            safe_unlink(archive_path)

    return {
        "message": f"已从 WebDAV 恢复：{filename}，并恢复 {result['restored_upload_files']} 个上传文件",
        "restored_upload_files": result["restored_upload_files"],
        "filename": filename,
    }
