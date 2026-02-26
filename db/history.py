import json
from typing import Optional

import aiosqlite

from .constants import ALLOWED_COLUMNS, DB_PATH, ITEM_COLUMNS
from .filters import build_history_filters


def to_json_text(data: Optional[dict]) -> Optional[str]:
    """将字典序列化为 JSON 文本。"""
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def safe_json_loads(value: Optional[str]) -> Optional[dict]:
    """解析 JSON 文本，失败时返回 None。"""
    if not value:
        return None
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        return None


def diff_item_fields(before: dict, after: dict) -> list[str]:
    """计算更新前后发生变化的字段。"""
    changed = []
    for column in ALLOWED_COLUMNS:
        if before.get(column) != after.get(column):
            changed.append(column)
    return sorted(changed)


async def fetch_item_row(db: aiosqlite.Connection, item_id: int) -> Optional[dict]:
    """按 id 查询完整记录，用于历史快照。"""
    columns = ", ".join(ITEM_COLUMNS)
    async with db.execute(
        f"SELECT {columns} FROM items WHERE id = ?",
        (item_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def insert_item_history(
    db: aiosqlite.Connection,
    item_id: Optional[int],
    action: str,
    before_data: Optional[dict],
    after_data: Optional[dict],
    changed_fields: Optional[list[str]] = None
) -> None:
    """写入一条变更历史。"""
    source = after_data or before_data or {}
    changed_text = ",".join(changed_fields or []) or None
    await db.execute(
        """
        INSERT INTO item_history (
            item_id, action, serial_number, department, handler, item_name,
            changed_fields, before_data, after_data
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id,
            action,
            source.get("serial_number"),
            source.get("department"),
            source.get("handler"),
            source.get("item_name"),
            changed_text,
            to_json_text(before_data),
            to_json_text(after_data),
        ),
    )


async def get_item_history(
    action: Optional[str] = None,
    keyword: Optional[str] = None,
    month: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> list[dict]:
    """分页查询变更历史。"""
    conditions, params = build_history_filters(
        action=action, keyword=keyword, month=month
    )
    query = "SELECT * FROM item_history"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([page_size, max(0, (page - 1) * page_size)])

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()

    records = []
    for row in rows:
        record = dict(row)
        record["changed_fields"] = (
            record.get("changed_fields", "").split(",")
            if record.get("changed_fields")
            else []
        )
        record["before_data"] = safe_json_loads(record.get("before_data"))
        record["after_data"] = safe_json_loads(record.get("after_data"))
        records.append(record)
    return records


async def count_item_history(
    action: Optional[str] = None,
    keyword: Optional[str] = None,
    month: Optional[str] = None
) -> int:
    """统计变更历史条数。"""
    conditions, params = build_history_filters(
        action=action, keyword=keyword, month=month
    )
    query = "SELECT COUNT(*) FROM item_history"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return int(row[0] if row else 0)
