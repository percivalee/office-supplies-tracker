# 办公用品采购系统

用于内部办公用品采购管理的单用户工具。支持上传领用单（PDF/图片）自动识别，在线维护采购流程，并可按条件筛选与导出 Excel。

当前版本：`1.2.3`

## 更新日志 (Changelog)

### v1.2.3 (2026-03-05)

- 修复 Windows 安装版在 `Program Files` 下运行时的权限问题：新增数据目录可写性探测，写入失败时自动回退到 `%APPDATA%/OfficeSuppliesTracker/data`。
- 统一运行时写路径到可写状态目录：SQLite、上传目录、运行日志、WebDAV/Gemini 配置与恢复临时文件不再依赖安装目录写权限。
- 修复 Windows 安装包“安装后打不开”问题：CI 打包入口切换为 `desktop.py`，并补齐 `alembic` / `alembic.ini` 及关键隐藏依赖。
- 修复 Release 资产发布稳定性：预清理同名资产并规范上传文件名，避免 `already_exists` 与异常 `-.exe` 命名。

## 🚀 一键私有化部署

企业用户无需本地构建镜像，只需下载项目根目录的 `docker-compose.yml` 到任意服务器目录，在同级目录执行：

```bash
docker-compose up -d
```

系统会自动从 `ghcr.io/percivalee/office-supplies-tracker:latest` 拉取网络镜像并启动服务。

访问地址：`http://服务器IP:8000`

数据持久化目录：
- 宿主机：`./data`
- 容器内：`/app/data`

## 核心功能

- 单据导入解析：上传 PDF/图片后自动提取流水号、部门、经办人、日期与物品明细
- AI 视觉解析网关：系统设置中可切换 `local/cloud` 引擎，`cloud` 支持 `OpenAI 兼容 / Anthropic / Google` 三协议与中转地址
- 异步解析任务：上传后立即返回 `task_id`，前端轮询任务状态，避免大文件阻塞超时
- 导入预览校正：入库前可逐项编辑，避免脏数据直接落库
- OCR 兜底链路：可复制 PDF 优先结构化提取，扫描 PDF/图片自动走 OCR
- 重复处理策略：按 `(流水号 + 物品名称 + 经办人)` 检测重复，支持跳过/合并数量/仅新增非重复项
- 台账在线编辑：关键字段可直接修改，支持批量修改与批量删除
- 执行看板闭环：`待采购 → 待到货 → 待分发 → 已分发`，支持拖拽和一键流转
- 报表筛选联动：台账筛选条件变更后，进入报表页会自动按最新筛选重算
- 统计报表：
  - 金额统计（总额、已计价、缺失单价、部门/状态/月度趋势）
  - 执行分析（执行漏斗、采购周期分布、月度金额结构）
- 审计日志：记录新增/修改/删除，支持按动作、关键词、月份筛选，并支持按历史版本回滚
- 数据治理：
  - 回收站（软删除恢复、彻底删除）
  - 数据质量巡检（问题码聚合、重复键组识别）
- 备份与恢复：
  - 本地备份包下载与恢复（恢复前自动健康检查）
  - WebDAV 云端备份、远端恢复、保留策略清理
- 导出与筛选：按筛选条件导出 Excel，支持关键词/状态/部门/月份/分页
- Windows 桌面版：支持 `start_windows.bat` 直接运行、`PyInstaller` 打包与 `Inno Setup` 安装包
- 轻动画体验：视图切换、图表级联、弹窗过渡，并支持 `prefers-reduced-motion` 自动降级

## 技术栈

- 后端：FastAPI + SQLite + aiosqlite + Alembic
- 文档解析：pdfplumber + PaddleOCR
- 前端：Vue 3 + TailwindCSS + Axios
- 桌面端容器：pywebview（本地启动 FastAPI 并内嵌 Web 界面）
- 导出：openpyxl

## AI 视觉解析引擎

系统支持 `local` 与 `cloud` 双引擎：

- `local`：本地 OCR/规则解析，不依赖外部大模型服务
- `cloud`：多协议大模型视觉解析，支持以下三种协议
  - `openai`：OpenAI 兼容接口（支持自定义 `base_url` 中转）
  - `anthropic`：Anthropic Claude 视觉接口
  - `google`：Google Gemini 直连接口

`cloud` 模式统一通过 `engine/protocol/api_key/model_name/base_url` 参数配置，上传后返回 `task_id`，前端轮询异步任务结果。

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

## 数据库迁移（Alembic）

- 应用启动时会自动执行 `alembic upgrade head`，用于平滑升级数据库结构
- 初次接入采用基线版本 `initial baseline`

手动执行迁移命令（可选）：

```bash
source venv/bin/activate
alembic upgrade head
alembic revision --autogenerate -m "your migration message"
```

## 桌面版运行（无需打包）

```bash
source venv/bin/activate
python desktop.py
```

## Windows 打开即用

### 先执行哪个命令（建议顺序）

在项目根目录打开 PowerShell 后，按目标选择以下命令：

```powershell
# 1) 只想运行系统（不打包）
.\start_windows.bat

# 2) 只安装打包环境（不产出 exe）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_env.ps1

# 3) 产出 exe
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

# 4) 产出安装包 Setup.exe（需先安装 Inno Setup 6）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

注意：
- 命令前不要带行号后缀（例如 `scripts/build_windows.bat:1` 是错误写法）
- 必须在项目根目录执行，否则会出现“系统找不到指定路径”

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

### 方式 C：生成安装包（Setup.exe）

先安装 Inno Setup 6（可选命令）：

```powershell
winget install JRSoftware.InnoSetup
```

然后在项目根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

常用参数：

```powershell
# 指定 Inno Setup 编译器路径（当系统 PATH 检测不到 iscc.exe 时）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

# 跳过 exe 重编译，直接基于现有 dist 目录生成安装包
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1 -SkipExeBuild
```

或：

```bat
scripts\build_windows_installer.bat
```

安装包产物：
- `dist-installer\OfficeSuppliesTracker-Setup-YYYY.MM.DD.exe`

若报 `ISCC.exe not found`：
- 先确认 Inno Setup 已安装
- 然后使用 `-IsccPath` 明确指定 `ISCC.exe` 路径
- 或设置环境变量 `ISCC_PATH` 后重新打开 PowerShell 再执行

常见错误排查：
- `No module named pyinstaller`：先执行 `setup_windows_env.ps1`，或删除旧 `venv` 后使用 `build_windows.ps1 -ReinstallVenv`
- `pyinstaller: error: argument --add-data: expected one argument`：不要手工拆行执行 PyInstaller 参数，直接运行 `build_windows.ps1`
- 出现 `>>>` 进入 Python 交互：这是脚本被中断或误进入解释器，输入 `exit()` 退出后，重新执行上面的完整命令
- `Get-Command iscc.exe` 找不到但已安装 Inno Setup：重新打开 PowerShell，再执行 `build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`

备注：
- 首次执行 OCR 时可能会初始化模型缓存，启动会比平时慢
- 运行数据（数据库、上传文件、WebDAV 配置）会落在 exe 所在目录
- 当前前端默认通过 CDN 加载 `Vue/Tailwind/Axios`，桌面版首次运行建议保持网络可用；如需完全离线，请改为本地静态依赖

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
| GET | `/api/recycle-bin` | 回收站列表（软删除记录） |
| POST | `/api/items/{id}/restore` | 从回收站恢复单条记录 |
| DELETE | `/api/recycle-bin/{id}` | 彻底删除回收站记录 |
| POST | `/api/upload-ocr` | 上传并创建异步解析任务（支持 `engine/protocol/api_key/model_name/base_url`） |
| POST | `/api/upload` | 兼容旧路径，行为同 `/api/upload-ocr` |
| GET | `/api/tasks/{task_id}` | 查询解析任务状态与结果 |
| POST | `/api/import/confirm` | 确认导入（支持人工校正与重复处理） |
| POST | `/api/upload/handle-duplicates` | 处理重复物品 |
| GET | `/api/stats` | 获取统计数据 |
| GET | `/api/reports/amount` | 金额统计报表（支持与列表一致的筛选参数） |
| GET | `/api/reports/operations` | 执行漏斗/周期分布/月度金额结构报表 |
| GET | `/api/data-quality` | 数据质量巡检报告 |
| GET | `/api/history` | 变更历史列表（`action`/`keyword`/`month`/`page`/`page_size`） |
| POST | `/api/items/{id}/rollback` | 回滚到指定历史版本 |
| GET | `/api/autocomplete` | 获取部门/经办人/状态候选 |
| GET | `/api/export` | 导出 Excel（支持与列表一致的筛选参数，含 `keyword`） |
| GET | `/api/backup` | 下载数据备份（数据库+上传文件） |
| POST | `/api/backup/health` | 备份健康检查（不写入当前数据） |
| POST | `/api/restore` | 上传备份包并恢复数据 |
| GET | `/api/webdav/config` | 获取 WebDAV 配置（不含明文密码） |
| PUT | `/api/webdav/config` | 保存 WebDAV 配置 |
| POST | `/api/webdav/test` | 测试 WebDAV 连接 |
| GET | `/api/webdav/backups` | 列出 WebDAV 远端备份 |
| POST | `/api/webdav/backup` | 上传当前备份到 WebDAV |
| POST | `/api/webdav/restore` | 从 WebDAV 下载并恢复指定备份 |
| GET | `/api/gemini/config` | 读取 Gemini 默认配置（脱敏） |
| PUT | `/api/gemini/config` | 保存 Gemini 默认配置 |
| POST | `/api/gemini/models` | 按 API Key 拉取可用 Gemini 模型 |

## 关键参数说明

- `month`：必须是 `YYYY-MM`，例如 `2026-02`
- `keyword`：模糊搜索关键词（会匹配流水号、物品名、经办人、申领部门）
- `action`：历史操作类型，仅支持 `create` / `update` / `delete`
- `page`：页码，从 `1` 开始
- `page_size`：每页条数，范围 `1-200`
- `engine`：解析引擎，`local` 或 `cloud`
- `protocol`：云端协议，`openai` / `anthropic` / `google`

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
| status | TEXT | 待采购/待到货/待分发/已分发（启动时自动迁移历史状态） |
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
- 数据库文件默认在 `data/office_supplies.db`（目录不存在会自动创建）

## 💼 商业授权与企业版

本项目免费提供给个人开发者学习使用。如果您希望在企业内部署、需要对接企业 OA 系统、或需要专业的审计功能定制与技术支持，请联系作者购买商业授权。企业版提供：无限制使用、专有合规功能更新、数据安全技术支持。

联系邮箱：`i@yep.li`

## 📦 获取 Windows 客户端

用户无需自行编译，请直接前往本仓库的 Releases 页面，下载最新版本的 `.exe` 绿色免安装版，双击即可运行。
