import shutil
import zipfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app_runtime import RUNTIME_DIR, UPLOAD_DIR
from api_utils import safe_unlink
from database import DB_PATH

MAX_BACKUP_ENTRIES = 5000
MAX_BACKUP_TOTAL_SIZE = 1024 * 1024 * 1024  # 1 GB
MAX_BACKUP_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_COMPRESSION_RATIO = 200


def resolve_db_path() -> Path:
    """解析数据库路径（兼容相对路径配置）。"""
    db_path = Path(DB_PATH)
    if db_path.is_absolute():
        return db_path
    return RUNTIME_DIR / db_path


def is_safe_zip_entry(name: str) -> bool:
    """校验压缩包内路径，阻止目录穿越。"""
    path = Path(name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def build_backup_archive() -> tuple[BytesIO, str]:
    """打包数据库与上传目录为 zip。"""
    buffer = BytesIO()
    filename = f"office_supplies_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    db_path = resolve_db_path()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if db_path.exists():
            archive.write(db_path, arcname="office_supplies.db")
        if UPLOAD_DIR.exists():
            for file_path in UPLOAD_DIR.rglob("*"):
                if file_path.is_file():
                    arcname = Path("uploads") / file_path.relative_to(UPLOAD_DIR)
                    archive.write(file_path, arcname=arcname.as_posix())

    buffer.seek(0)
    return buffer, filename


def restore_from_archive(archive_path: Path) -> dict:
    """从备份 zip 恢复数据库与上传目录。"""
    extract_dir = RUNTIME_DIR / f".restore_tmp_{uuid4().hex}"
    snapshot_db = RUNTIME_DIR / f".restore_db_snapshot_{uuid4().hex}.bak"
    snapshot_uploads = RUNTIME_DIR / f".restore_uploads_snapshot_{uuid4().hex}"
    db_path = resolve_db_path()

    try:
        extract_dir.mkdir(parents=True, exist_ok=False)

        with zipfile.ZipFile(archive_path, "r") as archive:
            members = [info for info in archive.infolist() if info.filename and not info.is_dir()]
            if not members:
                raise ValueError("备份包为空")
            if len(members) > MAX_BACKUP_ENTRIES:
                raise ValueError("备份包文件数量过多，疑似异常压缩包")

            total_size = 0
            for info in members:
                if not is_safe_zip_entry(info.filename):
                    raise ValueError("备份包包含非法路径")
                if info.file_size > MAX_BACKUP_FILE_SIZE:
                    raise ValueError("备份包存在超大文件，已拒绝恢复")
                total_size += info.file_size
                if total_size > MAX_BACKUP_TOTAL_SIZE:
                    raise ValueError("备份包总大小超限，已拒绝恢复")
                if info.compress_size > 0 and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise ValueError("备份包压缩比异常，已拒绝恢复")
            archive.extractall(extract_dir)

        restored_db = extract_dir / "office_supplies.db"
        restored_uploads = extract_dir / "uploads"
        if not restored_db.exists():
            raise ValueError("备份包缺少 office_supplies.db")

        if db_path.exists():
            snapshot_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, snapshot_db)
        if UPLOAD_DIR.exists():
            shutil.copytree(UPLOAD_DIR, snapshot_uploads)

        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored_db, db_path)

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

            return {
                "restored_db": True,
                "restored_upload_files": restored_upload_files,
            }
        except Exception:
            if snapshot_db.exists():
                shutil.copy2(snapshot_db, db_path)
            if snapshot_uploads.exists():
                shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
                shutil.copytree(snapshot_uploads, UPLOAD_DIR)
            raise
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        safe_unlink(snapshot_db)
        shutil.rmtree(snapshot_uploads, ignore_errors=True)
