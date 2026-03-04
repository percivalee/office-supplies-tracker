import aiosqlite
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pathlib import Path
from threading import Lock
from uuid import uuid4

from api_utils import (
    MAX_DOCUMENT_UPLOAD_BYTES,
    build_upload_path,
    safe_unlink,
    save_upload_file_with_limit,
)
from app_locks import DATA_MUTATION_LOCK
from gemini_ocr import GeminiParseError, parse_document_with_gemini
from import_flow import build_preview_data, confirm_import_payload, normalize_import_payload
from parser import parse_document
from schemas import DuplicateHandleRequest, ImportConfirmRequest

router = APIRouter(prefix="/api")
tasks: dict[str, dict] = {}
_tasks_lock = Lock()
_TERMINAL_TASK_STATUSES = {"completed", "failed"}
_MAX_TRACKED_TASKS = 200
_DEFAULT_UPLOAD_ENGINE = "local"
_DEFAULT_LLM_PROTOCOL = "openai"


def _friendly_task_error_detail(error: Exception) -> str:
    """统一任务失败文案，避免把底层异常原样暴露给前端。"""
    if isinstance(error, TimeoutError):
        return "解析超时，请稍后重试，或切换为手动录入。"
    raw = str(error or "").strip()
    if not raw:
        return "解析失败，请稍后重试，或切换为手动录入。"
    return raw[:300]


def _normalize_payload_from_fields(
    *,
    serial_number,
    department,
    handler,
    request_date,
    items,
) -> dict:
    return normalize_import_payload(
        {
            "serial_number": serial_number or "",
            "department": department or "",
            "handler": handler or "",
            "request_date": request_date or "",
            "items": items or [],
        }
    )


def _normalize_payload_from_parse_result(result: dict) -> dict:
    return _normalize_payload_from_fields(
        serial_number=result.get("serial_number", ""),
        department=result.get("department", ""),
        handler=result.get("handler", ""),
        request_date=result.get("request_date", ""),
        items=result.get("items", []),
    )


def _normalize_payload_from_items_data(items_data: list[dict]) -> dict:
    first = items_data[0] if items_data else {}
    return _normalize_payload_from_fields(
        serial_number=first.get("serial_number", ""),
        department=first.get("department", ""),
        handler=first.get("handler", ""),
        request_date=first.get("request_date", ""),
        items=items_data,
    )


async def _confirm_import_with_lock(
    normalized_payload: dict,
    duplicate_action: str | None,
    *,
    failure_prefix: str,
) -> dict:
    try:
        async with DATA_MUTATION_LOCK:
            return await confirm_import_payload(normalized_payload, duplicate_action)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except aiosqlite.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="导入触发唯一约束冲突（流水号+物品名称+经办人）")
        raise HTTPException(status_code=400, detail="导入失败：字段值不合法")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{failure_prefix}: {str(e)}")


def _set_task(task_id: str, *, status: str | None = None, result=None) -> None:
    with _tasks_lock:
        task = tasks.get(task_id)
        if task is None:
            return
        if status is not None:
            task["status"] = status
        task["result"] = result


def _prune_tasks() -> None:
    with _tasks_lock:
        if len(tasks) <= _MAX_TRACKED_TASKS:
            return
        for key in list(tasks.keys()):
            if len(tasks) <= _MAX_TRACKED_TASKS:
                break
            status = str(tasks.get(key, {}).get("status", ""))
            if status in _TERMINAL_TASK_STATUSES:
                tasks.pop(key, None)


def _normalize_engine(raw_engine: str | None) -> str:
    engine = str(raw_engine or "").strip().lower()
    if engine in {"local", "cloud"}:
        return engine
    if engine == "gemini":
        return "cloud"
    return _DEFAULT_UPLOAD_ENGINE


def _normalize_protocol(raw_protocol: str | None) -> str:
    protocol = str(raw_protocol or "").strip().lower()
    if protocol in {"google", "openai", "anthropic"}:
        return protocol
    return _DEFAULT_LLM_PROTOCOL


def _parse_by_engine(
    file_path: Path,
    *,
    engine: str,
    protocol: str,
    api_key: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
) -> dict:
    # 双引擎路由：local 走本地 OCR/规则解析，cloud 走多协议大模型解析。
    normalized_engine = _normalize_engine(engine)
    if normalized_engine == "cloud":
        return parse_document_with_gemini(
            file_path,
            protocol=_normalize_protocol(protocol),
            api_key_override=api_key,
            model_name_override=model_name,
            base_url_override=base_url,
        )
    return parse_document(str(file_path))


def _run_parse_task(
    task_id: str,
    file_path: Path,
    engine: str,
    protocol: str,
    api_key: str,
    model_name: str,
    base_url: str,
) -> None:
    _set_task(task_id, status="processing", result=None)
    try:
        parsed = _parse_by_engine(
            file_path,
            engine=engine,
            protocol=protocol,
            api_key=api_key,
            model_name=model_name,
            base_url=base_url,
        )
        normalized_payload = _normalize_payload_from_parse_result(parsed)
        preview_data = build_preview_data(normalized_payload, normalized_payload["items"])
        _set_task(
            task_id,
            status="completed",
            result={
                "message": f"解析完成，共 {len(preview_data['items'])} 条，请确认后导入",
                "parsed_data": preview_data,
                "has_duplicates": False,
                "requires_confirmation": True,
            },
        )
    except GeminiParseError as e:
        _set_task(
            task_id,
            status="failed",
            result={"detail": str(e)},
        )
    except Exception as e:
        _set_task(
            task_id,
            status="failed",
            result={"detail": _friendly_task_error_detail(e)},
        )
    finally:
        safe_unlink(file_path)


@router.post("/upload", status_code=202)
@router.post("/upload-ocr", status_code=202)
async def upload_and_parse(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    engine: str = Form(default=_DEFAULT_UPLOAD_ENGINE),
    protocol: str = Form(default=_DEFAULT_LLM_PROTOCOL),
    api_key: str = Form(default=""),
    model_name: str = Form(default=""),
    base_url: str = Form(default=""),
):
    """上传文件并创建异步解析任务。"""
    file_path = build_upload_path(file.filename or "")
    normalized_engine = _normalize_engine(engine)
    normalized_protocol = _normalize_protocol(protocol)
    normalized_api_key = str(api_key or "").strip()
    normalized_model_name = str(model_name or "").strip()
    normalized_base_url = str(base_url or "").strip()

    try:
        save_upload_file_with_limit(
            file,
            file_path,
            max_bytes=MAX_DOCUMENT_UPLOAD_BYTES,
            file_label="上传文件",
        )
        task_id = uuid4().hex
        with _tasks_lock:
            tasks[task_id] = {"status": "pending", "result": None}
        _prune_tasks()
        background_tasks.add_task(
            _run_parse_task,
            task_id,
            file_path,
            normalized_engine,
            normalized_protocol,
            normalized_api_key,
            normalized_model_name,
            normalized_base_url,
        )
        return {"task_id": task_id}

    except HTTPException:
        safe_unlink(file_path)
        raise
    except Exception as e:
        safe_unlink(file_path)
        raise HTTPException(
            status_code=500,
            detail=f"解析任务创建失败，请稍后重试。{_friendly_task_error_detail(e)}",
        )
    finally:
        await file.close()


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    with _tasks_lock:
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return {
            "task_id": task_id,
            "status": task.get("status", "failed"),
            "result": task.get("result"),
        }


@router.post("/import/confirm")
async def confirm_import(request: ImportConfirmRequest):
    """确认导入（支持人工校正后提交）。"""
    payload = request.model_dump()
    duplicate_action = payload.pop("duplicate_action", None)
    normalized_payload = normalize_import_payload(payload)
    return await _confirm_import_with_lock(
        normalized_payload,
        duplicate_action,
        failure_prefix="导入失败",
    )


@router.post("/upload/handle-duplicates")
async def handle_duplicates(request: DuplicateHandleRequest):
    """兼容旧前端：处理重复物品。"""
    normalized_payload = _normalize_payload_from_items_data(request.items_data)
    return await _confirm_import_with_lock(
        normalized_payload,
        request.action,
        failure_prefix="处理失败",
    )
