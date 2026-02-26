from typing import Optional

from fastapi import HTTPException

from database import (
    batch_create_items,
    bulk_update_quantities,
    get_existing_items_by_keys,
)


def item_key(item: dict) -> tuple[str, str, str]:
    """构造判重键：流水号 + 物品名称 + 经办人。"""
    return (
        str(item.get("serial_number") or "").strip(),
        str(item.get("item_name") or "").strip(),
        str(item.get("handler") or "").strip(),
    )


def safe_quantity(value) -> float:
    """数量兜底，避免异常值导致合并失败。"""
    try:
        quantity = float(value)
        return quantity if quantity > 0 else 1.0
    except (TypeError, ValueError):
        return 1.0


def normalize_import_payload(payload: dict) -> dict:
    """标准化导入数据，合并同键明细并清理空值。"""
    serial_number = str(payload.get("serial_number") or "").strip()
    department = str(payload.get("department") or "").strip()
    handler = str(payload.get("handler") or "").strip()
    request_date = str(payload.get("request_date") or "").strip()

    merged_items: dict[tuple[str, str, str], dict] = {}
    for raw in payload.get("items", []):
        item_name = str((raw or {}).get("item_name") or "").strip()
        if not item_name:
            continue
        key = (serial_number, item_name, handler)
        quantity = safe_quantity((raw or {}).get("quantity"))
        purchase_link_raw = str((raw or {}).get("purchase_link") or "").strip()
        purchase_link = purchase_link_raw or None

        if key in merged_items:
            merged_items[key]["quantity"] += quantity
            if not merged_items[key].get("purchase_link") and purchase_link:
                merged_items[key]["purchase_link"] = purchase_link
            continue

        merged_items[key] = {
            "serial_number": serial_number,
            "department": department,
            "handler": handler,
            "request_date": request_date,
            "item_name": item_name,
            "quantity": quantity,
            "purchase_link": purchase_link,
        }

    return {
        "serial_number": serial_number,
        "department": department,
        "handler": handler,
        "request_date": request_date,
        "items": list(merged_items.values()),
    }


def build_preview_data(normalized_payload: dict, items: list[dict]) -> dict:
    """构造可回显到前端的预览数据。"""
    return {
        "serial_number": normalized_payload.get("serial_number", ""),
        "department": normalized_payload.get("department", ""),
        "handler": normalized_payload.get("handler", ""),
        "request_date": normalized_payload.get("request_date", ""),
        "items": [
            {
                "item_name": item.get("item_name", ""),
                "quantity": safe_quantity(item.get("quantity")),
                "purchase_link": item.get("purchase_link"),
            }
            for item in items
        ],
    }


def collect_duplicates(items: list[dict], existing_by_key: dict) -> list[dict]:
    """收集与数据库已存在记录冲突的明细。"""
    duplicates: list[dict] = []
    for item in items:
        key = item_key(item)
        existing = existing_by_key.get(key)
        if not existing:
            continue
        duplicates.append({
            "serial_number": item["serial_number"],
            "item_name": item["item_name"],
            "handler": item["handler"],
            "existing_quantity": existing["quantity"],
            "new_quantity": item["quantity"],
            "department": item["department"],
            "existing_id": existing["id"],
        })
    return duplicates


async def confirm_import_payload(normalized_payload: dict, duplicate_action: Optional[str] = None) -> dict:
    """根据导入数据执行确认导入流程。"""
    items_to_create = normalized_payload.get("items", [])
    if not items_to_create:
        raise HTTPException(status_code=400, detail="未识别到可导入的物品明细")

    if duplicate_action is not None and duplicate_action not in {"skip", "add", "merge"}:
        raise HTTPException(status_code=400, detail="不支持的操作类型")

    existing_by_key = await get_existing_items_by_keys(
        [item_key(item) for item in items_to_create]
    )
    duplicates = collect_duplicates(items_to_create, existing_by_key)
    preview_data = build_preview_data(normalized_payload, items_to_create)

    if duplicates and duplicate_action is None:
        return {
            "message": f"检测到 {len(duplicates)} 个重复物品，请选择处理方式",
            "has_duplicates": True,
            "duplicates": duplicates,
            "parsed_data": preview_data,
        }

    action = duplicate_action or "add"
    created_ids: list[int] = []
    updated_count = 0
    to_insert: list[dict] = []

    if action == "skip":
        to_insert = [item for item in items_to_create if item_key(item) not in existing_by_key]
        if to_insert:
            created_ids = await batch_create_items(to_insert)
    elif action == "add":
        to_insert = list(items_to_create)
        created_ids = await batch_create_items(to_insert)
    elif action == "merge":
        quantity_updates: dict[int, float] = {}
        for item in items_to_create:
            key = item_key(item)
            quantity = safe_quantity(item.get("quantity"))
            existing = existing_by_key.get(key)
            if existing:
                existing_id = existing["id"]
                base_qty = quantity_updates.get(existing_id, safe_quantity(existing["quantity"]))
                quantity_updates[existing_id] = base_qty + quantity
            else:
                new_item = dict(item)
                new_item["quantity"] = quantity
                to_insert.append(new_item)

        if to_insert:
            created_ids = await batch_create_items(to_insert)
        updated_count = await bulk_update_quantities(quantity_updates)

    return {
        "message": f"导入完成：新增 {len(created_ids)} 条，更新 {updated_count} 条",
        "has_duplicates": False,
        "parsed_data": preview_data,
        "created_count": len(created_ids),
        "created_ids": created_ids,
        "updated_count": updated_count,
    }
