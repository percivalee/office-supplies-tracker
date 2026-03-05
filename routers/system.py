import json
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from api_utils import safe_unlink, save_upload_file_with_limit
from app_locks import DATA_MUTATION_LOCK, MAINTENANCE_MODE
from app_runtime import APP_STATE_DIR, STATIC_DIR, UPLOAD_DIR
from backup_service import (
    MAX_BACKUP_TOTAL_SIZE,
    build_backup_archive,
    build_backup_archive_file,
    inspect_backup_archive,
    restore_from_archive,
)
from database import init_db
from gemini_config import load_gemini_config, public_gemini_config, resolve_gemini_settings, save_gemini_config
from gemini_ocr import reset_gemini_model_cache
from schemas import (
    BackupHealthCheckResponse,
    GeminiConfigRequest,
    GeminiModelsRequest,
    WebDAVConfigRequest,
    WebDAVRestoreRequest,
)
from webdav_service import (
    WebDAVError,
    download_backup_to_file,
    prune_backups,
    upload_file,
    list_backups,
    normalize_webdav_config,
    test_connection,
)

router = APIRouter()
WEBDAV_CONFIG_PATH = APP_STATE_DIR / ".webdav_config.json"


def _validate_backup_filename(filename: str) -> str:
    """校验备份文件名与扩展名。"""
    normalized = (filename or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="无效的备份文件名")
    if Path(normalized).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="仅支持 .zip 备份文件")
    return normalized


async def _save_backup_upload(file: UploadFile, prefix: str) -> Path:
    """保存上传的备份压缩包并返回临时路径。"""
    archive_path = UPLOAD_DIR / f"{prefix}_{uuid4().hex}.zip"
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
    except Exception as exc:
        safe_unlink(archive_path)
        raise HTTPException(status_code=500, detail=f"写入备份文件失败: {str(exc)}")
    finally:
        await file.close()
    return archive_path


def _run_init_db_sync() -> None:
    """在线程池中执行 DB 初始化/迁移。"""
    asyncio.run(init_db())


def _load_webdav_config() -> dict:
    if not WEBDAV_CONFIG_PATH.exists():
        return {}
    try:
        raw = WEBDAV_CONFIG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        try:
            keep_backups = int(data.get("keep_backups") or 0)
        except (TypeError, ValueError):
            keep_backups = 0
        return {
            "base_url": str(data.get("base_url") or "").strip(),
            "username": str(data.get("username") or "").strip(),
            "password": str(data.get("password") or ""),
            "remote_dir": str(data.get("remote_dir") or "").strip(),
            "keep_backups": keep_backups,
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
    keep_backups = max(0, int(config.get("keep_backups") or 0))
    return {
        "configured": bool(base_url),
        "base_url": base_url,
        "username": username,
        "remote_dir": remote_dir,
        "keep_backups": keep_backups,
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


def _normalize_gemini_model_name(value: str) -> str:
    normalized = (value or "").strip()
    if normalized.startswith("models/"):
        return normalized
    return f"models/{normalized}" if normalized else ""


def _to_public_model_name(value: str) -> str:
    normalized = (value or "").strip()
    if normalized.startswith("models/"):
        return normalized.removeprefix("models/")
    return normalized


def _list_gemini_models(api_key: str) -> list[str]:
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 Gemini API Key")
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        names: list[str] = []
        for model in genai.list_models():
            methods = getattr(model, "supported_generation_methods", None) or []
            if "generateContent" not in methods:
                continue
            model_name = str(getattr(model, "name", "") or "").strip()
            public_name = _to_public_model_name(model_name)
            if public_name and public_name not in names:
                names.append(public_name)
        names.sort()
        return names
    except ModuleNotFoundError:
        raise HTTPException(status_code=500, detail="缺少 google-generativeai 依赖，无法获取 Gemini 模型列表")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败: {str(exc)}")


@router.get("/", response_class=HTMLResponse)
async def root():
    """返回主页。"""
    html_path = STATIC_DIR / "index.html"
    return FileResponse(html_path)


@router.get("/api/backup")
async def backup_data():
    """下载当前数据库与上传文件备份。"""
    async with DATA_MUTATION_LOCK:
        try:
            archive_buffer, filename = await run_in_threadpool(build_backup_archive)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")
    return StreamingResponse(
        archive_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/api/backup/health", response_model=BackupHealthCheckResponse)
async def backup_health_check(file: UploadFile = File(...)):
    """上传备份包并执行健康检查（不写入当前数据）。"""
    _validate_backup_filename(file.filename or "")
    archive_path = await _save_backup_upload(file, prefix="health")
    try:
        report = await run_in_threadpool(inspect_backup_archive, archive_path)
        return {"message": "备份健康检查通过", **report}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"备份健康检查失败: {exc}")
    finally:
        safe_unlink(archive_path)


@router.post("/api/restore")
async def restore_data(file: UploadFile = File(...)):
    """从备份包恢复数据库与上传文件。"""
    _validate_backup_filename(file.filename or "")
    archive_path = await _save_backup_upload(file, prefix="restore")

    async with DATA_MUTATION_LOCK:
        MAINTENANCE_MODE.set()
        try:
            result = await run_in_threadpool(restore_from_archive, archive_path, _run_init_db_sync)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")
        finally:
            MAINTENANCE_MODE.clear()
            safe_unlink(archive_path)

    return {
        "message": f"恢复完成（已自动通过健康检查），已恢复数据库与 {result['restored_upload_files']} 个上传文件",
        "restored_upload_files": result["restored_upload_files"],
    }


@router.get("/api/webdav/config")
async def get_webdav_config():
    """读取 WebDAV 配置（不返回明文密码）。"""
    return _public_webdav_config(_load_webdav_config())


@router.get("/api/gemini/config")
async def get_gemini_config():
    config = load_gemini_config()
    public = public_gemini_config(config)
    public["model_name"] = _to_public_model_name(public.get("model_name", ""))
    return public


@router.put("/api/gemini/config")
async def set_gemini_config(request: GeminiConfigRequest):
    payload = request.model_dump()
    payload["model_name"] = _normalize_gemini_model_name(payload.get("model_name", ""))
    saved = save_gemini_config(payload)
    reset_gemini_model_cache()
    public = public_gemini_config(saved)
    public["model_name"] = _to_public_model_name(public.get("model_name", ""))
    return {
        "message": "Gemini 配置已保存",
        "config": public,
    }


@router.post("/api/gemini/models")
async def list_gemini_models(request: GeminiModelsRequest):
    payload = request.model_dump()
    api_key, _model_name, _timeout = resolve_gemini_settings(payload.get("api_key", ""))
    items = await run_in_threadpool(_list_gemini_models, api_key)
    return {
        "items": items,
        "message": f"已获取可用模型 {len(items)} 个",
    }


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
    local_archive_path = UPLOAD_DIR / f"webdav_backup_{uuid4().hex}.zip"
    async with DATA_MUTATION_LOCK:
        try:
            await run_in_threadpool(build_backup_archive_file, local_archive_path)
            upload_name = f"office_supplies_backup_{uuid4().hex[:8]}.zip"
            remote_url = await run_in_threadpool(
                upload_file, config, upload_name, local_archive_path
            )
            keep_backups = max(0, int(config.get("keep_backups") or 0))
            retention = await run_in_threadpool(prune_backups, config, keep_backups)
        except Exception as e:
            _handle_webdav_error(e)
        finally:
            safe_unlink(local_archive_path)
    deleted_count = len(retention.get("deleted", []))
    retention_errors = retention.get("errors", [])
    message = f"备份已上传到 WebDAV：{upload_name}"
    if deleted_count:
        message += f"，自动清理旧备份 {deleted_count} 个"
    if retention_errors:
        message += f"（清理失败 {len(retention_errors)} 个）"
    return {
        "message": message,
        "filename": upload_name,
        "remote_url": remote_url,
        "retention": retention,
    }


@router.post("/api/webdav/restore")
async def restore_from_webdav(request: WebDAVRestoreRequest):
    """从 WebDAV 下载指定备份并恢复。"""
    config = _require_webdav_config()
    filename = request.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename 不能为空")

    archive_path = UPLOAD_DIR / f"restore_webdav_{uuid4().hex}.zip"
    async with DATA_MUTATION_LOCK:
        MAINTENANCE_MODE.set()
        try:
            await run_in_threadpool(download_backup_to_file, config, filename, archive_path)
            result = await run_in_threadpool(restore_from_archive, archive_path, _run_init_db_sync)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            _handle_webdav_error(e)
        finally:
            MAINTENANCE_MODE.clear()
            safe_unlink(archive_path)

    return {
        "message": f"已从 WebDAV 恢复：{filename}（已自动通过健康检查），并恢复 {result['restored_upload_files']} 个上传文件",
        "restored_upload_files": result["restored_upload_files"],
        "filename": filename,
    }
