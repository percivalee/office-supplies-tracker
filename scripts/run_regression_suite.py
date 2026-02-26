#!/usr/bin/env python3
"""Parse regression suite for document extraction quality."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_SUITE = Path("samples/regression/cases.json")
DEFAULT_REPORT = Path("samples/regression/last_report.json")


@dataclass
class CaseResult:
    case_id: str
    category: str
    file: str
    passed: bool
    issues: list[str]
    parsed: dict[str, Any] | None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _load_suite(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"回归用例不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        return data["cases"]
    raise ValueError("用例格式错误，应为列表或包含 cases 列表的对象")


def _get_item_names(parsed: dict[str, Any]) -> list[str]:
    items = parsed.get("items") or []
    names = []
    for item in items:
        names.append(str((item or {}).get("item_name") or "").strip())
    return [name for name in names if name]


def _evaluate_case(case: dict[str, Any], root: Path) -> CaseResult:
    case_id = str(case.get("id") or "unknown")
    category = str(case.get("category") or "")
    file_rel = str(case.get("file") or "")
    case_file = (root / file_rel).resolve()
    issues: list[str] = []
    parsed: dict[str, Any] | None = None

    if not file_rel:
        issues.append("missing:file")
        return CaseResult(case_id, category, file_rel, False, issues, parsed)
    if not case_file.exists():
        issues.append("missing:file_not_found")
        return CaseResult(case_id, category, file_rel, False, issues, parsed)

    try:
        from parser import parse_document
        parsed = parse_document(str(case_file))
    except Exception:
        issues.append("parse:exception")
        issues.append(traceback.format_exc(limit=1).strip().replace("\n", " | "))
        return CaseResult(case_id, category, file_rel, False, issues, parsed)

    expect = case.get("expect") or {}
    required_headers = expect.get("headers_required") or []
    min_items = int(expect.get("min_items") or 0)
    max_items = expect.get("max_items")
    must_item_keywords = expect.get("must_contain_item_names") or []
    exact_headers = expect.get("exact_headers") or {}
    min_link_count = int(expect.get("min_link_count") or 0)

    for field in required_headers:
        value = str(parsed.get(field) or "").strip()
        if not value:
            issues.append(f"header:missing:{field}")

    for field, expected in exact_headers.items():
        if _normalize_text(parsed.get(field)) != _normalize_text(expected):
            issues.append(f"header:mismatch:{field}")

    items = parsed.get("items") or []
    item_count = len(items)
    if min_items and item_count < min_items:
        issues.append(f"items:lt_min:{min_items}")
    if max_items is not None and item_count > int(max_items):
        issues.append(f"items:gt_max:{max_items}")

    item_names = _get_item_names(parsed)
    for keyword in must_item_keywords:
        kw = _normalize_text(keyword)
        if not any(kw in _normalize_text(name) for name in item_names):
            issues.append(f"items:keyword_missing:{keyword}")

    if min_link_count:
        link_count = 0
        for item in items:
            link = str((item or {}).get("purchase_link") or "").strip()
            if link:
                link_count += 1
        if link_count < min_link_count:
            issues.append(f"items:link_lt_min:{min_link_count}")

    return CaseResult(case_id, category, file_rel, not issues, issues, parsed)


def run_suite(suite_path: Path, save_report: Path | None = None) -> int:
    try:
        import pdfplumber  # noqa: F401
    except ModuleNotFoundError:
        print("缺少依赖：pdfplumber。请先安装 requirements.txt 后再执行回归。")
        return 2

    root = Path.cwd()
    cases = _load_suite(suite_path)
    if not cases:
        print("回归套件为空，没有可执行用例。")
        return 0

    results: list[CaseResult] = []
    issue_counter = Counter()

    for case in cases:
        result = _evaluate_case(case, root)
        results.append(result)
        for issue in result.issues:
            if ":" in issue:
                issue_counter[issue] += 1

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.case_id} ({result.category}) -> {result.file}")
        if result.issues:
            for issue in result.issues:
                print(f"  - {issue}")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    print("")
    print(f"Summary: total={total}, passed={passed}, failed={failed}")

    if issue_counter:
        print("Top Issues:")
        for issue, count in issue_counter.most_common(10):
            print(f"  - {issue}: {count}")

    if save_report:
        report = {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
            },
            "issues": dict(issue_counter),
            "results": [
                {
                    "case_id": r.case_id,
                    "category": r.category,
                    "file": r.file,
                    "passed": r.passed,
                    "issues": r.issues,
                    "parsed": r.parsed,
                }
                for r in results
            ],
        }
        save_report.parent.mkdir(parents=True, exist_ok=True)
        save_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report: {save_report}")

    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parser regression suite")
    parser.add_argument(
        "--suite",
        type=Path,
        default=DEFAULT_SUITE,
        help=f"回归用例 JSON 路径（默认: {DEFAULT_SUITE}）",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"报告输出路径（默认: {DEFAULT_REPORT}）",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="不写报告文件",
    )
    args = parser.parse_args()

    report_path = None if args.no_report else args.report
    raise SystemExit(run_suite(args.suite, report_path))


if __name__ == "__main__":
    main()
