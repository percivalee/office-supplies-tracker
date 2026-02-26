from typing import Optional

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    serial_number: str
    department: str
    handler: str
    request_date: str
    item_name: str
    quantity: float = Field(gt=0)
    purchase_link: Optional[str] = None
    unit_price: Optional[float] = Field(default=None, ge=0)
    status: str = "待采购"
    invoice_issued: bool = False
    payment_status: str = "未付款"


class ItemUpdate(BaseModel):
    serial_number: Optional[str] = None
    department: Optional[str] = None
    handler: Optional[str] = None
    request_date: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = Field(default=None, gt=0)
    purchase_link: Optional[str] = None
    unit_price: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = None
    invoice_issued: Optional[bool] = None
    payment_status: Optional[str] = None


class ImportItem(BaseModel):
    item_name: str = ""
    quantity: Optional[float] = None
    purchase_link: Optional[str] = None


class ImportConfirmRequest(BaseModel):
    serial_number: str = ""
    department: str = ""
    handler: str = ""
    request_date: str = ""
    items: list[ImportItem] = Field(default_factory=list)
    duplicate_action: Optional[str] = None


class DuplicateHandleRequest(BaseModel):
    """处理重复物品的请求。"""
    action: str  # 'skip', 'add', 'merge'
    duplicates: list[dict]
    items_data: list[dict]
