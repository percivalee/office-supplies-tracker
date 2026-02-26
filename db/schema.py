import aiosqlite

from .constants import DB_PATH


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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(serial_number, item_name, handler)
            )
            """
        )
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
