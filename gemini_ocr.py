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

from PIL import Image

from gemini_config import (
    DEFAULT_GEMINI_MODEL_NAME,
    DEFAULT_GEMINI_TIMEOUT_SECONDS,
    resolve_gemini_settings,
)


_GOOGLE_MODEL_LOCK = Lock()
_GOOGLE_MODEL = None
_GOOGLE_MODEL_SIGNATURE: tuple[str, str, str] | None = None

_REQUEST_DATE_PATTERN = re.compile(r"(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})")
_SUPPORTED_PROTOCOLS = {"google", "openai", "anthropic"}
_PAYLOAD_KEY_HINTS = {
    "流水号",
    "申领部门",
    "经办人",
    "物品明细",
    "物品名称",
    "采购链接",
    "供应商名称",
    "日期",
    "serial_number",
    "handler",
    "items",
    "department",
    "request_date",
    "purchase_link",
}
_DEFAULT_OPENAI_MODEL = "gpt-4o"
_DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
_HEADER_FIELD_KEYS = ("serial_number", "department", "handler", "request_date")

_SYSTEM_PROMPT = """
你是企业采购单据结构化抽取助手。请精确分析这张采购单据/发票图片（或 PDF 单据）。
请严格按以下 JSON 结构返回，不得输出任何 Markdown 标记或额外说明：
{
  "流水号": "单据编号，无则为空字符串",
  "申领部门": "申领/申请/领用部门，无则空字符串",
  "经办人": "经办/申领人姓名，无则空字符串",
  "日期": "YYYY-MM-DD，无则空字符串",
  "物品明细": [
    {"物品名称": "示例", "数量": 1, "采购链接": "", "单价": 0.0}
  ]
}
规则：
1) 所有字段必须存在；缺失时使用空字符串或空数组，不得编造。
2) 只返回 JSON 对象本体。
3) “申领部门”优先提取内部部门，不要误填供应商名称。
4) "物品明细" 必须是数组，未识别时返回空数组。
5) 若识别到链接，放入“采购链接”字段。
""".strip()


class GeminiParseError(RuntimeError):
    """多模态解析失败。"""


def _load_google_runtime():
    try:
        import google.generativeai as genai
        from google.api_core import exceptions as google_exceptions
    except ModuleNotFoundError as exc:
        raise GeminiParseError("缺少 google-generativeai 依赖，请先安装后再使用 Google 协议。") from exc
    return genai, google_exceptions


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


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_purchase_link(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    compact = (
        text.replace("：", ":")
        .replace("／", "/")
        .replace("．", ".")
        .replace("　", "")
        .replace(" ", "")
    )
    compact = re.sub(r"[，。；;、）)\]>》]+$", "", compact)
    if compact.lower().startswith("www."):
        compact = f"https://{compact}"
    if not re.match(r"^https?://", compact, re.IGNORECASE):
        return None
    return compact


def _coalesce_value(raw: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in raw:
            value = raw.get(key)
            if value is not None and str(value).strip() != "":
                return value
    return ""


def _extract_raw_items(payload: dict) -> list:
    for key in ("物品明细", "明细", "采购明细", "items", "item_list", "line_items", "rows"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _normalize_item_name(value: Any) -> str:
    name = _normalize_text(value)
    if not name:
        return ""
    # 去掉常见行号与链接残留，降低噪音行进入概率。
    name = re.sub(r"^\d+[\.\s、-]*", "", name).strip()
    name = re.sub(r"https?://[^\s]+", "", name).strip()
    return name


def _normalize_item_record(raw: Any) -> dict | None:
    if isinstance(raw, dict):
        name_value = _coalesce_value(
            raw,
            ("物品名称", "名称", "物品", "品名", "item_name", "name", "title"),
        )
        quantity_value = _coalesce_value(
            raw,
            ("数量", "qty", "count", "quantity", "件数"),
        )
        link_value = _coalesce_value(
            raw,
            ("采购链接", "购买链接", "关联链接", "链接", "url", "link", "purchase_link"),
        )
        if not link_value:
            link_value = _coalesce_value(raw, ("备注", "remark", "note", "说明"))
        unit_price_value = _coalesce_value(
            raw,
            ("单价", "price", "unit_price", "含税单价"),
        )
    elif isinstance(raw, (list, tuple)):
        compact_values = [_normalize_text(value) for value in raw if _normalize_text(value)]
        if not compact_values:
            return None
        name_value = compact_values[0]
        quantity_value = compact_values[1] if len(compact_values) > 1 else ""
        link_value = ""
        for value in compact_values:
            normalized_link = _normalize_purchase_link(value)
            if normalized_link:
                link_value = normalized_link
                break
        unit_price_value = ""
    else:
        return None

    item_name = _normalize_item_name(name_value)
    if not item_name:
        return None

    item: dict[str, Any] = {
        "item_name": item_name,
        "quantity": _normalize_quantity(quantity_value),
        "purchase_link": _normalize_purchase_link(link_value),
    }
    unit_price = _normalize_unit_price(unit_price_value)
    if unit_price is not None:
        item["unit_price"] = unit_price
    return item


def _normalize_items(raw_items: list[Any]) -> list[dict]:
    normalized: list[dict] = []
    for raw in raw_items:
        item = _normalize_item_record(raw)
        if not item:
            continue
        normalized.append(item)
    return normalized


def _should_use_local_supplement(parsed: dict) -> bool:
    items = parsed.get("items") or []
    if not items:
        return True
    for field in _HEADER_FIELD_KEYS:
        if not _normalize_text(parsed.get(field)):
            return True
    return False


def _merge_items_with_fallback(primary_items: list[dict], fallback_items: list[dict]) -> list[dict]:
    merged = _normalize_items(primary_items)
    if not fallback_items:
        return merged

    index: dict[tuple[str, float], int] = {}
    for idx, item in enumerate(merged):
        key = (
            re.sub(r"\s+", "", str(item.get("item_name") or "")).lower(),
            float(item.get("quantity") or 1.0),
        )
        index[key] = idx

    for item in _normalize_items(fallback_items):
        key = (
            re.sub(r"\s+", "", str(item.get("item_name") or "")).lower(),
            float(item.get("quantity") or 1.0),
        )
        existing_idx = index.get(key)
        if existing_idx is None:
            index[key] = len(merged)
            merged.append(item)
            continue
        existing = merged[existing_idx]
        if not existing.get("purchase_link") and item.get("purchase_link"):
            existing["purchase_link"] = item.get("purchase_link")
        if existing.get("unit_price") is None and item.get("unit_price") is not None:
            existing["unit_price"] = item.get("unit_price")

    return merged


def _supplement_with_local_parser(file_path: Path, parsed: dict) -> dict:
    if not _should_use_local_supplement(parsed):
        return parsed
    try:
        from parser import parse_document

        local_parsed_raw = parse_document(str(file_path))
        local_parsed = _normalize_payload(local_parsed_raw if isinstance(local_parsed_raw, dict) else {})
    except Exception:
        return parsed

    merged = dict(parsed)
    for field in _HEADER_FIELD_KEYS:
        if not _normalize_text(merged.get(field)):
            merged[field] = _normalize_text(local_parsed.get(field))
    merged["items"] = _merge_items_with_fallback(
        merged.get("items") or [],
        local_parsed.get("items") or [],
    )
    return merged


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
    if not isinstance(payload, dict):
        payload = {}

    serial_number = _normalize_text(
        _coalesce_value(payload, ("流水号", "单号", "编号", "serial_number", "serialNo"))
    )
    department = _normalize_text(
        _coalesce_value(
            payload,
            ("申领部门", "申请部门", "领用部门", "使用部门", "部门", "department"),
        )
    )
    handler = _normalize_text(
        _coalesce_value(payload, ("经办人", "申领人", "申请人", "handler", "operator"))
    )
    request_date = _normalize_date(
        _coalesce_value(payload, ("日期", "申领日期", "申请日期", "request_date", "date"))
    )
    items = _normalize_items(_extract_raw_items(payload))

    return {
        "serial_number": serial_number,
        "department": department,
        "handler": handler,
        "request_date": request_date,
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
    genai, _ = _load_google_runtime()

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
    _, google_exceptions = _load_google_runtime()
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
                            "text": "请提取流水号、申领部门、经办人、日期、物品明细（物品名称/数量/采购链接/单价），并仅返回 JSON。",
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
                            "text": "请提取流水号、申领部门、经办人、日期、物品明细（物品名称/数量/采购链接/单价），并仅返回 JSON。",
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
    parsed: dict
    if normalized_protocol == "openai":
        parsed = _parse_with_openai(
            path,
            api_key_override=api_key_override,
            model_name_override=model_name_override,
            base_url_override=base_url_override,
        )
    elif normalized_protocol == "anthropic":
        parsed = _parse_with_anthropic(
            path,
            api_key_override=api_key_override,
            model_name_override=model_name_override,
            base_url_override=base_url_override,
        )
    else:
        parsed = _parse_with_google(
            path,
            api_key_override=api_key_override,
            model_name_override=model_name_override,
            base_url_override=base_url_override,
        )

    return _supplement_with_local_parser(path, parsed)
