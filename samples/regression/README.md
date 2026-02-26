# 回归样本说明

本目录用于放置解析回归样本和用例配置。

## 目录建议

- `pdf_text/`: 可复制文本的 PDF（矢量 PDF）
- `pdf_scan/`: 扫描版 PDF（图片型 PDF）
- `image/`: 图片单据（png/jpg/jpeg）

## 用例文件

编辑 `samples/regression/cases.json`，示例：

```json
{
  "cases": [
    {
      "id": "pdf_text_001",
      "category": "pdf_text",
      "file": "samples/regression/pdf_text/example.pdf",
      "expect": {
        "headers_required": ["serial_number", "department", "handler", "request_date"],
        "min_items": 1,
        "must_contain_item_names": ["签字笔"]
      }
    },
    {
      "id": "pdf_scan_001",
      "category": "pdf_scan",
      "file": "samples/regression/pdf_scan/example.pdf",
      "expect": {
        "headers_required": ["department", "handler"],
        "min_items": 1
      }
    }
  ]
}
```

## 执行

```bash
python3 scripts/run_regression_suite.py
```

默认会输出报告到 `samples/regression/last_report.json`。
