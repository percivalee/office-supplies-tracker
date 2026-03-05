import os
import sys
from pathlib import Path


def resolve_runtime_dir() -> Path:
    """运行目录（源码模式为项目目录，打包模式为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_pyinstaller_internal_dir() -> Path | None:
    """PyInstaller one-dir 默认内容目录（通常为 _internal）。"""
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).resolve().parent / "_internal"
    if candidate.exists():
        return candidate
    return None


def resolve_static_dir() -> Path:
    """静态资源目录（兼容源码与 PyInstaller 打包）。"""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "static")
    internal_dir = resolve_pyinstaller_internal_dir()
    if internal_dir is not None:
        candidates.append(internal_dir / "static")
    candidates.append(Path(__file__).resolve().parent / "static")
    candidates.append(Path.cwd() / "static")

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _ensure_writable_dir(path: Path) -> None:
    """创建目录并通过临时文件验证可写权限。"""
    path.mkdir(parents=True, exist_ok=True)
    probe_file = path / ".test_write"
    try:
        probe_file.write_text("ok", encoding="utf-8")
    finally:
        try:
            probe_file.unlink()
        except OSError:
            pass


def resolve_data_dir() -> Path:
    """优先使用程序目录下 data/，不可写时回退到 APPDATA。"""
    runtime_data_dir = resolve_runtime_dir() / "data"
    try:
        _ensure_writable_dir(runtime_data_dir)
        return runtime_data_dir
    except (PermissionError, OSError):
        fallback_data_dir = (
            Path(os.environ.get("APPDATA", "~")).expanduser()
            / "OfficeSuppliesTracker"
            / "data"
        )
        _ensure_writable_dir(fallback_data_dir)
        return fallback_data_dir


RUNTIME_DIR = resolve_runtime_dir()
PYINSTALLER_INTERNAL_DIR = resolve_pyinstaller_internal_dir()
STATIC_DIR = resolve_static_dir()
DATA_DIR = resolve_data_dir()
APP_STATE_DIR = DATA_DIR.parent
LOG_DIR = APP_STATE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = APP_STATE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
