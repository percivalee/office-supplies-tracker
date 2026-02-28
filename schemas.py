from typing import Literal, Optional

from pydantic import BaseModel, Field

from db.constants import ItemStatus, PaymentStatus


class ItemCreate(BaseModel):
    serial_number: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    handler: str = Field(min_length=1, max_length=80)
    request_date: str = Field(min_length=1, max_length=32)
    item_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0)
    purchase_link: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Optional[float] = Field(default=None, ge=0)
    status: ItemStatus = Field(default=ItemStatus.PENDING)
    invoice_issued: bool = False
    payment_status: PaymentStatus = Field(default=PaymentStatus.UNPAID)
    arrival_date: Optional[str] = Field(default=None, max_length=32)
    recipient: Optional[str] = Field(default=None, max_length=120)
    distribution_date: Optional[str] = Field(default=None, max_length=32)
    signoff_note: Optional[str] = Field(default=None, max_length=500)


class ItemUpdate(BaseModel):
    serial_number: Optional[str] = Field(default=None, min_length=1, max_length=120)
    department: Optional[str] = Field(default=None, min_length=1, max_length=120)
    handler: Optional[str] = Field(default=None, min_length=1, max_length=80)
    request_date: Optional[str] = Field(default=None, min_length=1, max_length=32)
    item_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    quantity: Optional[float] = Field(default=None, gt=0)
    purchase_link: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Optional[float] = Field(default=None, ge=0)
    status: Optional[ItemStatus] = None
    invoice_issued: Optional[bool] = None
    payment_status: Optional[PaymentStatus] = None
    arrival_date: Optional[str] = Field(default=None, max_length=32)
    recipient: Optional[str] = Field(default=None, max_length=120)
    distribution_date: Optional[str] = Field(default=None, max_length=32)
    signoff_note: Optional[str] = Field(default=None, max_length=500)


class ImportItem(BaseModel):
    item_name: str = Field(default="", max_length=200)
    quantity: Optional[float] = None
    purchase_link: Optional[str] = Field(default=None, max_length=2000)


class ImportConfirmRequest(BaseModel):
    serial_number: str = Field(default="", max_length=120)
    department: str = Field(default="", max_length=120)
    handler: str = Field(default="", max_length=80)
    request_date: str = Field(default="", max_length=32)
    items: list[ImportItem] = Field(default_factory=list)
    duplicate_action: Optional[Literal["skip", "add", "merge"]] = None


class DuplicateHandleRequest(BaseModel):
    """处理重复物品的请求。"""
    action: Literal["skip", "add", "merge"]
    duplicates: list[dict]
    items_data: list[dict]


class BatchUpdateRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    updates: dict


class WebDAVConfigRequest(BaseModel):
    base_url: str = Field(min_length=1, max_length=300)
    username: str = Field(default="", max_length=200)
    password: str = Field(default="", max_length=200)
    remote_dir: str = Field(default="", max_length=300)


class WebDAVRestoreRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
