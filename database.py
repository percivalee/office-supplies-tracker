import aiosqlite
from enum import Enum
from typing import Optional

DB_PATH = "office_supplies.db"

ALLOWED_COLUMNS = frozenset({
    'serial_number', 'department', 'handler', 'request_date',
    'item_name', 'quantity', 'purchase_link', 'unit_price',
    'status', 'invoice_issued', 'payment_status'
})


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
        await db.commit()
        return cursor.lastrowid


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
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values())
        values.append(item_id)
        cursor = await db.execute(
            f"UPDATE items SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            values
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_item(item_id: int) -> bool:
    """删除物品记录"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM items WHERE id = ?", (item_id,))
        await db.commit()
        return cursor.rowcount > 0


async def batch_create_items(items: list[dict]) -> list[int]:
    """批量创建物品记录"""
    created_ids = []
    async with aiosqlite.connect(DB_PATH) as db:
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
            created_ids.append(cursor.lastrowid)
        await db.commit()
    return created_ids


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
