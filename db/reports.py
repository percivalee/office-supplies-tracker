from typing import Optional

import aiosqlite

from .constants import DB_PATH
from .filters import build_item_filters


async def get_stats_summary() -> dict:
    """获取统计信息（SQL 聚合）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN invoice_issued = 1 THEN 1 ELSE 0 END) AS issued,
                SUM(CASE WHEN invoice_issued = 1 THEN 0 ELSE 1 END) AS not_issued
            FROM items
            """
        ) as cursor:
            row = await cursor.fetchone()
            total = int(row[0] if row and row[0] is not None else 0)
            issued = int(row[1] if row and row[1] is not None else 0)
            not_issued = int(row[2] if row and row[2] is not None else 0)

        async with db.execute(
            "SELECT status, COUNT(*) FROM items GROUP BY status"
        ) as cursor:
            status_rows = await cursor.fetchall()
            status_count = {str(status): int(count) for status, count in status_rows}

        async with db.execute(
            "SELECT payment_status, COUNT(*) FROM items GROUP BY payment_status"
        ) as cursor:
            payment_rows = await cursor.fetchall()
            payment_count = {str(status): int(count) for status, count in payment_rows}

    return {
        "total": total,
        "status_count": status_count,
        "payment_count": payment_count,
        "invoice_count": {
            "issued": issued,
            "not_issued": not_issued,
        },
    }


async def get_amount_report(
    status: Optional[str] = None,
    department: Optional[str] = None,
    month: Optional[str] = None,
    keyword: Optional[str] = None
) -> dict:
    """金额统计报表。"""
    conditions, params = build_item_filters(
        status=status, department=department, month=month, keyword=keyword
    )
    where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        summary_query = f"""
            SELECT
                COUNT(*) AS total_records,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount,
                COALESCE(SUM(CASE WHEN unit_price IS NOT NULL THEN quantity * unit_price ELSE 0 END), 0) AS priced_amount,
                SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END) AS missing_price_records
            FROM items
            {where_clause}
        """
        async with db.execute(summary_query, params) as cursor:
            row = await cursor.fetchone()
            summary = dict(row) if row else {}

        department_query = f"""
            SELECT
                department,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount,
                SUM(CASE WHEN unit_price IS NULL THEN 1 ELSE 0 END) AS missing_price_records
            FROM items
            {where_clause}
            GROUP BY department
            ORDER BY total_amount DESC, record_count DESC
            LIMIT 30
        """
        async with db.execute(department_query, params) as cursor:
            by_department = [dict(row) for row in await cursor.fetchall()]

        status_query = f"""
            SELECT
                status,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount
            FROM items
            {where_clause}
            GROUP BY status
            ORDER BY total_amount DESC, record_count DESC
        """
        async with db.execute(status_query, params) as cursor:
            by_status = [dict(row) for row in await cursor.fetchall()]

        month_conditions = list(conditions)
        month_params = list(params)
        month_conditions.append("request_date IS NOT NULL")
        month_conditions.append("request_date <> ''")
        month_where = f" WHERE {' AND '.join(month_conditions)}"

        month_query = f"""
            SELECT
                SUBSTR(request_date, 1, 7) AS month,
                COUNT(*) AS record_count,
                COALESCE(SUM(quantity * COALESCE(unit_price, 0)), 0) AS total_amount
            FROM items
            {month_where}
            GROUP BY month
            HAVING month IS NOT NULL AND month <> ''
            ORDER BY month DESC
            LIMIT 12
        """
        async with db.execute(month_query, month_params) as cursor:
            by_month = [dict(row) for row in await cursor.fetchall()]

    return {
        "summary": {
            "total_records": int(summary.get("total_records") or 0),
            "total_amount": float(summary.get("total_amount") or 0),
            "priced_amount": float(summary.get("priced_amount") or 0),
            "missing_price_records": int(summary.get("missing_price_records") or 0),
        },
        "by_department": [
            {
                "department": row.get("department") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
                "missing_price_records": int(row.get("missing_price_records") or 0),
            }
            for row in by_department
        ],
        "by_status": [
            {
                "status": row.get("status") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
            }
            for row in by_status
        ],
        "by_month": [
            {
                "month": row.get("month") or "",
                "record_count": int(row.get("record_count") or 0),
                "total_amount": float(row.get("total_amount") or 0),
            }
            for row in by_month
        ],
    }
