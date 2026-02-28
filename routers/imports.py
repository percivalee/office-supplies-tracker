from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from api_utils import (
    MAX_DOCUMENT_UPLOAD_BYTES,
    build_upload_path,
    safe_unlink,
    save_upload_file_with_limit,
)
from import_flow import build_preview_data, confirm_import_payload, normalize_import_payload
from parser import parse_document
from schemas import DuplicateHandleRequest, ImportConfirmRequest

router = APIRouter(prefix="/api")


@router.post("/upload")
async def upload_and_parse(file: UploadFile = File(...)):
    """上传文件并解析。"""
    file_path = build_upload_path(file.filename or "")

    try:
        save_upload_file_with_limit(
            file,
            file_path,
            max_bytes=MAX_DOCUMENT_UPLOAD_BYTES,
            file_label="上传文件",
        )
        result = await run_in_threadpool(parse_document, str(file_path))
        normalized_payload = normalize_import_payload({
            "serial_number": result.get("serial_number", ""),
            "department": result.get("department", ""),
            "handler": result.get("handler", ""),
            "request_date": result.get("request_date", ""),
            "items": result.get("items", []),
        })
        preview_data = build_preview_data(normalized_payload, normalized_payload["items"])

        return {
            "message": f"解析完成，共 {len(preview_data['items'])} 条，请确认后导入",
            "parsed_data": preview_data,
            "has_duplicates": False,
            "requires_confirmation": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
    finally:
        await file.close()
        safe_unlink(file_path)


@router.post("/import/confirm")
async def confirm_import(request: ImportConfirmRequest):
    """确认导入（支持人工校正后提交）。"""
    payload = request.model_dump()
    duplicate_action = payload.pop("duplicate_action", None)
    normalized_payload = normalize_import_payload(payload)
    return await confirm_import_payload(normalized_payload, duplicate_action)


@router.post("/upload/handle-duplicates")
async def handle_duplicates(request: DuplicateHandleRequest):
    """兼容旧前端：处理重复物品。"""
    try:
        first = request.items_data[0] if request.items_data else {}
        normalized_payload = normalize_import_payload({
            "serial_number": first.get("serial_number", ""),
            "department": first.get("department", ""),
            "handler": first.get("handler", ""),
            "request_date": first.get("request_date", ""),
            "items": request.items_data,
        })
        return await confirm_import_payload(normalized_payload, request.action)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
