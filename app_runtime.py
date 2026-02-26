import sys
from pathlib import Path


def resolve_runtime_dir() -> Path:
    """运行目录（源码模式为项目目录，打包模式为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolve_static_dir() -> Path:
    """静态资源目录（兼容源码与 PyInstaller 打包）。"""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "static")
    candidates.append(Path(__file__).resolve().parent / "static")
    candidates.append(Path.cwd() / "static")

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


RUNTIME_DIR = resolve_runtime_dir()
STATIC_DIR = resolve_static_dir()
UPLOAD_DIR = RUNTIME_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
