import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiosqlite

from .constants import ALLOWED_COLUMNS, DB_PATH
from .filters import build_item_filters
from .history import diff_item_fields, fetch_item_row, insert_item_history


TEXT_FIELD_MAX_LENGTH = {
    "serial_number": 120,
    "department": 120,
    "handler": 80,
    "request_date": 32,
    "item_name": 200,
    "purchase_link": 2000,
}

DATE_CANONICAL_PATTERN = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
DATE_COMPACT_PATTERN = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
DEFAULT_STATUS = "待采购"
DEFAULT_PAYMENT_STATUS = "未付款"
DEFAULT_INVOICE_ISSUED = 0
INSERT_ITEM_SQL = """
    INSERT INTO items (
        serial_number, department, handler, request_date,
        item_name, quantity, purchase_link, unit_price,
        status, invoice_issued, payment_status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
FULLWIDTH_TRANSLATION = str.maketrans({
    "０": "0",
    "１": "1",
    "２": "2",
    "３": "3",
    "４": "4",
    "５": "5",
    "６": "6",
    "７": "7",
    "８": "8",
    "９": "9",
    "：": ":",
    "／": "/",
    "．": ".",
    "－": "-",
    "　": " ",
})


def _normalize_required_text(field: str, value) -> str:
    text = str(value or "").translate(FULLWIDTH_TRANSLATION).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        raise ValueError(f"{field} 不能为空")
    limit = TEXT_FIELD_MAX_LENGTH.get(field)
    if limit is not None and len(text) > limit:
        raise ValueError(f"{field} 长度不能超过 {limit}")
    return text


def _normalize_optional_text(field: str, value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).translate(FULLWIDTH_TRANSLATION).strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    limit = TEXT_FIELD_MAX_LENGTH.get(field)
    if limit is not None and len(text) > limit:
        raise ValueError(f"{field} 长度不能超过 {limit}")
    return text


def _normalize_quantity(value) -> float:
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        raise ValueError("quantity 必须为数字")
    if quantity <= 0:
        raise ValueError("quantity 必须 > 0")
    return quantity


def _normalize_unit_price(value) -> Optional[float]:
    if value is None:
        return None
    try:
        unit_price = float(value)
    except (TypeError, ValueError):
        raise ValueError("unit_price 必须为数字")
    if unit_price < 0:
        raise ValueError("unit_price 不能为负数")
    return unit_price


def _normalize_request_date(value) -> str:
    """容错解析日期并统一为 YYYY-MM-DD。"""
    raw = _normalize_required_text("request_date", value)
    normalized = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("号", "")
        .replace("/", "-")
        .replace(".", "-")
        .replace("T", " ")
        .strip()
    )
    if " " in normalized:
        normalized = normalized.split(" ", 1)[0].strip()
    normalized = re.sub(r"-+", "-", normalized).strip("-")

    matched = DATE_CANONICAL_PATTERN.fullmatch(normalized)
    if matched:
        year, month, day = matched.groups()
    else:
        compact = DATE_COMPACT_PATTERN.fullmatch(normalized)
        if compact:
            year, month, day = compact.groups()
        else:
            raise ValueError("request_date 格式应为 YYYY-MM-DD（支持 YYYY/M/D、YYYY年M月D日）")

    try:
        parsed = datetime(int(year), int(month), int(day))
    except ValueError:
        raise ValueError("request_date 不是有效日期")
    return parsed.strftime("%Y-%m-%d")


def _normalize_serial_number(value) -> str:
    return _normalize_required_text("serial_number", value).upper().replace(" ", "")


def _normalize_purchase_link(value) -> Optional[str]:
    text = _normalize_optional_text("purchase_link", value)
    if not text:
        return None
    compact = text.replace(" ", "")
    compact = re.sub(r"[，。；;、）)\]>》]+$", "", compact)
    if compact.lower().startswith("www."):
        compact = f"https://{compact}"
    parsed = urlparse(compact)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("purchase_link 必须是有效的 http(s) URL")
    if len(compact) > TEXT_FIELD_MAX_LENGTH["purchase_link"]:
        raise ValueError(f"purchase_link 长度不能超过 {TEXT_FIELD_MAX_LENGTH['purchase_link']}")
    return compact


def normalize_item_payload(item: dict) -> dict:
    """标准化并校验新增记录。"""
    payload = dict(item)
    payload["serial_number"] = _normalize_serial_number(payload.get("serial_number"))
    payload["department"] = _normalize_required_text("department", payload.get("department"))
    payload["handler"] = _normalize_required_text("handler", payload.get("handler"))
    payload["request_date"] = _normalize_request_date(payload.get("request_date"))
    payload["item_name"] = _normalize_required_text("item_name", payload.get("item_name"))
    payload["purchase_link"] = _normalize_purchase_link(payload.get("purchase_link"))
    payload["quantity"] = _normalize_quantity(payload.get("quantity"))
    payload["unit_price"] = _normalize_unit_price(payload.get("unit_price"))
    return payload


def normalize_update_payload(updates: dict) -> dict:
    """标准化并校验更新记录。"""
    payload = dict(updates)
    if "serial_number" in payload:
        payload["serial_number"] = _normalize_serial_number(payload.get("serial_number"))
    if "department" in payload:
        payload["department"] = _normalize_required_text("department", payload.get("department"))
    if "handler" in payload:
        payload["handler"] = _normalize_required_text("handler", payload.get("handler"))
    if "request_date" in payload:
        payload["request_date"] = _normalize_request_date(payload.get("request_date"))
    if "item_name" in payload:
        payload["item_name"] = _normalize_required_text("item_name", payload.get("item_name"))
    if "purchase_link" in payload:
        payload["purchase_link"] = _normalize_purchase_link(payload.get("purchase_link"))
    if "quantity" in payload:
        payload["quantity"] = _normalize_quantity(payload.get("quantity"))
    if "unit_price" in payload:
        payload["unit_price"] = _normalize_unit_price(payload.get("unit_price"))
    return payload


def _validate_allowed_columns(payload: dict) -> None:
    invalid = set(payload.keys()) - ALLOWED_COLUMNS
    if invalid:
        raise ValueError(f"不允许的字段: {invalid}")


def _deduplicate_positive_ids(raw_ids: list[int]) -> list[int]:
    unique_ids = []
    seen = set()
    for raw in raw_ids:
        item_id = int(raw)
        if item_id <= 0:
            raise ValueError("ids 必须为正整数")
        if item_id not in seen:
            seen.add(item_id)
            unique_ids.append(item_id)
    return unique_ids


def _build_insert_values(payload: dict) -> tuple:
    return (
        payload["serial_number"],
        payload["department"],
        payload["handler"],
        payload["request_date"],
        payload["item_name"],
        payload["quantity"],
        payload.get("purchase_link"),
        payload.get("unit_price"),
        payload.get("status", DEFAULT_STATUS),
        payload.get("invoice_issued", DEFAULT_INVOICE_ISSUED),
        payload.get("payment_status", DEFAULT_PAYMENT_STATUS),
    )


async def _insert_item_with_history(db: aiosqlite.Connection, payload: dict) -> int:
    cursor = await db.execute(INSERT_ITEM_SQL, _build_insert_values(payload))
    item_id = int(cursor.lastrowid)
    snapshot = await fetch_item_row(db, item_id)
    await insert_item_history(
        db,
        item_id=item_id,
        action="create",
        before_data=None,
        after_data=snapshot,
        changed_fields=sorted(ALLOWED_COLUMNS),
    )
    return item_id


def _has_effective_changes(before_data: dict, updates: dict) -> bool:
    for field, new_value in updates.items():
        if before_data.get(field) != new_value:
            return True
    return False


async def get_items(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None
) -> list[dict]:
    """获取所有物品列表。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM items"
        conditions, params = build_item_filters(
            status=status, department=department, month=month, keyword=keyword
        )

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        if page is not None and page_size is not None:
            offset = max(0, (page - 1) * page_size)
            query += " LIMIT ? OFFSET ?"
            params.extend([page_size, offset])

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def count_items(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None
) -> int:
    """获取筛选后的记录总数。"""
    async with aiosqlite.connect(DB_PATH) as db:
        query = "SELECT COUNT(*) FROM items"
        conditions, params = build_item_filters(
            status=status, department=department, month=month, keyword=keyword
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return int(row[0] if row else 0)


async def get_item(item_id: int) -> Optional[dict]:
    """获取单个物品详情。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM items WHERE id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_item(item: dict) -> int:
    """创建新物品记录。"""
    payload = normalize_item_payload(item)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        item_id = await _insert_item_with_history(db, payload)
        await db.commit()
        return item_id


async def update_item(item_id: int, updates: dict) -> bool:
    """更新物品记录。"""
    if not updates:
        return False
    payload = normalize_update_payload(updates)
    _validate_allowed_columns(payload)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        before_data = await fetch_item_row(db, item_id)
        if not before_data:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in payload.keys())
        values = list(payload.values())
        values.append(item_id)
        cursor = await db.execute(
            f"UPDATE items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values,
        )
        if cursor.rowcount <= 0:
            await db.rollback()
            return False

        after_data = await fetch_item_row(db, item_id)
        if after_data:
            changed_fields = diff_item_fields(before_data, after_data)
            if changed_fields:
                await insert_item_history(
                    db,
                    item_id=item_id,
                    action="update",
                    before_data=before_data,
                    after_data=after_data,
                    changed_fields=changed_fields,
                )
        await db.commit()
        return True


async def delete_item(item_id: int) -> bool:
    """删除物品记录。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        before_data = await fetch_item_row(db, item_id)
        if not before_data:
            return False

        cursor = await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        if cursor.rowcount > 0:
            await insert_item_history(
                db,
                item_id=item_id,
                action="delete",
                before_data=before_data,
                after_data=None,
                changed_fields=sorted(ALLOWED_COLUMNS),
            )
        await db.commit()
        return cursor.rowcount > 0


async def batch_create_items(items: list[dict]) -> list[int]:
    """批量创建物品记录。"""
    created_ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for raw_item in items:
            item = normalize_item_payload(raw_item)
            async with db.execute(
                """
                SELECT 1 FROM items
                WHERE serial_number = ? AND item_name = ? AND handler = ? LIMIT 1
                """,
                (item["serial_number"], item["item_name"], item["handler"]),
            ) as cursor:
                exists = await cursor.fetchone()
                if exists:
                    continue
            item_id = await _insert_item_with_history(db, item)
            created_ids.append(item_id)
        await db.commit()
    return created_ids


async def get_existing_items_by_keys(keys: list[tuple[str, str, str]]) -> dict[tuple[str, str, str], dict]:
    """按 (serial_number, item_name, handler) 批量查询已存在记录。"""
    unique_keys = list(dict.fromkeys(keys))
    if not unique_keys:
        return {}

    results: dict[tuple[str, str, str], dict] = {}
    chunk_size = 200
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for start in range(0, len(unique_keys), chunk_size):
            chunk = unique_keys[start:start + chunk_size]
            placeholders = ", ".join(["(?, ?, ?)"] * len(chunk))
            params = []
            for serial_number, item_name, handler in chunk:
                params.extend([serial_number, item_name, handler])
            query = (
                "SELECT * FROM items "
                f"WHERE (serial_number, item_name, handler) IN ({placeholders})"
            )
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    record = dict(row)
                    key = (
                        str(record.get("serial_number") or "").strip(),
                        str(record.get("item_name") or "").strip(),
                        str(record.get("handler") or "").strip(),
                    )
                    results[key] = record

    return results


async def bulk_update_quantities(quantity_updates: dict[int, float]) -> int:
    """批量更新数量，单次连接提交，减少导入合并开销。"""
    if not quantity_updates:
        return 0

    normalized_updates: dict[int, float] = {}
    for item_id, quantity in quantity_updates.items():
        normalized_updates[int(item_id)] = _normalize_quantity(quantity)

    updated_count = 0
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for item_id, quantity in normalized_updates.items():
            before_data = await fetch_item_row(db, item_id)
            if not before_data:
                continue
            cursor = await db.execute(
                "UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (quantity, item_id),
            )
            if cursor.rowcount <= 0:
                continue
            after_data = await fetch_item_row(db, item_id)
            if after_data:
                changed_fields = diff_item_fields(before_data, after_data)
                if changed_fields:
                    await insert_item_history(
                        db,
                        item_id=item_id,
                        action="update",
                        before_data=before_data,
                        after_data=after_data,
                        changed_fields=changed_fields,
                    )
            updated_count += 1
        await db.commit()

    return updated_count


async def batch_update_items(item_ids: list[int], updates: dict) -> dict:
    """批量更新记录，单连接事务提交并写入历史。"""
    if not item_ids:
        return {
            "updated_count": 0,
            "missing_ids": [],
            "unchanged_count": 0,
        }
    payload = normalize_update_payload(updates)
    if not payload:
        raise ValueError("未提供可更新字段")
    _validate_allowed_columns(payload)
    unique_ids = _deduplicate_positive_ids(item_ids)

    placeholders = ",".join("?" for _ in unique_ids)
    existing_ids = set()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"SELECT id FROM items WHERE id IN ({placeholders})",
            unique_ids,
        ) as cursor:
            rows = await cursor.fetchall()
            existing_ids = {int(row["id"]) for row in rows}

        missing_ids = [item_id for item_id in unique_ids if item_id not in existing_ids]
        set_clause = ", ".join(f"{k} = ?" for k in payload.keys())
        updated_count = 0
        unchanged_count = 0

        for item_id in unique_ids:
            if item_id not in existing_ids:
                continue
            before_data = await fetch_item_row(db, item_id)
            if not before_data:
                continue
            if not _has_effective_changes(before_data, payload):
                unchanged_count += 1
                continue

            values = list(payload.values())
            values.append(item_id)
            cursor = await db.execute(
                f"UPDATE items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                values,
            )
            if cursor.rowcount <= 0:
                continue

            after_data = await fetch_item_row(db, item_id)
            if after_data:
                changed_fields = diff_item_fields(before_data, after_data)
                if changed_fields:
                    await insert_item_history(
                        db,
                        item_id=item_id,
                        action="update",
                        before_data=before_data,
                        after_data=after_data,
                        changed_fields=changed_fields,
                    )
            updated_count += 1

        await db.commit()

    return {
        "updated_count": updated_count,
        "missing_ids": missing_ids,
        "unchanged_count": unchanged_count,
    }


async def get_serial_numbers() -> list[str]:
    """获取所有流水号（用于自动补全）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT serial_number FROM items ORDER BY serial_number DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_departments() -> list[str]:
    """获取所有部门（用于自动补全）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT department FROM items ORDER BY department"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_handlers() -> list[str]:
    """获取所有经办人（用于自动补全）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT handler FROM items ORDER BY handler"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
