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


RUNTIME_DIR = resolve_runtime_dir()
PYINSTALLER_INTERNAL_DIR = resolve_pyinstaller_internal_dir()
STATIC_DIR = resolve_static_dir()
UPLOAD_DIR = RUNTIME_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
