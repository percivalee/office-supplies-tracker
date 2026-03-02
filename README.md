# 办公用品采购自动解析与追踪系统

用于内部办公用品采购管理的单用户工具。支持上传领用单（PDF/图片）自动识别，在线维护采购流程，并可按条件筛选与导出 Excel。

## 核心功能

- 自动解析领用单：提取流水号、申领部门、经办人、申领日期、物品明细
- 导入预览与人工校正：上传后先预览，支持逐项修改后再确认入库
- PDF + 图片识别：PDF 优先表格提取，图片使用 OCR 兜底
- 扫描版 PDF 兜底识别：当 PDF 文本/表格提取失败时自动尝试 OCR
- 申领部门精准解析：优先顶部“申领部门”字段，规避“部门领导意见/管理员意见”干扰
- 重复物品处理：检测 `(流水号 + 物品名称 + 经办人)`，支持跳过/新增/合并数量
- 一键备份/恢复：可下载当前数据库+上传文件备份，并一键恢复
- WebDAV 同步：支持配置 WebDAV，上传备份到远端并从远端恢复
- 采购记录在线编辑：字段直接修改并保存
- 关键字模糊搜索：支持流水号、物品名、经办人、申领部门
- 输入容错与规范化：自动清理空白、统一流水号格式、校验并规范链接 URL
- 手动录入提效：部门/经办人支持自动补全，流水号可留空自动生成
- 高级筛选：按状态、申领部门、月份（`YYYY-MM`）筛选
- 执行看板闭环：`待采购 → 已下单 → 待到货 → 待分发 → 已分发`
- 服务端分页：支持页码切换、每页条数切换、页码跳转
- 宽表格交互：支持横向滚动，首列复选框与末列操作列冻结（Sticky）
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

## Windows 打开即用

### 方式 A：源码双击启动（推荐）

1. 在 Windows 上安装 Python 3.10+（安装时勾选 `Add Python to PATH`）
2. 双击项目根目录的 `start_windows.bat`

说明：
- 首次启动会自动创建 `venv` 并安装依赖，时间较长属于正常现象
- 后续双击会直接启动桌面窗口
- 如需强制重装依赖，可用命令行运行：`start_windows.bat --reinstall`

### 方式 B：打包为 exe 分发

在 Windows 机器上执行：

```bat
scripts\build_windows.bat
```

或在 PowerShell 中执行（推荐，兼容性更好）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

仅一次性安装打包环境（不打包）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_env.ps1
```

产物：
- `dist\OfficeSuppliesTracker\OfficeSuppliesTracker.exe`

分发时请复制整个 `dist\OfficeSuppliesTracker` 目录到目标机器，再双击 `OfficeSuppliesTracker.exe`。

备注：
- 首次执行 OCR 时可能会初始化模型缓存，启动会比平时慢
- 运行数据（数据库、上传文件、WebDAV 配置）会落在 exe 所在目录

## 解析回归测试

用于持续验证“可复制 PDF / 扫描 PDF / 图片”三类样本解析效果：

```bash
python3 scripts/run_regression_suite.py
```

- 用例配置：`samples/regression/cases.json`
- 样本说明：`samples/regression/README.md`
- 结果报告：`samples/regression/last_report.json`

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 前端页面 |
| GET | `/api/items` | 列表查询（支持 `keyword`/`status`/`department`/`month`/`page`/`page_size`） |
| GET | `/api/execution-board` | 执行看板数据（按执行状态分组） |
| GET | `/api/items/{id}` | 获取单条记录 |
| POST | `/api/items` | 手动新增 |
| POST | `/api/items/batch-update` | 批量更新（状态/部门/经办人/付款/发票等） |
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
| GET | `/api/webdav/config` | 获取 WebDAV 配置（不含明文密码） |
| PUT | `/api/webdav/config` | 保存 WebDAV 配置 |
| POST | `/api/webdav/test` | 测试 WebDAV 连接 |
| GET | `/api/webdav/backups` | 列出 WebDAV 远端备份 |
| POST | `/api/webdav/backup` | 上传当前备份到 WebDAV |
| POST | `/api/webdav/restore` | 从 WebDAV 下载并恢复指定备份 |

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
| status | TEXT | 待采购/已下单/待到货/待分发/已分发（启动时自动迁移历史状态） |
| invoice_issued | BOOLEAN | 发票状态（`0=待报`，`1=已入账`） |
| payment_status | TEXT | 未付款/已付款/已报销 |
| arrival_date | TEXT | 到货日期（`YYYY-MM-DD`） |
| distribution_date | TEXT | 分发日期（`YYYY-MM-DD`） |
| signoff_note | TEXT | 签收备注 |

`recipient/分发对象` 字段已下线，不再写入数据库。

变更历史保存在 `item_history` 表，记录每次新增/更新/删除的前后快照与变更字段。

## 目录结构

```text
office-supplies-tracker/
├── main.py
├── database.py
├── import_flow.py
├── schemas.py
├── app_runtime.py
├── api_utils.py
├── backup_service.py
├── db/
│   ├── constants.py
│   ├── filters.py
│   ├── history.py
│   ├── items.py
│   ├── reports.py
│   └── schema.py
├── routers/
│   ├── imports.py
│   ├── items.py
│   └── system.py
├── parser.py
├── static/
│   ├── index.html
│   ├── app.css
│   ├── state.js
│   ├── api.js
│   └── ui.js
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
