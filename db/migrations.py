import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from app_runtime import PYINSTALLER_INTERNAL_DIR, RUNTIME_DIR
from db.constants import DB_PATH


def _resolve_existing_path(candidates: list[Path], what: str) -> Path:
    for path in candidates:
        if path.exists():
            return path
    joined = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Cannot find {what}. Tried: {joined}")


def _resolve_alembic_ini() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [Path(RUNTIME_DIR) / "alembic.ini", Path(__file__).resolve().parents[1] / "alembic.ini"]
    if meipass:
        candidates.insert(0, Path(meipass) / "alembic.ini")
    if PYINSTALLER_INTERNAL_DIR is not None:
        candidates.insert(0, Path(PYINSTALLER_INTERNAL_DIR) / "alembic.ini")
    return _resolve_existing_path(candidates, "alembic.ini")


def _resolve_script_location() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = [Path(RUNTIME_DIR) / "alembic", Path(__file__).resolve().parents[1] / "alembic"]
    if meipass:
        candidates.insert(0, Path(meipass) / "alembic")
    if PYINSTALLER_INTERNAL_DIR is not None:
        candidates.insert(0, Path(PYINSTALLER_INTERNAL_DIR) / "alembic")
    return _resolve_existing_path(candidates, "alembic script directory")


def upgrade_database_to_head() -> None:
    config_path = _resolve_alembic_ini()
    alembic_cfg = Config(str(config_path))
    alembic_cfg.set_main_option("script_location", str(_resolve_script_location()))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{Path(DB_PATH).resolve().as_posix()}")
    command.upgrade(alembic_cfg, "head")
