import json
import aiosqlite
from enum import Enum
from typing import Optional

DB_PATH = "office_supplies.db"

ALLOWED_COLUMNS = frozenset({
    'serial_number', 'department', 'handler', 'request_date',
    'item_name', 'quantity', 'purchase_link', 'unit_price',
    'status', 'invoice_issued', 'payment_status'
})

ITEM_COLUMNS = (
    "id", "serial_number", "department", "handler", "request_date",
    "item_name", "quantity", "purchase_link", "unit_price", "status",
    "invoice_issued", "payment_status", "created_at", "updated_at"
)


class PaymentStatus(str, Enum):
    UNPAID = "未付款"
    PAID = "已付款"
    REIMBURSED = "已报销"


class ItemStatus(str, Enum):
    PENDING = "待采购"
    PURCHASED = "已采购"
    ARRIVED = "已到货"
    DISTRIBUTED = "已发放"


def _escape_like_pattern(value: str) -> str:
    """转义 LIKE 特殊字符，避免输入中的 %/_ 被当作通配符。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _build_item_filters(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None
) -> tuple[list[str], list]:
    """构建筛选条件与参数。"""
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if department:
        conditions.append("department = ?")
        params.append(department)
    if month:
        conditions.append("request_date LIKE ?")
        params.append(f"{month}%")
    if keyword:
        pattern = f"%{_escape_like_pattern(keyword)}%"
        conditions.append(
            "("
            "serial_number LIKE ? ESCAPE '\\' OR "
            "item_name LIKE ? ESCAPE '\\' OR "
            "handler LIKE ? ESCAPE '\\' OR "
            "department LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern])

    return conditions, params


def _build_history_filters(
    action: Optional[str] = None,
    keyword: Optional[str] = None,
    month: Optional[str] = None
) -> tuple[list[str], list]:
    """构建历史记录筛选条件与参数。"""
    conditions = []
    params = []

    if action:
        conditions.append("action = ?")
        params.append(action)
    if month:
        conditions.append("created_at LIKE ?")
        params.append(f"{month}%")
    if keyword:
        pattern = f"%{_escape_like_pattern(keyword)}%"
        conditions.append(
            "("
            "serial_number LIKE ? ESCAPE '\\' OR "
            "item_name LIKE ? ESCAPE '\\' OR "
            "handler LIKE ? ESCAPE '\\' OR "
            "department LIKE ? ESCAPE '\\' OR "
            "changed_fields LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    return conditions, params


def _to_json_text(data: Optional[dict]) -> Optional[str]:
    """将字典序列化为 JSON 文本。"""
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def _safe_json_loads(value: Optional[str]) -> Optional[dict]:
    """解析 JSON 文本，失败时返回 None。"""
    if not value:
        return None
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        return None


def _diff_item_fields(before: dict, after: dict) -> list[str]:
    """计算更新前后发生变化的字段。"""
    changed = []
    for column in ALLOWED_COLUMNS:
        if before.get(column) != after.get(column):
            changed.append(column)
    return sorted(changed)


async def _fetch_item_row(db: aiosqlite.Connection, item_id: int) -> Optional[dict]:
    """按 id 查询完整记录，用于历史快照。"""
    columns = ", ".join(ITEM_COLUMNS)
    async with db.execute(
        f"SELECT {columns} FROM items WHERE id = ?",
        (item_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def _insert_item_history(
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
            _to_json_text(before_data),
            _to_json_text(after_data),
        )
    )


async def init_db():
    """初始化数据库表"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_number TEXT NOT NULL,
                department TEXT NOT NULL,
                handler TEXT NOT NULL,
                request_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                purchase_link TEXT,
                unit_price REAL,
                status TEXT NOT NULL DEFAULT '待采购',
                invoice_issued BOOLEAN DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT '未付款',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_number, item_name, handler)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS item_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                action TEXT NOT NULL,
                serial_number TEXT,
                department TEXT,
                handler TEXT,
                item_name TEXT,
                changed_fields TEXT,
                before_data TEXT,
                after_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_history_created_at ON item_history(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_history_action ON item_history(action)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_item_history_item_id ON item_history(item_id)"
        )
        await db.commit()


async def get_items(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None
) -> list[dict]:
    """获取所有物品列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM items"
        conditions, params = _build_item_filters(
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
        conditions, params = _build_item_filters(
            status=status, department=department, month=month, keyword=keyword
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return int(row[0] if row else 0)


async def get_stats_summary() -> dict:
    """获取统计信息（SQL 聚合）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN invoice_issued = 1 THEN 1 ELSE 0 END) AS issued,
                SUM(CASE WHEN invoice_issued = 1 THEN 0 ELSE 1 END) AS not_issued
            FROM items
            """
        ) as cursor:
            row = await cursor.fetchone()
            total = int(row[0] if row and row[0] is not None else 0)
            issued = int(row[1] if row and row[1] is not None else 0)
            not_issued = int(row[2] if row and row[2] is not None else 0)

        async with db.execute(
            "SELECT status, COUNT(*) FROM items GROUP BY status"
        ) as cursor:
            status_rows = await cursor.fetchall()
            status_count = {str(status): int(count) for status, count in status_rows}

        async with db.execute(
            "SELECT payment_status, COUNT(*) FROM items GROUP BY payment_status"
        ) as cursor:
            payment_rows = await cursor.fetchall()
            payment_count = {str(status): int(count) for status, count in payment_rows}

    return {
        "total": total,
        "status_count": status_count,
        "payment_count": payment_count,
        "invoice_count": {
            "issued": issued,
            "not_issued": not_issued,
        },
    }


async def get_amount_report(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None
) -> dict:
    """金额统计报表。"""
    conditions, params = _build_item_filters(
        status=status, department=department, month=month, keyword=keyword
    )
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        summary_query = f"""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount,
                COALESCE(SUM(CASE WHEN unit_price IS NOT NULL THEN quantity * unit_price ELSE 0 END), 0) AS priced_amount,
                SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END) AS missing_price_records
            FROM items
            {where_clause}
        """
        async with db.execute(summary_query, params) as cursor:
            row = await cursor.fetchone()
            summary = dict(row) if row else {}

        department_query = f"""
            SELECT
                department,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount,
                SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END) AS missing_price_records
            FROM items
            {where_clause}
            GROUP BY department
            ORDER BY total_amount DESC, record_count DESC
            LIMIT 30
        """
        async with db.execute(department_query, params) as cursor:
            by_department = [dict(row) for row in await cursor.fetchall()]

        status_query = f"""
            SELECT
                status,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount
            FROM items
            {where_clause}
            GROUP BY status
            ORDER BY total_amount DESC, record_count DESC
        """
        async with db.execute(status_query, params) as cursor:
            by_status = [dict(row) for row in await cursor.fetchall()]

        month_conditions = list(conditions)
        month_params = list(params)
        month_conditions.append("request_date IS NOT NULL")
        month_conditions.append("request_date <> ''")
        month_where = f" WHERE {' AND '.join(month_conditions)}"

        month_query = f"""
            SELECT
                SUBSTR(request_date, 1, 7) AS month,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount
            FROM items
            {month_where}
            GROUP BY month
            HAVING month IS NOT NULL AND month <> ''
            ORDER BY month DESC
            LIMIT 12
        """
        async with db.execute(month_query, month_params) as cursor:
            by_month = [dict(row) for row in await cursor.fetchall()]

    return {
        "summary": {
            "total_records": int(summary.get("total_records") or 0),
            "total_amount": float(summary.get("total_amount") or 0),
            "priced_amount": float(summary.get("priced_amount") or 0),
            "missing_price_records": int(summary.get("missing_price_records") or 0),
        },
        "by_department": [
            {
                "department": row.get("department") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
                "missing_price_records": int(row.get("missing_price_records") or 0),
            }
            for row in by_department
        ],
        "by_status": [
            {
                "status": row.get("status") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
            }
            for row in by_status
        ],
        "by_month": [
            {
                "month": row.get("month") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
            }
            for row in by_month
        ],
    }


async def get_item(item_id: int) -> Optional[dict]:
    """获取单个物品详情"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM items WHERE id = ?", (item_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_item(item: dict) -> int:
    """创建新物品记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            INSERT INTO items (serial_number, department, handler, request_date,
                             item_name, quantity, purchase_link, unit_price,
                             status, invoice_issued, payment_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["serial_number"], item["department"], item["handler"],
            item["request_date"], item["item_name"], item["quantity"],
            item.get("purchase_link"), item.get("unit_price"),
            item.get("status", "待采购"), item.get("invoice_issued", 0),
            item.get("payment_status", "未付款")
        ))
        item_id = cursor.lastrowid
        snapshot = await _fetch_item_row(db, item_id)
        await _insert_item_history(
            db,
            item_id=item_id,
            action="create",
            before_data=None,
            after_data=snapshot,
            changed_fields=sorted(ALLOWED_COLUMNS),
        )
        await db.commit()
        return item_id


async def update_item(item_id: int, updates: dict) -> bool:
    """更新物品记录"""
    if not updates:
        return False
    if "quantity" in updates:
        quantity = updates["quantity"]
        if quantity is None:
            raise ValueError("quantity 不能为空")
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise ValueError("quantity 必须为数字")
        if quantity <= 0:
            raise ValueError("quantity 必须 > 0")
        updates["quantity"] = quantity
    if "unit_price" in updates and updates["unit_price"] is not None:
        unit_price = updates["unit_price"]
        try:
            unit_price = float(unit_price)
        except (TypeError, ValueError):
            raise ValueError("unit_price 必须为数字")
        if unit_price < 0:
            raise ValueError("unit_price 不能为负数")
        updates["unit_price"] = unit_price
    invalid = set(updates.keys()) - ALLOWED_COLUMNS
    if invalid:
        raise ValueError(f"不允许的字段: {invalid}")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        before_data = await _fetch_item_row(db, item_id)
        if not before_data:
            return False

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values())
        values.append(item_id)
        cursor = await db.execute(
            f"UPDATE items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        if cursor.rowcount <= 0:
            await db.rollback()
            return False

        after_data = await _fetch_item_row(db, item_id)
        if after_data:
            changed_fields = _diff_item_fields(before_data, after_data)
            if changed_fields:
                await _insert_item_history(
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
    """删除物品记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        before_data = await _fetch_item_row(db, item_id)
        if not before_data:
            return False

        cursor = await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        if cursor.rowcount > 0:
            await _insert_item_history(
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
    """批量创建物品记录"""
    created_ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for item in items:
            # 检查是否已存在
            async with db.execute(
                """SELECT 1 FROM items
                   WHERE serial_number = ? AND item_name = ? AND handler = ? LIMIT 1""",
                (item["serial_number"], item["item_name"], item["handler"])
            ) as cursor:
                exists = await cursor.fetchone()
                if exists:
                    continue
            cursor = await db.execute("""
                INSERT INTO items (serial_number, department, handler, request_date,
                                 item_name, quantity, purchase_link, unit_price,
                                 status, invoice_issued, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["serial_number"], item["department"], item["handler"],
                item["request_date"], item["item_name"], item["quantity"],
                item.get("purchase_link"), item.get("unit_price"),
                item.get("status", "待采购"), item.get("invoice_issued", 0),
                item.get("payment_status", "未付款")
            ))
            item_id = cursor.lastrowid
            created_ids.append(item_id)
            snapshot = await _fetch_item_row(db, item_id)
            await _insert_item_history(
                db,
                item_id=item_id,
                action="create",
                before_data=None,
                after_data=snapshot,
                changed_fields=sorted(ALLOWED_COLUMNS),
            )
        await db.commit()
    return created_ids


async def get_item_history(
    action: Optional[str] = None,
    keyword: Optional[str] = None,
    month: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
) -> list[dict]:
    """分页查询变更历史。"""
    conditions, params = _build_history_filters(
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
        record["before_data"] = _safe_json_loads(record.get("before_data"))
        record["after_data"] = _safe_json_loads(record.get("after_data"))
        records.append(record)
    return records


async def count_item_history(
    action: Optional[str] = None,
    keyword: Optional[str] = None,
    month: Optional[str] = None
) -> int:
    """统计变更历史条数。"""
    conditions, params = _build_history_filters(
        action=action, keyword=keyword, month=month
    )
    query = "SELECT COUNT(*) FROM item_history"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return int(row[0] if row else 0)


async def get_serial_numbers() -> list[str]:
    """获取所有流水号（用于自动补全）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT serial_number FROM items ORDER BY serial_number DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_departments() -> list[str]:
    """获取所有部门（用于自动补全）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT department FROM items ORDER BY department"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_handlers() -> list[str]:
    """获取所有经办人（用于自动补全）"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT handler FROM items ORDER BY handler"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
