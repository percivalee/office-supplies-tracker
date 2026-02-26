from typing import Optional


def escape_like_pattern(value: str) -> str:
    """转义 LIKE 特殊字符，避免输入中的 %/_ 被当作通配符。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_item_filters(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None
) -> tuple[list[str], list]:
    """构建物品筛选条件与参数。"""
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
        pattern = f"%{escape_like_pattern(keyword)}%"
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


def build_history_filters(
    action: str | None = None,
    keyword: str | None = None,
    month: str | None = None
) -> tuple[list[str], list]:
    """构建历史记录筛选条件与参数。"""
    conditions = []
    params = []

    if action:
        conditions.append("action = ?")
        params.append(action)
    if month:
        conditions.append("created_at LIKE ?")
        params.append(f"{month}%")
    if keyword:
        pattern = f"%{escape_like_pattern(keyword)}%"
        conditions.append(
            "("
            "serial_number LIKE ? ESCAPE '\\' OR "
            "item_name LIKE ? ESCAPE '\\' OR "
            "handler LIKE ? ESCAPE '\\' OR "
            "department LIKE ? ESCAPE '\\' OR "
            "changed_fields LIKE ? ESCAPE '\\'"
            ")"
        )
        params.extend([pattern, pattern, pattern, pattern, pattern])

    return conditions, params
