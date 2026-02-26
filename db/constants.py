from enum import Enum

DB_PATH = "office_supplies.db"

ALLOWED_COLUMNS = frozenset({
    "serial_number", "department", "handler", "request_date",
    "item_name", "quantity", "purchase_link", "unit_price",
    "status", "invoice_issued", "payment_status",
})

ITEM_COLUMNS = (
    "id", "serial_number", "department", "handler", "request_date",
    "item_name", "quantity", "purchase_link", "unit_price", "status",
    "invoice_issued", "payment_status", "created_at", "updated_at",
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
