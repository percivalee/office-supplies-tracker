from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import aiosqlite
import shutil
import os
import re
from pathlib import Path
from io import BytesIO
from datetime import datetime

from database import (
    init_db, get_items, get_item, create_item, update_item, delete_item,
    batch_create_items, get_serial_numbers, get_departments, get_handlers,
    ItemStatus, PaymentStatus
)
from parser import parse_document


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库"""
    await init_db()
    yield


app = FastAPI(title="办公用品采购追踪系统", lifespan=lifespan)

# 创建上传目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")


def _item_key(item: dict) -> tuple[str, str, str]:
    """构造判重键：流水号 + 物品名称 + 经办人。"""
    return (
        str(item.get("serial_number") or "").strip(),
        str(item.get("item_name") or "").strip(),
        str(item.get("handler") or "").strip(),
    )


def _safe_quantity(value) -> float:
    """数量兜底，避免异常值导致合并失败。"""
    try:
        qty = float(value)
        return qty if qty > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def _normalize_month(month: Optional[str]) -> Optional[str]:
    """校验月份参数，格式为 YYYY-MM。"""
    if month is None:
        return None
    month = month.strip()
    if not month:
        return None
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=400, detail="month 参数格式应为 YYYY-MM")
    return month


def _normalize_text_filter(value: Optional[str]) -> Optional[str]:
    """将空白筛选值归一化为 None。"""
    if value is None:
        return None
    value = value.strip()
    return value or None


# Pydantic 模型
class ItemCreate(BaseModel):
    serial_number: str
    department: str
    handler: str
    request_date: str
    item_name: str
    quantity: float
    purchase_link: Optional[str] = None
    unit_price: Optional[float] = None
    status: str = "待采购"
    invoice_issued: bool = False
    payment_status: str = "未付款"


class ItemUpdate(BaseModel):
    serial_number: Optional[str] = None
    department: Optional[str] = None
    handler: Optional[str] = None
    request_date: Optional[str] = None
    item_name: Optional[str] = None
    quantity: Optional[float] = None
    purchase_link: Optional[str] = None
    unit_price: Optional[float] = None
    status: Optional[str] = None
    invoice_issued: Optional[bool] = None
    payment_status: Optional[str] = None


class ParseResult(BaseModel):
    serial_number: str
    department: str
    handler: str
    request_date: str
    items: list[dict]


@app.get("/", response_class=HTMLResponse)
async def root():
    """返回主页"""
    html_path = Path(__file__).parent / "static" / "index.html"
    return FileResponse(html_path)


@app.get("/api/items")
async def list_items(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None
):
    """获取所有物品列表"""
    status = _normalize_text_filter(status)
    department = _normalize_text_filter(department)
    month = _normalize_month(month)
    items = await get_items(status=status, department=department, month=month)
    return {"items": items}


@app.get("/api/export")
async def export_items(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None
):
    """导出筛选后的记录为 Excel"""
    status = _normalize_text_filter(status)
    department = _normalize_text_filter(department)
    month = _normalize_month(month)
    items = await get_items(status=status, department=department, month=month)

    try:
        from openpyxl import Workbook
        from openpyxl.utils import get_column_letter
    except ModuleNotFoundError:
        raise HTTPException(status_code=500, detail="缺少 openpyxl 依赖，请先安装 requirements.txt")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "采购记录"

    headers = ["流水号", "申领日期", "申领部门", "经办人", "物品名称", "数量", "单价", "状态"]
    sheet.append(headers)

    for item in items:
        sheet.append([
            item.get("serial_number", ""),
            item.get("request_date", ""),
            item.get("department", ""),
            item.get("handler", ""),
            item.get("item_name", ""),
            item.get("quantity", ""),
            "" if item.get("unit_price") is None else item.get("unit_price"),
            item.get("status", ""),
        ])

    column_widths = [18, 12, 24, 12, 28, 10, 10, 12]
    for idx, width in enumerate(column_widths, start=1):
        sheet.column_dimensions[get_column_letter(idx)].width = width

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    filename = f"office_supplies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/items/{item_id}")
async def read_item(item_id: int):
    """获取单个物品详情"""
    item = await get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="物品不存在")
    return item


@app.post("/api/items")
async def create_new_item(item: ItemCreate):
    """手动创建新物品记录"""
    try:
        item_id = await create_item(item.model_dump())
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=409, detail="记录已存在（流水号+物品名称+经办人）")
    return {"id": item_id, "message": "创建成功"}


@app.put("/api/items/{item_id}")
async def update_item_endpoint(item_id: int, updates: ItemUpdate):
    """更新物品记录"""
    update_data = updates.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="未提供可更新字段")
    try:
        success = await update_item(item_id, update_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="物品不存在")
    return {"message": "更新成功"}


@app.delete("/api/items/{item_id}")
async def delete_item_endpoint(item_id: int):
    """删除物品记录"""
    success = await delete_item(item_id)
    if not success:
        raise HTTPException(status_code=404, detail="物品不存在")
    return {"message": "删除成功"}


@app.post("/api/upload")
async def upload_and_parse(file: UploadFile = File(...)):
    """上传文件并解析"""
    # 校验并净化文件名，防止路径穿越
    if not file.filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    safe_filename = Path(file.filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="无效的文件名")

    # 保存文件
    file_path = UPLOAD_DIR / safe_filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 解析文档
        result = parse_document(str(file_path))

        # 构建待插入的记录
        items_to_create = []
        for item in result.get("items", []):
            items_to_create.append({
                "serial_number": result.get("serial_number", ""),
                "department": result.get("department", ""),
                "handler": result.get("handler", ""),
                "request_date": result.get("request_date", ""),
                "item_name": item.get("item_name", ""),
                "quantity": item.get("quantity", 1),
                "purchase_link": item.get("purchase_link"),
            })

        # 检查重复物品（按流水号+物品名称+经办人）
        duplicates = []

        existing_items = await get_items()
        existing_by_key = {_item_key(item): item for item in existing_items}

        for item in items_to_create:
            key = _item_key(item)
            if key in existing_by_key:
                existing = existing_by_key[key]
                duplicates.append({
                    "serial_number": item["serial_number"],
                    "item_name": item["item_name"],
                    "handler": item["handler"],
                    "existing_quantity": existing["quantity"],
                    "new_quantity": item["quantity"],
                    "department": item["department"],
                    "existing_id": existing["id"]
                })

        # 如果有重复，返回重复信息（先清理临时文件）
        if duplicates:
            os.remove(file_path)
            return {
                "message": f"检测到 {len(duplicates)} 个重复物品",
                "parsed_data": result,
                "duplicates": duplicates,
                "has_duplicates": True
            }

        # 没有重复，直接插入
        created_ids = await batch_create_items(items_to_create)

        # 删除临时文件
        os.remove(file_path)

        return {
            "message": f"成功解析并创建 {len(created_ids)} 条记录",
            "parsed_data": result,
            "created_count": len(created_ids),
            "created_ids": created_ids,
            "has_duplicates": False
        }

    except Exception as e:
        # 清理文件
        if file_path.exists():
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@app.get("/api/autocomplete")
async def autocomplete():
    """获取自动补全数据"""
    return {
        "serial_numbers": await get_serial_numbers(),
        "departments": await get_departments(),
        "handlers": await get_handlers(),
        "statuses": [s.value for s in ItemStatus],
        "payment_statuses": [s.value for s in PaymentStatus]
    }


@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    items = await get_items()

    total = len(items)
    status_count = {}
    payment_count = {}
    invoice_count = {"issued": 0, "not_issued": 0}

    for item in items:
        # 状态统计
        status = item.get("status", "待采购")
        status_count[status] = status_count.get(status, 0) + 1

        # 付款状态统计
        payment = item.get("payment_status", "未付款")
        payment_count[payment] = payment_count.get(payment, 0) + 1

        # 发票统计
        if item.get("invoice_issued"):
            invoice_count["issued"] += 1
        else:
            invoice_count["not_issued"] += 1

    return {
        "total": total,
        "status_count": status_count,
        "payment_count": payment_count,
        "invoice_count": invoice_count
    }


class DuplicateHandleRequest(BaseModel):
    """处理重复物品的请求"""
    action: str  # 'skip', 'add', 'merge'
    duplicates: list[dict]
    items_data: list[dict]  # 所有待插入的数据


@app.post("/api/upload/handle-duplicates")
async def handle_duplicates(request: DuplicateHandleRequest):
    """处理重复物品"""
    try:
        if request.action not in {"skip", "add", "merge"}:
            raise HTTPException(status_code=400, detail="不支持的操作类型")

        items_to_create = []
        quantity_updates = {}  # item_id -> merged quantity

        # 获取现有物品
        all_items = await get_items()
        existing_by_key = {_item_key(item): item for item in all_items}

        # 重复标记优先按完整键匹配；兼容旧前端仅传 item_name 的情况
        duplicate_keys = {
            _item_key(dup)
            for dup in request.duplicates
            if dup.get("serial_number") is not None and dup.get("handler") is not None
        }
        duplicate_names = {
            str(dup.get("item_name") or "").strip()
            for dup in request.duplicates
            if dup.get("item_name")
        }

        for item in request.items_data:
            item_key = _item_key(item)
            item_name = item_key[1]
            qty = _safe_quantity(item.get("quantity"))
            is_duplicate = item_key in duplicate_keys or item_name in duplicate_names

            if request.action == "skip":
                # 跳过重复物品
                if not is_duplicate:
                    item["quantity"] = qty
                    items_to_create.append(item)
            elif request.action == "add":
                # 全部新增
                item["quantity"] = qty
                items_to_create.append(item)
            elif request.action == "merge":
                # 合并：重复的更新数量，不重复的新增
                if item_key in existing_by_key:
                    existing = existing_by_key[item_key]
                    existing_id = existing["id"]
                    base_qty = quantity_updates.get(existing_id, _safe_quantity(existing["quantity"]))
                    quantity_updates[existing_id] = base_qty + qty
                else:
                    item["quantity"] = qty
                    items_to_create.append(item)

        # 批量创建新记录
        created_ids = []
        if items_to_create:
            created_ids = await batch_create_items(items_to_create)

        # 执行更新操作（合并）
        for item_id, quantity in quantity_updates.items():
            await update_item(item_id, {"quantity": quantity})

        return {
            "message": f"新增 {len(created_ids)} 条，更新 {len(quantity_updates)} 条",
            "parsed_data": {"items": items_to_create},
            "created_count": len(created_ids),
            "updated_count": len(quantity_updates)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
