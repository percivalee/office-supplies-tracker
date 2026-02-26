# 办公用品采购自动解析与追踪系统

用于内部办公用品采购管理的单用户工具。支持上传领用单（PDF/图片）自动识别，在线维护采购流程，并可按条件筛选与导出 Excel。

## 核心功能

- 自动解析领用单：提取流水号、申领部门、经办人、申领日期、物品明细
- 导入预览与人工校正：上传后先预览，支持逐项修改后再确认入库
- PDF + 图片识别：PDF 优先表格提取，图片使用 OCR 兜底
- 申领部门精准解析：优先顶部“申领部门”字段，规避“部门领导意见/管理员意见”干扰
- 重复物品处理：检测 `(流水号 + 物品名称 + 经办人)`，支持跳过/新增/合并数量
- 一键备份/恢复：可下载当前数据库+上传文件备份，并一键恢复
- 采购记录在线编辑：字段直接修改并保存
- 关键字模糊搜索：支持流水号、物品名、经办人、申领部门
- 高级筛选：按状态、申领部门、月份（`YYYY-MM`）筛选
- 服务端分页：支持页码切换、每页条数切换、页码跳转
- Excel 导出：按当前筛选导出 `.xlsx`
- 统计面板：总数、待采购、发票、报销等统计
- 金额统计报表：基于当前筛选汇总总金额，并按部门/状态/月份统计
- 变更历史：自动记录新增/编辑/删除，支持按关键词/操作/月份检索

## 技术栈

- 后端：FastAPI + SQLite + aiosqlite
- 文档解析：pdfplumber + PaddleOCR
- 前端：Vue 3 + TailwindCSS + Axios
- 导出：openpyxl

## 安装与启动

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动服务

```bash
./start.sh
```

或手动启动：

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 访问系统

打开：`http://localhost:8000`

## 桌面版运行（无需打包）

```bash
source venv/bin/activate
python desktop.py
```

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 前端页面 |
| GET | `/api/items` | 列表查询（支持 `keyword`/`status`/`department`/`month`/`page`/`page_size`） |
| GET | `/api/items/{id}` | 获取单条记录 |
| POST | `/api/items` | 手动新增 |
| PUT | `/api/items/{id}` | 更新记录 |
| DELETE | `/api/items/{id}` | 删除记录 |
| POST | `/api/upload` | 上传并解析领用单 |
| POST | `/api/import/confirm` | 确认导入（支持人工校正与重复处理） |
| POST | `/api/upload/handle-duplicates` | 处理重复物品 |
| GET | `/api/stats` | 获取统计数据 |
| GET | `/api/reports/amount` | 金额统计报表（支持与列表一致的筛选参数） |
| GET | `/api/history` | 变更历史列表（`action`/`keyword`/`month`/`page`/`page_size`） |
| GET | `/api/autocomplete` | 获取部门/经办人/状态候选 |
| GET | `/api/export` | 导出 Excel（支持与列表一致的筛选参数，含 `keyword`） |
| GET | `/api/backup` | 下载数据备份（数据库+上传文件） |
| POST | `/api/restore` | 上传备份包并恢复数据 |

## 关键参数说明

- `month`：必须是 `YYYY-MM`，例如 `2026-02`
- `keyword`：模糊搜索关键词（会匹配流水号、物品名、经办人、申领部门）
- `action`：历史操作类型，仅支持 `create` / `update` / `delete`
- `page`：页码，从 `1` 开始
- `page_size`：每页条数，范围 `1-200`

## 数据字段

| 字段 | 类型 | 说明 |
|---|---|---|
| serial_number | TEXT | 流水号 |
| department | TEXT | 申领部门 |
| handler | TEXT | 经办人 |
| request_date | TEXT | 申领日期（`YYYY-MM-DD`） |
| item_name | TEXT | 物品名称 |
| quantity | REAL | 数量 |
| purchase_link | TEXT | 购买链接 |
| unit_price | REAL | 单价 |
| status | TEXT | 待采购/已采购/已到货/已发放 |
| invoice_issued | BOOLEAN | 是否开票 |
| payment_status | TEXT | 未付款/已付款/已报销 |

变更历史保存在 `item_history` 表，记录每次新增/更新/删除的前后快照与变更字段。

## 目录结构

```text
office-supplies-tracker/
├── main.py
├── database.py
├── import_flow.py
├── schemas.py
├── parser.py
├── static/
│   ├── index.html
│   ├── app.css
│   └── app.js
├── requirements.txt
├── start.sh
├── README.md
└── USAGE.md
```

## 使用建议

- 优先上传 PDF，识别稳定性最佳
- 图片上传建议使用高清截图，避免带审批系统按钮区域
- 解析后请抽样核对关键字段（部门、日期、数量）
- 数据库文件 `office_supplies.db` 默认在项目根目录（已被 `.gitignore` 忽略）
