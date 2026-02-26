import base64
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


DEFAULT_TIMEOUT_SECONDS = 20
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024  # 1 GB


class WebDAVError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip()
    if not value:
        raise WebDAVError("WebDAV 地址不能为空")
    if not value.startswith(("http://", "https://")):
        raise WebDAVError("WebDAV 地址必须以 http:// 或 https:// 开头")
    parsed = urlparse(value)
    if not parsed.netloc:
        raise WebDAVError("WebDAV 地址无效")
    return value.rstrip("/")


def _normalize_remote_dir(remote_dir: Optional[str]) -> str:
    if remote_dir is None:
        return ""
    raw = remote_dir.replace("\\", "/").strip().strip("/")
    if not raw:
        return ""
    parts = [part for part in raw.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise WebDAVError("remote_dir 不能包含 '..'")
    return "/".join(parts)


def normalize_webdav_config(payload: dict) -> dict:
    base_url = _normalize_base_url(str(payload.get("base_url") or ""))
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    remote_dir = _normalize_remote_dir(payload.get("remote_dir"))
    if len(username) > 200:
        raise WebDAVError("username 长度不能超过 200")
    if len(password) > 200:
        raise WebDAVError("password 长度不能超过 200")
    return {
        "base_url": base_url,
        "username": username,
        "password": password,
        "remote_dir": remote_dir,
    }


def _build_auth_header(username: str, password: str) -> dict[str, str]:
    if not username and not password:
        return {}
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _compose_url(base_url: str, path: str = "") -> str:
    if not path:
        return base_url
    safe_path = "/".join(quote(part, safe="") for part in path.split("/") if part)
    return f"{base_url}/{safe_path}" if safe_path else base_url


def _request(
    method: str,
    url: str,
    headers: Optional[dict[str, str]] = None,
    data: Optional[bytes] = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, str], bytes]:
    req = Request(url=url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            return int(response.status), dict(response.headers.items()), body
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore").strip()
        message = f"WebDAV 请求失败: HTTP {e.code}"
        if detail:
            message = f"{message} - {detail[:200]}"
        raise WebDAVError(message, status_code=e.code)
    except URLError as e:
        raise WebDAVError(f"WebDAV 连接失败: {e.reason}")


def ensure_remote_dir(base_url: str, remote_dir: str, auth_headers: dict[str, str]) -> None:
    if not remote_dir:
        return
    current = ""
    for part in remote_dir.split("/"):
        current = f"{current}/{part}" if current else part
        url = _compose_url(base_url, current)
        try:
            status, _, _ = _request("MKCOL", url, headers=auth_headers)
            if status not in (201, 204, 301, 302, 405):
                raise WebDAVError(f"创建目录失败: {current} (HTTP {status})")
        except WebDAVError as e:
            if e.status_code in (301, 302, 405, 409):
                # 301/302: 已存在或被代理重定向; 405: 已存在; 409: 父目录创建刚完成后重试可忽略
                continue
            raise


def test_connection(config: dict) -> None:
    auth_headers = _build_auth_header(config.get("username", ""), config.get("password", ""))
    base_url = _normalize_base_url(config.get("base_url", ""))
    remote_dir = _normalize_remote_dir(config.get("remote_dir"))
    ensure_remote_dir(base_url, remote_dir, auth_headers)
    target = _compose_url(base_url, remote_dir)
    headers = {
        **auth_headers,
        "Depth": "0",
        "Content-Type": "application/xml; charset=utf-8",
    }
    body = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b"<propfind xmlns='DAV:'><prop><resourcetype/></prop></propfind>"
    )
    status, _, _ = _request("PROPFIND", target, headers=headers, data=body)
    if status not in (200, 207):
        raise WebDAVError(f"WebDAV 连接测试失败: HTTP {status}")


def upload_bytes(config: dict, filename: str, content: bytes) -> str:
    if not filename or "/" in filename or "\\" in filename:
        raise WebDAVError("文件名不合法")
    base_url = _normalize_base_url(config.get("base_url", ""))
    remote_dir = _normalize_remote_dir(config.get("remote_dir"))
    auth_headers = _build_auth_header(config.get("username", ""), config.get("password", ""))
    ensure_remote_dir(base_url, remote_dir, auth_headers)
    remote_path = str(PurePosixPath(remote_dir) / filename) if remote_dir else filename
    target = _compose_url(base_url, remote_path)
    headers = {
        **auth_headers,
        "Content-Type": "application/zip",
        "Content-Length": str(len(content)),
    }
    status, _, _ = _request("PUT", target, headers=headers, data=content, timeout=60)
    if status not in (200, 201, 204):
        raise WebDAVError(f"上传备份失败: HTTP {status}")
    return target


def _parse_http_datetime(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw


def list_backups(config: dict) -> list[dict]:
    base_url = _normalize_base_url(config.get("base_url", ""))
    remote_dir = _normalize_remote_dir(config.get("remote_dir"))
    auth_headers = _build_auth_header(config.get("username", ""), config.get("password", ""))
    ensure_remote_dir(base_url, remote_dir, auth_headers)
    target = _compose_url(base_url, remote_dir)
    headers = {
        **auth_headers,
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }
    body = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b"<propfind xmlns='DAV:'><prop><getcontentlength/><getlastmodified/><resourcetype/></prop></propfind>"
    )
    status, _, response_body = _request("PROPFIND", target, headers=headers, data=body)
    if status not in (200, 207):
        raise WebDAVError(f"获取 WebDAV 文件列表失败: HTTP {status}")

    try:
        root = ET.fromstring(response_body)
    except ET.ParseError:
        raise WebDAVError("WebDAV 返回数据格式异常")

    files: list[dict] = []
    for response in root.findall(".//{*}response"):
        href_text = (response.findtext("{*}href") or "").strip()
        if not href_text:
            continue
        prop = response.find(".//{*}prop")
        if prop is None:
            continue
        resourcetype = prop.find("{*}resourcetype")
        is_collection = (
            resourcetype is not None and resourcetype.find("{*}collection") is not None
        )
        if is_collection:
            continue

        path = urlparse(href_text).path
        name = unquote(path.rstrip("/").split("/")[-1])
        if not name.lower().endswith(".zip"):
            continue

        size_text = (prop.findtext("{*}getcontentlength") or "0").strip()
        try:
            size = int(size_text)
        except ValueError:
            size = 0
        modified_raw = prop.findtext("{*}getlastmodified") or ""
        files.append({
            "name": name,
            "size": size,
            "modified": _parse_http_datetime(modified_raw),
            "modified_raw": modified_raw,
        })

    files.sort(
        key=lambda item: (item.get("modified_raw", ""), item.get("name", "")),
        reverse=True,
    )
    return files


def download_backup(config: dict, filename: str) -> bytes:
    if not filename or "/" in filename or "\\" in filename:
        raise WebDAVError("文件名不合法")
    base_url = _normalize_base_url(config.get("base_url", ""))
    remote_dir = _normalize_remote_dir(config.get("remote_dir"))
    auth_headers = _build_auth_header(config.get("username", ""), config.get("password", ""))
    remote_path = str(PurePosixPath(remote_dir) / filename) if remote_dir else filename
    target = _compose_url(base_url, remote_path)
    req = Request(url=target, method="GET")
    for key, value in auth_headers.items():
        req.add_header(key, value)
    try:
        with urlopen(req, timeout=60) as response:
            length_header = response.headers.get("Content-Length") or "0"
            try:
                length = int(length_header)
            except ValueError:
                length = 0
            if length > MAX_DOWNLOAD_BYTES:
                raise WebDAVError("远端备份文件过大，已拒绝下载")
            content = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(content) > MAX_DOWNLOAD_BYTES:
                raise WebDAVError("远端备份文件过大，已拒绝下载")
            return content
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore").strip()
        message = f"下载 WebDAV 备份失败: HTTP {e.code}"
        if detail:
            message = f"{message} - {detail[:200]}"
        raise WebDAVError(message, status_code=e.code)
    except URLError as e:
        raise WebDAVError(f"下载 WebDAV 备份失败: {e.reason}")
