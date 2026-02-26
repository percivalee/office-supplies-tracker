import aiosqlite
from enum import Enum
from typing import Optional
from datetime import date

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
    month: Optional[str] = None
) -> list[dict]:
    """获取所有物品列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM items"
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

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


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


async def check_exists(serial_number: str, item_name: str, handler: str) -> bool:
    """检查记录是否已存在"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT 1 FROM items
               WHERE serial_number = ? AND item_name = ? AND handler = ? LIMIT 1""",
            (serial_number, item_name, handler)
        ) as cursor:
            return await cursor.fetchone() is not None


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
