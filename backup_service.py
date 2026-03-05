import os
import shutil
import sqlite3
import stat
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from api_utils import safe_unlink
from app_runtime import APP_STATE_DIR, UPLOAD_DIR
from database import DB_PATH

MAX_BACKUP_ENTRIES = 5000
MAX_BACKUP_TOTAL_SIZE = 1024 * 1024 * 1024  # 1 GB
MAX_BACKUP_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_COMPRESSION_RATIO = 200
SQLITE_INTEGRITY_OK = "ok"

REQUIRED_DB_TABLES = {"items"}
REQUIRED_ITEMS_COLUMNS = {
    "id",
    "serial_number",
    "department",
    "handler",
    "request_date",
    "item_name",
    "quantity",
    "purchase_link",
    "unit_price",
    "status",
    "invoice_issued",
    "payment_status",
    "created_at",
    "updated_at",
}


def resolve_db_path() -> Path:
    """解析数据库路径（兼容相对路径配置）。"""
    db_path = Path(DB_PATH)
    if db_path.is_absolute():
        return db_path
    return APP_STATE_DIR / db_path


def is_safe_zip_entry(name: str) -> bool:
    """校验压缩包内路径，阻止目录穿越。"""
    path = Path(name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def is_safe_zip_member(info: zipfile.ZipInfo) -> bool:
    if not is_safe_zip_entry(info.filename):
        return False
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        return False
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode):
        return False
    return True


def _validate_archive_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = [info for info in archive.infolist() if info.filename and not info.is_dir()]
    if not members:
        raise ValueError("备份包为空")
    if len(members) > MAX_BACKUP_ENTRIES:
        raise ValueError("备份包文件数量过多，疑似异常压缩包")

    total_size = 0
    for info in members:
        if not is_safe_zip_member(info):
            raise ValueError("备份包包含非法文件条目")
        if info.file_size > MAX_BACKUP_FILE_SIZE:
            raise ValueError("备份包存在超大文件，已拒绝恢复")
        total_size += info.file_size
        if total_size > MAX_BACKUP_TOTAL_SIZE:
            raise ValueError("备份包总大小超限，已拒绝恢复")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ValueError("备份包压缩比异常，已拒绝恢复")
    return members


def _validate_sqlite_db_file(db_file: Path) -> dict:
    if not db_file.exists():
        raise ValueError("备份包缺少 office_supplies.db")

    try:
        conn = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ValueError(f"备份数据库无法打开: {exc}") from exc

    try:
        integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0] if integrity_row else "").strip().lower()
        if integrity != SQLITE_INTEGRITY_OK:
            raise ValueError("备份数据库完整性校验失败")

        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = {str(row[0]) for row in table_rows if row and row[0]}
        missing_tables = sorted(REQUIRED_DB_TABLES - tables)
        if missing_tables:
            raise ValueError(f"备份数据库缺少数据表: {', '.join(missing_tables)}")

        column_rows = conn.execute("PRAGMA table_info(items)").fetchall()
        columns = {str(row[1]) for row in column_rows if len(row) > 1}
        missing_columns = sorted(REQUIRED_ITEMS_COLUMNS - columns)
        if missing_columns:
            raise ValueError(f"备份数据库 items 表缺少字段: {', '.join(missing_columns)}")

        row = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        item_count = int(row[0] if row and row[0] is not None else 0)
    finally:
        conn.close()

    return {
        "integrity": SQLITE_INTEGRITY_OK,
        "tables": sorted(tables),
        "item_count": item_count,
    }


def inspect_backup_archive(archive_path: Path) -> dict:
    """备份健康检查：验证 zip 结构与数据库可读性。"""
    extract_dir = APP_STATE_DIR / f".backup_health_{uuid4().hex}"
    try:
        extract_dir.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                _validate_archive_members(archive)
                archive.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError("备份文件不是有效的 zip 压缩包") from exc

        restored_db = extract_dir / "office_supplies.db"
        restored_uploads = extract_dir / "uploads"
        db_report = _validate_sqlite_db_file(restored_db)
        upload_files = 0
        if restored_uploads.exists():
            upload_files = sum(1 for path in restored_uploads.rglob("*") if path.is_file())

        return {
            "ok": True,
            "db": db_report,
            "upload_files": upload_files,
        }
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)


def _build_archive(target: zipfile.ZipFile) -> None:
    db_path = resolve_db_path()
    if db_path.exists():
        target.write(db_path, arcname="office_supplies.db")
    if UPLOAD_DIR.exists():
        for file_path in UPLOAD_DIR.rglob("*"):
            if file_path.is_file():
                arcname = Path("uploads") / file_path.relative_to(UPLOAD_DIR)
                target.write(file_path, arcname=arcname.as_posix())


def build_backup_archive() -> tuple[BytesIO, str]:
    """打包数据库与上传目录为 zip。"""
    buffer = BytesIO()
    filename = f"office_supplies_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _build_archive(archive)
    buffer.seek(0)
    return buffer, filename


def build_backup_archive_file(destination: Path) -> Path:
    """打包为磁盘文件（用于大文件上传场景）。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _build_archive(archive)
    return destination


def restore_from_archive(
    archive_path: Path,
    post_restore_hook: Optional[Callable[[], None]] = None,
) -> dict:
    """从备份 zip 恢复数据库与上传目录。"""
    extract_dir = APP_STATE_DIR / f".restore_tmp_{uuid4().hex}"
    snapshot_db = APP_STATE_DIR / f".restore_db_snapshot_{uuid4().hex}.bak"
    snapshot_uploads = APP_STATE_DIR / f".restore_uploads_snapshot_{uuid4().hex}"
    temp_db_target = APP_STATE_DIR / f".restore_db_target_{uuid4().hex}.tmp"
    db_path = resolve_db_path()

    try:
        extract_dir.mkdir(parents=True, exist_ok=False)

        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                _validate_archive_members(archive)
                archive.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError("备份文件不是有效的 zip 压缩包") from exc

        restored_db = extract_dir / "office_supplies.db"
        restored_uploads = extract_dir / "uploads"
        _validate_sqlite_db_file(restored_db)

        if db_path.exists():
            snapshot_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, snapshot_db)
        if UPLOAD_DIR.exists():
            shutil.copytree(UPLOAD_DIR, snapshot_uploads)

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored_db, temp_db_target)
            os.replace(temp_db_target, db_path)

            shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            restored_upload_files = 0
            if restored_uploads.exists():
                for src_file in restored_uploads.rglob("*"):
                    if not src_file.is_file():
                        continue
                    relative = src_file.relative_to(restored_uploads)
                    dest_file = UPLOAD_DIR / relative
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)
                    restored_upload_files += 1

            if not any(UPLOAD_DIR.iterdir()):
                (UPLOAD_DIR / ".gitkeep").touch(exist_ok=True)

            if post_restore_hook:
                post_restore_hook()

            return {
                "restored_db": True,
                "restored_upload_files": restored_upload_files,
            }
        except Exception:
            safe_unlink(temp_db_target)
            if snapshot_db.exists():
                os.replace(snapshot_db, db_path)
            else:
                safe_unlink(db_path)

            if snapshot_uploads.exists():
                shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
                shutil.copytree(snapshot_uploads, UPLOAD_DIR)
            else:
                shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                (UPLOAD_DIR / ".gitkeep").touch(exist_ok=True)
            raise
    finally:
        safe_unlink(temp_db_target)
        shutil.rmtree(extract_dir, ignore_errors=True)
        safe_unlink(snapshot_db)
        shutil.rmtree(snapshot_uploads, ignore_errors=True)
