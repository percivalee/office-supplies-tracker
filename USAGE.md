# 使用说明

本文档描述当前版本的页面操作流程。

## 1. 启动

```bash
./start.sh
```

启动后访问：`http://localhost:8000`

## 2. 上传领用单

- 页面顶部点击 `上传领用单`
- 支持格式：`PDF / PNG / JPG / JPEG`
- 上传后系统先进入“导入预览”窗口

- 先核对并可直接修改：流水号、部门、经办人、日期、物品名称、数量、链接
- 点击 `确认导入` 后再写入数据库
- 若为扫描版 PDF，系统会在文本提取失败时自动切换 OCR 兜底

导入确认后有两种结果：

- 无重复：直接写入数据库
- 有重复：弹出“检测到重复物品”窗口，按需选择：
  - 跳过重复
  - 合并数量
  - 新增非重复项（重复项会被跳过）

## 3. 手动添加记录

- 点击顶部 `添加记录`
- 在弹窗中填写字段并提交
- 提交成功后会刷新表格和统计
- 输入会自动做基础规范化（去多余空白、流水号大写、`www.` 链接自动补 `https://`）
- 手动新增时流水号可留空，系统会自动生成（`REQ-时间戳`）

## 4. 在线编辑记录

采购记录表中可直接编辑并保存：

- 申领部门
- 经办人
- 物品名称
- 数量
- 单价
- 状态
- 到货日期
- 分发日期
- 签收备注
- 发票状态
- 付款状态

说明：
- `分发对象` 字段已移除，不再显示也不再入库
- 表格列较多时支持横向滚动，首列复选框与末列操作列会固定显示

删除：点击行内 `删除` 按钮。

批量删除：勾选多条后点击 `批量删除`。

批量修改：勾选多条后，在批量操作栏选择字段和值，点击 `应用批量修改`。

## 5. 高级筛选

表格顶部支持组合筛选：

- 关键字搜索（流水号 / 物品名 / 经办人 / 申领部门，模糊匹配）
- 状态
- 申领部门
- 月份（`YYYY-MM`）

点击 `重置筛选` 可恢复默认。

## 6. 分页

分页位于表格底部，支持：

- 上一页 / 下一页
- 每页条数切换（20 / 50 / 100）
- 输入页码后跳转

## 7. 执行看板

- 点击顶部 `执行看板`
- 卡片按执行流状态分列：`待采购`、`已下单`、`待到货`、`待分发`（固定四列同屏）
- `已分发` 作为闭环结果，不单独占用执行中列
- 在 `待分发` 列可填写分发日期和签收备注，点击 `完成分发闭环` 后流转为 `已分发`

## 8. Excel 导出

点击 `导出为 Excel`，按当前筛选条件导出。

导出列包含：

- 流水号
- 申领日期
- 申领部门
- 经办人
- 物品名称
- 数量
- 单价
- 状态
- 到货日期
- 分发日期
- 签收备注

## 9. 金额统计报表

- 点击顶部 `金额报表`
- 报表会按当前主列表筛选条件统计：
  - 总金额
  - 已填单价金额
  - 未填单价记录数
  - 按部门/状态/月份的金额分布
- 需要时点击弹窗底部 `刷新报表`

## 10. 变更历史

- 点击顶部 `变更历史`
- 可按以下条件筛选：
  - 关键词（流水号/物品名/经办人/部门）
  - 操作类型（新增/修改/删除）
  - 月份（`YYYY-MM`）
- 表格会显示每次变更的时间、字段与简要前后值

## 11. 数据备份与恢复

- 备份：点击页面顶部 `备份数据`，会下载一个 `.zip` 备份包
- 恢复：点击页面顶部 `恢复备份`，选择 `.zip` 文件后确认
- 恢复会覆盖当前 `office_supplies.db` 与 `uploads/`，请谨慎操作

## 12. WebDAV 同步

- 点击顶部 `WebDAV`
- 填写并保存：地址、用户名、密码、远端目录
- 点击 `测试连接` 验证配置
- 点击 `上传当前备份` 可把当前数据快照上传到 WebDAV
- 远端备份列表可直接点击 `恢复`，会覆盖本地数据

## 13. 常见问题

### 13.1 申领部门识别错误

优先使用 PDF，且确保页首“申领部门”区域清晰完整。

### 13.2 上传失败

检查：

- 文件类型是否受支持
- 网络或模型加载是否异常（首次 OCR 可能较慢）

### 13.3 数据备份

备份项目根目录的 `office_supplies.db` 即可。

### 13.4 Windows 打包报错

- 必须先 `cd` 到项目根目录再执行脚本
- 不要执行带行号的命令（例如 `scripts/build_windows.bat:1`）
- 若出现 `No module named pyinstaller`，先执行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_env.ps1`
- 若出现 `ISCC.exe not found`，执行：`powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1 -IsccPath "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"`

## 14. Windows 打包与安装包

在项目根目录 PowerShell 执行：

```powershell
# 1) 安装打包环境（仅安装，不打包）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows_env.ps1

# 2) 生成 exe
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

# 3) 生成 Setup 安装包（需先安装 Inno Setup 6）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows_installer.ps1
```

产物位置：

- exe：`dist\OfficeSuppliesTracker\OfficeSuppliesTracker.exe`
- 安装包：`dist-installer\OfficeSuppliesTracker-Setup-YYYY.MM.DD.exe`
- 构建日志：`build_logs\`

## 15. 解析回归

当你调整了 PDF/OCR 解析逻辑后，建议执行回归：

```bash
python3 scripts/run_regression_suite.py
```

- 用例与样本说明：`samples/regression/README.md`
- 回归报告默认输出到：`samples/regression/last_report.json`
