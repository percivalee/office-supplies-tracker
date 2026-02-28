import aiosqlite

from .constants import DB_PATH


async def _get_existing_columns(db: aiosqlite.Connection, table: str) -> set[str]:
    async with db.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    return {str(row[1]) for row in rows}


async def _ensure_item_columns(db: aiosqlite.Connection) -> None:
    existing_columns = await _get_existing_columns(db, "items")
    expected_columns = {
        "arrival_date": "TEXT",
        "recipient": "TEXT",
        "distribution_date": "TEXT",
        "signoff_note": "TEXT",
    }
    for column_name, column_type in expected_columns.items():
        if column_name in existing_columns:
            continue
        await db.execute(f"ALTER TABLE items ADD COLUMN {column_name} {column_type}")


async def _migrate_legacy_statuses(db: aiosqlite.Connection) -> None:
    # 兼容历史状态命名，迁移到新的执行流状态。
    await db.execute("UPDATE items SET status = '已下单' WHERE status = '已采购'")
    await db.execute("UPDATE items SET status = '待分发' WHERE status = '已到货'")
    await db.execute("UPDATE items SET status = '已分发' WHERE status = '已发放'")


async def init_db():
    """初始化数据库表。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
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
                arrival_date TEXT,
                recipient TEXT,
                distribution_date TEXT,
                signoff_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_number, item_name, handler)
            )
            """
        )
        await _ensure_item_columns(db)
        await _migrate_legacy_statuses(db)
        await db.execute(
            """
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
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_department ON items(department)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_request_date ON items(request_date)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_serial_number ON items(serial_number)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_items_handler ON items(handler)"
        )
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
