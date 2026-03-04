import atexit
import multiprocessing as mp
import os
import signal
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Optional

APP_TITLE = "办公用品采购系统"
HOST = "127.0.0.1"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
STARTUP_TIMEOUT_SECONDS = 45
BACKEND_CRASH_LOG_FILENAME = "backend_crash.log"
_FALLBACK_STREAM = None


def _ensure_standard_streams(
    *,
    fallback_log_path: Optional[Path] = None,
    force_redirect: bool = False,
) -> None:
    """在 --windowed 场景补齐 stdout/stderr，避免第三方库写日志时报错。"""
    global _FALLBACK_STREAM
    has_streams = sys.stdout is not None and sys.stderr is not None
    if has_streams and not force_redirect:
        return

    need_log_stream = fallback_log_path is not None
    current_stream_path = None
    if _FALLBACK_STREAM is not None:
        current_stream_path = getattr(_FALLBACK_STREAM, "name", None)

    if need_log_stream:
        target_path = str(fallback_log_path)
        if (
            _FALLBACK_STREAM is None
            or _FALLBACK_STREAM.closed
            or current_stream_path != target_path
        ):
            try:
                fallback_log_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            _FALLBACK_STREAM = open(fallback_log_path, "a", encoding="utf-8", buffering=1)
    elif _FALLBACK_STREAM is None or _FALLBACK_STREAM.closed:
        _FALLBACK_STREAM = open(os.devnull, "w", encoding="utf-8", buffering=1)

    if force_redirect or sys.stdout is None:
        sys.stdout = _FALLBACK_STREAM
    if force_redirect or sys.stderr is None:
        sys.stderr = _FALLBACK_STREAM


def _runtime_dir() -> Path:
    """获取运行目录（源码模式为项目目录，打包模式为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _find_free_port(host: str) -> int:
    """分配可用本地端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _read_text_tail(path: Path, max_chars: int = 1600) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _run_fastapi_server(host: str, port: int, runtime_dir: str) -> None:
    """子进程入口：启动 FastAPI 服务。"""
    runtime_path = Path(runtime_dir)
    crash_log_path = runtime_path / BACKEND_CRASH_LOG_FILENAME
    try:
        crash_log_path.unlink(missing_ok=True)
    except OSError:
        pass
    _ensure_standard_streams(fallback_log_path=crash_log_path, force_redirect=True)

    os.chdir(runtime_dir)
    Path("uploads").mkdir(exist_ok=True)

    try:
        import uvicorn
        from main import app

        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,
            workers=1,
            log_level="warning",
            access_log=False,
        )
    except BaseException:
        try:
            with crash_log_path.open("a", encoding="utf-8") as f:
                f.write("\n\n=== Python Traceback ===\n")
                f.write(traceback.format_exc())
        except OSError:
            pass
        raise


class DesktopApp:
    def __init__(self) -> None:
        self.host = HOST
        self.port = _find_free_port(self.host)
        self.runtime_dir = _runtime_dir()

        self.server_process: Optional[mp.Process] = None
        self.window = None

        self._shutdown_lock = threading.Lock()
        self._is_shutting_down = False

    def _wait_server_ready(self, timeout: int = STARTUP_TIMEOUT_SECONDS) -> None:
        """等待后端可访问。"""
        url = f"http://{self.host}:{self.port}/"
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self.server_process and not self.server_process.is_alive():
                exitcode = self.server_process.exitcode
                crash_log = self.runtime_dir / BACKEND_CRASH_LOG_FILENAME
                if crash_log.exists():
                    log_tail = _read_text_tail(crash_log)
                    tail_hint = f"\n--- 日志尾部 ---\n{log_tail}" if log_tail else ""
                    raise RuntimeError(
                        f"FastAPI 后台进程已提前退出（exitcode={exitcode}），请查看日志：{crash_log}{tail_hint}"
                    )
                raise RuntimeError(f"FastAPI 后台进程已提前退出（exitcode={exitcode}）")
            try:
                with urllib.request.urlopen(url, timeout=1):
                    return
            except Exception:
                time.sleep(0.25)

        raise TimeoutError(f"FastAPI 启动超时（>{timeout}s）：{url}")

    def start_backend(self) -> None:
        """启动后台 FastAPI 子进程。"""
        crash_log = self.runtime_dir / BACKEND_CRASH_LOG_FILENAME
        try:
            crash_log.unlink(missing_ok=True)
        except OSError:
            pass

        process = mp.Process(
            target=_run_fastapi_server,
            args=(self.host, self.port, str(self.runtime_dir)),
            name="fastapi-backend",
        )
        process.start()
        self.server_process = process
        self._wait_server_ready()

    def shutdown_backend(self, *_args) -> None:
        """幂等关闭后台进程，避免遗留幽灵进程。"""
        with self._shutdown_lock:
            if self._is_shutting_down:
                return
            self._is_shutting_down = True

        process = self.server_process
        if not process:
            return

        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

        if process.is_alive():
            process.kill()
            process.join(timeout=2)

        self.server_process = None

    def _on_window_closing(self, *_args) -> None:
        self.shutdown_backend()

    def _on_window_closed(self, *_args) -> None:
        self.shutdown_backend()

    def _install_signal_handlers(self) -> None:
        def _handler(signum, _frame) -> None:
            self.shutdown_backend()
            raise SystemExit(0)

        for sig_name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, sig_name, None)
            if sig is not None:
                signal.signal(sig, _handler)

    def run(self) -> None:
        atexit.register(self.shutdown_backend)
        self._install_signal_handlers()

        self.start_backend()

        import webview

        url = f"http://{self.host}:{self.port}/"
        self.window = webview.create_window(
            APP_TITLE,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
        )

        self.window.events.closing += self._on_window_closing
        self.window.events.closed += self._on_window_closed

        try:
            webview.start(debug=False)
        finally:
            self.shutdown_backend()


def main() -> None:
    _ensure_standard_streams()
    mp.freeze_support()
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()
