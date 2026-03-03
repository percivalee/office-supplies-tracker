import base64
import ast
import io
import json
import mimetypes
import re
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from PIL import Image

from gemini_config import (
    DEFAULT_GEMINI_MODEL_NAME,
    DEFAULT_GEMINI_TIMEOUT_SECONDS,
    resolve_gemini_settings,
)


_GOOGLE_MODEL_LOCK = Lock()
_GOOGLE_MODEL = None
_GOOGLE_MODEL_SIGNATURE: tuple[str, str, str] | None = None

_REQUEST_DATE_PATTERN = re.compile(r"^(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_SUPPORTED_PROTOCOLS = {"google", "openai", "anthropic"}
_PAYLOAD_KEY_HINTS = {
    "流水号",
    "物品明细",
    "供应商名称",
    "日期",
    "serial_number",
    "items",
    "department",
    "request_date",
}
_DEFAULT_OPENAI_MODEL = "gpt-4o"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"

_SYSTEM_PROMPT = """
你是一个专业的企业内控与财务审计视觉助手。请精确分析这张采购单据/发票图片（或 PDF 单据）。
请严格按照以下 JSON 格式返回，不得输出任何 Markdown 标记或额外说明：
{
  "流水号": "单据编号，无则为空",
  "物品明细": [
    {"名称": "示例", "数量": 1, "单价": 0.0}
  ],
  "供应商名称": "示例供应商",
  "日期": "YYYY-MM-DD"
}
规则：
1) 所有字段都必须存在；缺失时用 null 或默认值。
2) 只返回 JSON 对象本体。
3) "物品明细" 必须是数组，未识别时返回空数组。
""".strip()


class GeminiParseError(RuntimeError):
    """多模态解析失败。"""


def _normalize_protocol(value: str | None) -> str:
    protocol = str(value or "").strip().lower()
    if protocol in _SUPPORTED_PROTOCOLS:
        return protocol
    return "openai"


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    matched = _REQUEST_DATE_PATTERN.search(text)
    if not matched:
        return ""
    year, month, day = matched.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _normalize_quantity(value: Any) -> float:
    if isinstance(value, (int, float)):
        quantity = float(value)
        return quantity if quantity > 0 else 1.0
    text = str(value or "").strip()
    if not text:
        return 1.0
    matched = re.search(r"(\d+(?:\.\d+)?)", text)
    if not matched:
        return 1.0
    try:
        quantity = float(matched.group(1))
        return quantity if quantity > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _normalize_unit_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        return price if price >= 0 else None
    text = str(value or "").strip().replace("￥", "").replace("¥", "")
    if not text:
        return None
    matched = re.search(r"(\d+(?:\.\d+)?)", text)
    if not matched:
        return None
    try:
        price = float(matched.group(1))
        return price if price >= 0 else None
    except (TypeError, ValueError):
        return None


def _safe_json_loads(value: str) -> dict:
    raw = _strip_markdown_wrappers(str(value or "").strip())
    candidates = _build_json_candidates(raw)

    for candidate in candidates:
        parsed = _try_parse_json(candidate)
        if parsed is not None:
            payload = _unwrap_payload_dict(parsed)
            if payload is not None:
                return payload

        repaired = _sanitize_json_like(candidate)
        parsed = _try_parse_json(repaired)
        if parsed is not None:
            payload = _unwrap_payload_dict(parsed)
            if payload is not None:
                return payload

        parsed = _try_parse_literal(repaired)
        if parsed is not None:
            payload = _unwrap_payload_dict(parsed)
            if payload is not None:
                return payload

    raise GeminiParseError("模型返回内容不是有效 JSON，请重试或手动录入。")


def _strip_markdown_wrappers(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|JSON)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def _build_json_candidates(raw: str) -> list[str]:
    text = raw.strip()
    candidates: list[str] = []
    if text:
        candidates.append(text)

    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        candidates.append(obj_match.group(0).strip())

    arr_match = re.search(r"\[[\s\S]*\]", text)
    if arr_match:
        candidates.append(arr_match.group(0).strip())

    # 去重并保持顺序
    uniq: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item and item not in seen:
            uniq.append(item)
            seen.add(item)
    return uniq


def _sanitize_json_like(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    text = text.replace("\ufeff", "")
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace("：", ":").replace("，", ",")
    text = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text.strip()


def _try_parse_json(value: str) -> Any | None:
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _try_parse_literal(value: str) -> Any | None:
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None


def _unwrap_payload_dict(parsed: Any) -> dict | None:
    if isinstance(parsed, dict):
        if _PAYLOAD_KEY_HINTS.intersection(parsed.keys()):
            return parsed
        for key in ("data", "result", "output", "json", "content"):
            nested = parsed.get(key)
            if isinstance(nested, dict):
                if _PAYLOAD_KEY_HINTS.intersection(nested.keys()):
                    return nested
                return nested
            if isinstance(nested, str):
                nested_payload = _try_parse_json(_sanitize_json_like(_strip_markdown_wrappers(nested)))
                if isinstance(nested_payload, dict):
                    return nested_payload
        return parsed

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                if _PAYLOAD_KEY_HINTS.intersection(item.keys()):
                    return item
                return item
    return None


def _extract_google_response_text(response: Any) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    chunks: list[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            chunk = str(getattr(part, "text", "") or "").strip()
            if chunk:
                chunks.append(chunk)
    return "".join(chunks).strip()


def _extract_openai_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict):
                chunk = str(part.get("text") or "").strip()
                if chunk:
                    chunks.append(chunk)
        return "".join(chunks).strip()
    return str(content or "").strip()


def _extract_anthropic_response_text(response: Any) -> str:
    blocks = getattr(response, "content", None) or []
    chunks: list[str] = []
    for block in blocks:
        block_type = str(getattr(block, "type", "") or "")
        if block_type == "text":
            text = str(getattr(block, "text", "") or "").strip()
            if text:
                chunks.append(text)
            continue
        if isinstance(block, dict) and str(block.get("type") or "") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _normalize_payload(payload: dict) -> dict:
    raw_items = payload.get("物品明细")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items") if isinstance(payload.get("items"), list) else []

    items: list[dict] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        name = str(
            raw.get("名称")
            or raw.get("物品名称")
            or raw.get("item_name")
            or raw.get("name")
            or ""
        ).strip()
        if not name:
            continue
        item = {
            "item_name": name,
            "quantity": _normalize_quantity(raw.get("数量") or raw.get("quantity")),
        }
        unit_price = _normalize_unit_price(raw.get("单价") or raw.get("unit_price") or raw.get("price"))
        if unit_price is not None:
            item["unit_price"] = unit_price
        items.append(item)

    return {
        "serial_number": str(payload.get("流水号") or payload.get("serial_number") or "").strip(),
        "department": str(payload.get("供应商名称") or payload.get("department") or "").strip(),
        "handler": str(payload.get("经办人") or payload.get("handler") or "").strip(),
        "request_date": _normalize_date(payload.get("日期") or payload.get("request_date")),
        "items": items,
    }


def _resolve_media_for_google(file_path: Path) -> Any:
    mime_type = (mimetypes.guess_type(file_path.name)[0] or "").lower()
    if mime_type.startswith("image/"):
        with Image.open(file_path) as image:
            image.load()
            return image.convert("RGB")
    return {
        "mime_type": mime_type or "application/octet-stream",
        "data": file_path.read_bytes(),
    }


def _resolve_mime_type(file_path: Path) -> str:
    return (mimetypes.guess_type(file_path.name)[0] or "application/octet-stream").lower()


def _image_to_jpeg_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _load_vision_image_bytes(file_path: Path) -> tuple[str, bytes]:
    mime_type = _resolve_mime_type(file_path)
    if mime_type.startswith("image/"):
        try:
            with Image.open(file_path) as image:
                image.load()
                return "image/jpeg", _image_to_jpeg_bytes(image)
        except Exception as exc:
            raise GeminiParseError("读取图片失败，请更换图片后重试。") from exc
    if mime_type == "application/pdf":
        try:
            import pdfplumber
        except ModuleNotFoundError as exc:
            raise GeminiParseError("缺少 pdfplumber 依赖，无法在云端协议下解析 PDF。") from exc

        try:
            with pdfplumber.open(str(file_path)) as pdf:
                if not pdf.pages:
                    raise GeminiParseError("PDF 不包含可解析页面，请重新上传。")
                first_page = pdf.pages[0]
                page_image = first_page.to_image(resolution=180).original
            return "image/jpeg", _image_to_jpeg_bytes(page_image)
        except GeminiParseError:
            raise
        except Exception as exc:
            raise GeminiParseError("PDF 转图片失败，请改用 Google 协议或本地 OCR。") from exc
    raise GeminiParseError("云端视觉协议仅支持图片或 PDF 文件。")


def _build_openai_image_data_url(file_path: Path) -> str:
    mime_type, image_bytes = _load_vision_image_bytes(file_path)
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _normalize_google_endpoint(base_url: str | None) -> str:
    raw = str(base_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    endpoint = (parsed.netloc or parsed.path or "").strip().rstrip("/")
    path = (parsed.path or "").strip().rstrip("/")
    if parsed.netloc and path:
        return f"{parsed.netloc}{path}"
    return endpoint


def _build_google_model(api_key: str, model_name: str, base_url: str):
    if not api_key:
        raise GeminiParseError("未配置 API Key，请先在系统设置中填写后重试。")

    configure_kwargs: dict[str, Any] = {"api_key": api_key}
    endpoint = _normalize_google_endpoint(base_url)
    if endpoint:
        configure_kwargs["client_options"] = {"api_endpoint": endpoint}

    genai.configure(**configure_kwargs)
    return genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0,
        },
    )


def _get_google_model(
    *,
    api_key_override: str | None = None,
    model_name_override: str | None = None,
    base_url_override: str | None = None,
):
    global _GOOGLE_MODEL, _GOOGLE_MODEL_SIGNATURE

    api_key, model_name, timeout_seconds = resolve_gemini_settings(api_key_override)
    if model_name_override is not None and str(model_name_override).strip():
        model_name = str(model_name_override).strip()
    if not model_name:
        model_name = DEFAULT_GEMINI_MODEL_NAME

    base_url = str(base_url_override or "").strip()
    signature = (api_key, model_name, base_url)

    with _GOOGLE_MODEL_LOCK:
        if _GOOGLE_MODEL is None or _GOOGLE_MODEL_SIGNATURE != signature:
            _GOOGLE_MODEL = _build_google_model(api_key, model_name, base_url)
            _GOOGLE_MODEL_SIGNATURE = signature
        return _GOOGLE_MODEL, (timeout_seconds or DEFAULT_GEMINI_TIMEOUT_SECONDS)


def _extract_openai_error_detail(error: Exception) -> str:
    name = type(error).__name__
    message = str(error or "").strip()
    if name in {"APITimeoutError", "Timeout", "TimeoutError"}:
        return "OpenAI 兼容接口请求超时，请稍后重试，或切换为手动录入。"
    if name in {"RateLimitError", "ResourceExhausted"}:
        return "OpenAI 兼容接口配额不足或请求过于频繁，请稍后重试。"
    if name in {"APIConnectionError", "ConnectError", "ConnectionError"}:
        return "OpenAI 兼容接口网络连接失败，请检查网络或中转地址。"
    if "quota" in message.lower():
        return "OpenAI 兼容接口配额不足，请检查账号额度。"
    return f"OpenAI 兼容接口调用失败: {message or name}"


def _extract_anthropic_error_detail(error: Exception) -> str:
    name = type(error).__name__
    message = str(error or "").strip()
    lowered = message.lower()
    if "timeout" in lowered or "timed out" in lowered:
        return "Anthropic 接口请求超时，请稍后重试，或切换为手动录入。"
    if "rate" in lowered or "quota" in lowered or "429" in lowered:
        return "Anthropic 接口配额不足或请求过于频繁，请稍后重试。"
    if "connection" in lowered or "network" in lowered:
        return "Anthropic 接口网络连接失败，请检查网络或中转地址。"
    return f"Anthropic 接口调用失败: {message or name}"


def _parse_with_google(
    file_path: Path,
    *,
    api_key_override: str | None = None,
    model_name_override: str | None = None,
    base_url_override: str | None = None,
) -> dict:
    model, timeout_seconds = _get_google_model(
        api_key_override=api_key_override,
        model_name_override=model_name_override,
        base_url_override=base_url_override,
    )
    media = _resolve_media_for_google(file_path)

    try:
        response = model.generate_content(
            [_SYSTEM_PROMPT, media],
            request_options={"timeout": timeout_seconds},
        )
    except google_exceptions.ResourceExhausted as exc:
        raise GeminiParseError("Google 接口配额不足或请求过于频繁，请稍后重试。") from exc
    except google_exceptions.DeadlineExceeded as exc:
        raise GeminiParseError("Google 接口请求超时，请稍后重试。") from exc
    except google_exceptions.GoogleAPICallError as exc:
        raise GeminiParseError("Google 接口调用失败，请检查网络或接口地址。") from exc
    except Exception as exc:
        raise GeminiParseError("Google 接口解析失败，请稍后重试或手动录入。") from exc

    payload = _safe_json_loads(_extract_google_response_text(response))
    return _normalize_payload(payload)


def _parse_with_openai(
    file_path: Path,
    *,
    api_key_override: str | None = None,
    model_name_override: str | None = None,
    base_url_override: str | None = None,
) -> dict:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise GeminiParseError("缺少 openai 依赖，请先安装后再使用 OpenAI 兼容协议。") from exc

    api_key = str(api_key_override or "").strip()
    if not api_key:
        raise GeminiParseError("未配置 API Key，请先在系统设置中填写后重试。")

    model_name = str(model_name_override or "").strip() or _DEFAULT_OPENAI_MODEL
    base_url = str(base_url_override or "").strip()
    image_data_url = _build_openai_image_data_url(file_path)

    try:
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = OpenAI(**client_kwargs)

        completion = client.chat.completions.create(
            model=model_name,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请提取流水号、物品明细（名称/数量/单价）、供应商名称、日期，并仅返回 JSON。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                    ],
                },
            ],
        )
    except Exception as exc:
        raise GeminiParseError(_extract_openai_error_detail(exc)) from exc

    payload = _safe_json_loads(_extract_openai_response_text(completion))
    return _normalize_payload(payload)


def _parse_with_anthropic(
    file_path: Path,
    *,
    api_key_override: str | None = None,
    model_name_override: str | None = None,
    base_url_override: str | None = None,
) -> dict:
    try:
        from anthropic import Anthropic
    except ModuleNotFoundError as exc:
        raise GeminiParseError("缺少 anthropic 依赖，请先安装后再使用 Anthropic 协议。") from exc

    api_key = str(api_key_override or "").strip()
    if not api_key:
        raise GeminiParseError("未配置 API Key，请先在系统设置中填写后重试。")

    model_name = str(model_name_override or "").strip() or _DEFAULT_ANTHROPIC_MODEL
    base_url = str(base_url_override or "").strip()
    media_type, image_bytes = _load_vision_image_bytes(file_path)
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = Anthropic(**client_kwargs)
        message = client.messages.create(
            model=model_name,
            max_tokens=2048,
            temperature=0,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请提取流水号、物品明细（名称/数量/单价）、供应商名称、日期，并仅返回 JSON。",
                        },
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded_image,
                            },
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        raise GeminiParseError(_extract_anthropic_error_detail(exc)) from exc

    payload = _safe_json_loads(_extract_anthropic_response_text(message))
    return _normalize_payload(payload)


def reset_gemini_model_cache() -> None:
    global _GOOGLE_MODEL, _GOOGLE_MODEL_SIGNATURE
    with _GOOGLE_MODEL_LOCK:
        _GOOGLE_MODEL = None
        _GOOGLE_MODEL_SIGNATURE = None


def parse_document_with_gemini(
    file_path: str | Path,
    *,
    protocol: str = "openai",
    api_key_override: str | None = None,
    model_name_override: str | None = None,
    base_url_override: str | None = None,
) -> dict:
    path = Path(file_path).resolve()
    if not path.exists():
        raise GeminiParseError("上传文件不存在，请重新上传。")

    normalized_protocol = _normalize_protocol(protocol)
    if normalized_protocol == "openai":
        return _parse_with_openai(
            path,
            api_key_override=api_key_override,
            model_name_override=model_name_override,
            base_url_override=base_url_override,
        )
    if normalized_protocol == "anthropic":
        return _parse_with_anthropic(
            path,
            api_key_override=api_key_override,
            model_name_override=model_name_override,
            base_url_override=base_url_override,
        )
    return _parse_with_google(
        path,
        api_key_override=api_key_override,
        model_name_override=model_name_override,
        base_url_override=base_url_override,
    )
