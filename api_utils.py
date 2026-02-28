import re
from pathlib import Path
from typing import Optional
from uuid import uuid4
from datetime import datetime

from fastapi import HTTPException

from app_runtime import UPLOAD_DIR

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".jfif"}
MAX_DOCUMENT_UPLOAD_BYTES = 30 * 1024 * 1024  # 30MB
STREAM_CHUNK_SIZE = 1024 * 1024


def normalize_month(month: Optional[str]) -> Optional[str]:
    """校验月份参数，格式为 YYYY-MM。"""
    if month is None:
        return None
    month = month.strip()
    if not month:
        return None
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=400, detail="month 参数格式应为 YYYY-MM")
    return month


def normalize_text_filter(value: Optional[str]) -> Optional[str]:
    """将空白筛选值归一化为 None。"""
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_history_action(value: Optional[str]) -> Optional[str]:
    """校验历史操作类型。"""
    value = normalize_text_filter(value)
    if value is None:
        return None
    if value not in {"create", "update", "delete"}:
        raise HTTPException(status_code=400, detail="action 仅支持 create / update / delete")
    return value


def safe_unlink(path: Path) -> None:
    """安全删除临时文件。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def build_upload_path(filename: str) -> Path:
    """构造唯一上传路径，并校验扩展名。"""
    safe_filename = Path(filename).name if filename else ""
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    extension = Path(safe_filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持 PDF / PNG / JPG / JPEG / JFIF 文件")

    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex}{extension}"
    return UPLOAD_DIR / unique_name


def save_upload_file_with_limit(
    upload_file,
    destination: Path,
    max_bytes: int,
    file_label: str = "文件",
) -> int:
    """流式写入上传文件并限制大小，超限直接中断。"""
    written = 0
    limit_mb = max(1, max_bytes // (1024 * 1024))
    with open(destination, "wb") as buffer:
        while True:
            chunk = upload_file.file.read(STREAM_CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(status_code=413, detail=f"{file_label}过大，最大支持 {limit_mb}MB")
            buffer.write(chunk)
    return written
