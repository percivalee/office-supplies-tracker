from enum import Enum
from app_runtime import DATA_DIR

# 使用可写数据目录（安装到 Program Files 时自动回退到 APPDATA）。
DB_PATH = str((DATA_DIR / "office_supplies.db").resolve())

ALLOWED_COLUMNS = frozenset({
    "serial_number", "department", "handler", "request_date",
    "item_name", "quantity", "purchase_link", "unit_price",
    "status", "invoice_issued", "payment_status",
    "arrival_date", "distribution_date", "signoff_note",
})

ITEM_COLUMNS = (
    "id", "serial_number", "department", "handler", "request_date",
    "item_name", "quantity", "purchase_link", "unit_price", "status",
    "invoice_issued", "payment_status",
    "arrival_date", "distribution_date", "signoff_note",
    "deleted_at",
    "created_at", "updated_at",
)


class PaymentStatus(str, Enum):
    UNPAID = "未付款"
    PAID = "已付款"
    REIMBURSED = "已报销"


class ItemStatus(str, Enum):
    PENDING = "待采购"
    PENDING_ARRIVAL = "待到货"
    PENDING_DISTRIBUTION = "待分发"
    DISTRIBUTED = "已分发"


EXECUTION_BOARD_COLUMNS = (
    ("pending_purchase", ItemStatus.PENDING.value),
    ("pending_arrival", ItemStatus.PENDING_ARRIVAL.value),
    ("pending_distribution", ItemStatus.PENDING_DISTRIBUTION.value),
)
