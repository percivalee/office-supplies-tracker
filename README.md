# 办公用品采购自动解析与追踪系统

单用户效率工具，自动解析办公用品领用单（PDF/图片），追踪采购和发放进度。

## 功能特性

- 📄 **智能解析**: 支持 PDF 和图片格式，自动提取表单信息
- 🔍 **OCR 识别**: 集成 PaddleOCR，精准识别中文表格
- 🔗 **链接清洗**: 自动清洗和修复被换行截断的购买链接
- 📊 **进度追踪**: 状态管理（待采购→已采购→已到货→已发放）
- 💰 **财务跟进**: 发票开具状态、付款/报销状态追踪
- 🖱️ **快捷操作**: 表格内直接编辑，无需跳转页面

## 数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| 流水号 | String | 领用单编号 |
| 申领部门 | String | 申领部门名称 |
| 经办人 | String | 申领/经办人 |
| 申领日期 | Date | 领用单日期 |
| 物品名称 | String | 物品名称 |
| 数量 | Float | 申领数量 |
| 购买链接 | String | 清洗后的可点击链接 |
| 实际单价 | Float | 采购时填入 |
| 状态 | Enum | 待采购、已采购、已到货、已发放 |
| 发票是否开具 | Boolean | 是否已开发票 |
| 付款状态 | Enum | 未付款、已付款、已报销 |

## 安装与运行

### 1. 安装依赖

```bash
cd office-supplies-tracker
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python main.py
```

### 3. 访问系统

打开浏览器访问: http://localhost:8000

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/api/items` | 获取所有记录 |
| GET | `/api/items/{id}` | 获取单条记录 |
| POST | `/api/items` | 手动创建记录 |
| PUT | `/api/items/{id}` | 更新记录 |
| DELETE | `/api/items/{id}` | 删除记录 |
| POST | `/api/upload` | 上传文件解析 |
| GET | `/api/stats` | 获取统计数据 |
| GET | `/api/autocomplete` | 获取自动补全数据 |

## 解析逻辑说明

### PDF 解析
- 使用 `pdfplumber` 提取表格结构
- 优先解析结构化表格，失败时降级到文本解析
- 支持处理多行文本被截断的情况

### 图片 OCR
- 使用 `PaddleOCR` 进行文字识别
- 按坐标聚类识别表格行和列
- 对中文和复杂表格有较好的识别效果

### 链接清洗策略
```
原始: "拼多多官网\nhttps://pinduoduo.com/item/123\n"
↓ 合并多行
"拼多多官网 https://pinduoduo.com/item/123"
↓ 正则提取
"https://pinduoduo.com/item/123"
↓ 清理尾部字符
"https://pinduoduo.com/item/123"
```

### 表头识别规则
- **流水号**: 匹配 `单号/流水号/编号/No` 后的内容，或 `OA+数字` 格式
- **部门**: 匹配 `部门/申领部门` 后的内容
- **经办人**: 匹配 `经办人/申领人/申请人` 后的内容
- **日期**: 匹配 `2024-01-15` 或 `2024年1月15日` 格式

## 目录结构

```
office-supplies-tracker/
├── main.py              # FastAPI 主程序
├── database.py          # 数据库操作
├── parser.py            # 文件解析器
├── requirements.txt     # Python 依赖
├── README.md            # 说明文档
├── static/
│   └── index.html       # 前端页面
└── office_supplies.db   # SQLite 数据库（运行后生成）
```

## 使用建议

1. **首次运行**: PaddleOCR 会自动下载中文模型（约 100MB），请耐心等待
2. **图片质量**: 建议上传清晰的扫描件或高清截图，识别效果更佳
3. **批量导入**: 同一领用单会自动拆分为多条记录
4. **去重机制**: 基于 (流水号+物品名称+经办人) 自动去重

## 技术栈

- **后端**: FastAPI + SQLite + aiosqlite
- **解析**: pdfplumber + PyMuPDF + PaddleOCR
- **前端**: Vue 3 + TailwindCSS + Axios
