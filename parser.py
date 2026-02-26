import re
import logging
import pdfplumber
from typing import Optional, Union

logger = logging.getLogger(__name__)

# 懒加载 PaddleOCR，避免模块导入时即加载模型
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False,
            use_gpu=False
        )
    return _ocr


class DocumentParser:
    """办公用品领用单解析器"""
    MAX_PDF_PAGES = 5
    MIN_TEXT_LENGTH_FOR_PDF_PARSE = 40

    # 正则表达式模式
    PATTERNS = {
        "serial_number": [
            r'(?:流水号|单号|编号|No\.?|NO\.?)[：:\s]*([A-Z0-9\-]+)',
            r'([A-Z]{2,}\d{6,})',
        ],
        "department": [
            r'申领部门[：:\s]*([^\n\r]+)',
        ],
        "handler": [
            r'经办人[：:\s]*([^\s\n（]+)',
            r'申领人[：:\s]*([^\s\n（]+)',
            r'人[：:\s]*([^\s\n（]+)',
        ],
        "date": [
            r'(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})',
            r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
        ],
    }

    # 非物品关键词（用于过滤）
    SKIP_KEYWORDS = [
        "插入项", "删除项", "总金额", "合计", "金额",
        "【", "】", "同意", "元",
        "部门领导", "管理员", "意见", "归属月份",
        "审批", "领用单", "序号", "编号", "No",
        "办公用品", "管理员意见"
    ]

    UI_PATTERNS = [
        r'^转发|^转事件|^回退|^指定回退|^打印|^意见|^查找',
        r'^同意|^不同意|^消息|^跟踪|^全部|^指定人',
        r'^处理后归档|^草稿|^暂存|^待办|^附言',
        r'^发起人|^附件|^隐藏|^中国瑞达|^CHINARIDA',
        r'^\d+\(\d+\)$',
        r'^《|^》|^○',
        r'^ds/',
    ]

    OCR_SKIP_KEYWORDS = SKIP_KEYWORDS + [
        "转发", "回退", "指定", "打印", "查找",
        "跟踪", "全部", "草稿", "暂存", "待办",
        "附言", "发起人", "附件", "隐藏",
        "中国瑞达", "CHINARIDA"
    ]

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.file_type = self._detect_file_type()
        self.text = ""
        self.tables = []

    def _detect_file_type(self) -> str:
        """检测文件类型"""
        import os
        ext = os.path.splitext(self.file_path)[1].lower()
        if ext in ['.pdf']:
            return 'pdf'
        elif ext in ['.png', '.jpg', '.jpeg', '.jfif']:
            return 'image'
        return 'unknown'

    def parse(self) -> dict:
        """主解析方法"""
        if self.file_type == 'pdf':
            return self._parse_pdf()
        elif self.file_type == 'image':
            return self._parse_image()
        else:
            raise ValueError(f"不支持的文件类型: {self.file_type}")

    def _parse_pdf(self) -> dict:
        """解析 PDF 文件"""
        with pdfplumber.open(self.file_path) as pdf:
            if not pdf.pages:
                return self._get_empty_result()

            pages = pdf.pages[:self.MAX_PDF_PAGES]
            text_parts = []
            table_parts = []

            for page in pages:
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    text_parts.append(page_text)

                page_tables = page.extract_tables() or []
                if not page_tables:
                    # 文本策略对部分表格线不完整的 PDF 更稳。
                    try:
                        page_tables = page.extract_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                                "snap_tolerance": 3,
                                "intersection_tolerance": 8,
                            }
                        ) or []
                    except Exception:
                        page_tables = []
                if page_tables:
                    table_parts.extend(page_tables)

            self.text = "\n".join(text_parts)
            self.tables = table_parts

            parsed = self._parse_from_tables_and_text()
            parsed["items"] = self._deduplicate_items(parsed.get("items", []))

            # 扫描件 PDF 常见无文本/无表格，触发 OCR 兜底。
            if self._should_fallback_pdf_ocr(parsed):
                ocr_parsed = self._parse_pdf_via_ocr()
                if ocr_parsed.get("items"):
                    return ocr_parsed
                # OCR 若只识别到表头字段，也尽量补齐返回值。
                for key in ("serial_number", "department", "handler", "request_date"):
                    if not parsed.get(key) and ocr_parsed.get(key):
                        parsed[key] = ocr_parsed[key]

            return parsed

    def _parse_image(self) -> dict:
        """解析图片文件（OCR）"""
        ocr = _get_ocr()
        raw_result = ocr.ocr(self.file_path, cls=True)
        ocr_pages = self._extract_ocr_pages(raw_result)
        ocr_results = ocr_pages[0] if ocr_pages else []

        # 按行分组OCR结果（根据Y坐标）
        lines = self._group_ocr_by_line_with_coords(ocr_results)

        # 过滤掉UI元素（按钮、标签等）
        filtered_lines = self._filter_ui_elements(lines)

        # 构建文本
        lines_text = [" ".join([item[1][0] for item in line]) for line in filtered_lines]
        self.text = "\n".join(lines_text)

        parsed = self._parse_from_ocr_with_coords(filtered_lines)
        parsed["items"] = self._deduplicate_items(parsed.get("items", []))
        return parsed

    def _should_fallback_pdf_ocr(self, parsed: dict) -> bool:
        items = parsed.get("items") or []
        if items:
            return False
        compact_text = re.sub(r"\s+", "", self.text or "")
        has_header = any(parsed.get(key) for key in ("serial_number", "department", "handler", "request_date"))
        return len(compact_text) < self.MIN_TEXT_LENGTH_FOR_PDF_PARSE or not has_header

    def _is_ocr_item(self, value) -> bool:
        return (
            isinstance(value, (list, tuple))
            and len(value) >= 2
            and isinstance(value[0], (list, tuple))
            and isinstance(value[1], (list, tuple))
            and len(value[1]) >= 1
        )

    def _extract_ocr_pages(self, raw_result) -> list[list]:
        """兼容 PaddleOCR 图片/PDF 的不同返回结构。"""
        if not isinstance(raw_result, list) or not raw_result:
            return []

        pages: list[list] = []

        # 情况1：图片常见结构 [[item, item, ...]]
        if len(raw_result) == 1 and isinstance(raw_result[0], list):
            first = raw_result[0]
            if first and self._is_ocr_item(first[0]):
                return [first]

        # 情况2：PDF 多页结构 [[page1_items], [page2_items], ...]
        for entry in raw_result:
            if not isinstance(entry, list) or not entry:
                continue
            if self._is_ocr_item(entry[0]):
                pages.append(entry)
                continue
            # 情况3：嵌套结构 [[[page_items]], ...]
            if isinstance(entry[0], list) and entry[0] and self._is_ocr_item(entry[0][0]):
                pages.extend([sub for sub in entry if isinstance(sub, list) and sub and self._is_ocr_item(sub[0])])

        # 情况4：少数版本直接返回 [item, item, ...]
        if not pages and self._is_ocr_item(raw_result[0]):
            pages.append(raw_result)

        return pages

    def _parse_pdf_via_ocr(self) -> dict:
        """PDF OCR 兜底：用于扫描件或文本提取失败场景。"""
        try:
            ocr = _get_ocr()
            raw_result = ocr.ocr(self.file_path, cls=True)
        except Exception as exc:
            logger.warning("PDF OCR fallback failed: %s", exc)
            return self._get_empty_result()

        ocr_pages = self._extract_ocr_pages(raw_result)[:self.MAX_PDF_PAGES]
        if not ocr_pages:
            return self._get_empty_result()

        text_parts = []
        all_items = []
        for page_results in ocr_pages:
            lines = self._group_ocr_by_line_with_coords(page_results)
            filtered_lines = self._filter_ui_elements(lines)
            if not filtered_lines:
                continue
            lines_text = [" ".join([item[1][0] for item in line]) for line in filtered_lines]
            text_parts.append("\n".join(lines_text))
            all_items.extend(self._extract_items_from_ocr_lines(filtered_lines))

        if not text_parts and not all_items:
            return self._get_empty_result()

        original_text = self.text
        self.text = "\n".join(text_parts)
        result = self._get_empty_result()
        result.update(self._extract_header_info())
        result["items"] = self._deduplicate_items(all_items)

        if not result["items"]:
            result["items"] = self._deduplicate_items(
                self._extract_items_from_text_lines(self.text.split('\n'))
            )

        # OCR 没拿到表头时，回退到原 PDF 文本再尝试一次。
        if original_text and not any(result.get(k) for k in ("serial_number", "department", "handler", "request_date")):
            self.text = original_text
            result.update(self._extract_header_info())

        return result

    def _group_ocr_by_line_with_coords(self, ocr_results: list, line_threshold: float = 20.0) -> list:
        """将OCR结果按行分组（保留坐标）"""
        if not ocr_results:
            return []

        lines = []
        current_line = [ocr_results[0]]
        current_y = ocr_results[0][0][0][1]

        for item in ocr_results[1:]:
            y = item[0][0][1]
            if abs(y - current_y) <= line_threshold:
                current_line.append(item)
            else:
                current_line.sort(key=lambda x: x[0][0][0])
                lines.append(current_line)
                current_line = [item]
                current_y = y

        if current_line:
            current_line.sort(key=lambda x: x[0][0][0])
            lines.append(current_line)

        return lines

    def _filter_ui_elements(self, lines: list) -> list:
        """过滤UI元素（按钮、标签等）"""
        filtered = []
        for line in lines:
            line_text = " ".join([item[1][0] for item in line])
            # 检查是否匹配UI模式
            is_ui = False
            for pattern in self.UI_PATTERNS:
                if re.search(pattern, line_text):
                    is_ui = True
                    break
            if not is_ui:
                # 过滤掉纯UI元素的item
                filtered_items = []
                for item in line:
                    text = item[1][0]
                    is_ui_item = False
                    for pattern in self.UI_PATTERNS:
                        if re.search(pattern, text):
                            is_ui_item = True
                            break
                    if not is_ui_item:
                        filtered_items.append(item)
                if filtered_items:
                    filtered.append(filtered_items)

        return filtered

    def _parse_from_ocr_with_coords(self, lines: list) -> dict:
        """从OCR结果（带坐标）解析数据"""
        result = self._get_empty_result()

        # 提取表头信息
        header_info = self._extract_header_info()
        result.update(header_info)

        result["items"] = self._extract_items_from_ocr_lines(lines)

        return result

    def _extract_items_from_ocr_lines(self, lines: list) -> list[dict]:
        table_start = -1
        for idx, line in enumerate(lines):
            line_text = " ".join([item[1][0] for item in line])
            if "序号" in line_text and ("物品" in line_text or "名称" in line_text):
                table_start = idx
                break
        if table_start == -1:
            return self._extract_items_simple(lines)
        return self._extract_items_from_ocr_merged(lines[table_start:])

    def _extract_items_from_ocr_merged(self, lines: list) -> list[dict]:
        """从OCR行中提取明细（基于表格结构）"""
        items = []

        # 找到表头行，确定列位置
        header_line = None
        header_idx = -1
        for idx, line in enumerate(lines):
            line_text = " ".join([item[1][0] for item in line])
            if "序号" in line_text and "物品" in line_text:
                header_line = line
                header_idx = idx
                break

        if not header_line:
            # 找不到表头，使用简单方法
            return self._extract_items_simple(lines)

        # 确定各列的X坐标范围
        col_ranges = self._determine_column_ranges(header_line)

        # 解析数据行
        for i in range(header_idx + 1, len(lines)):
            line = lines[i]
            line_text = " ".join([item[1][0] for item in line])

            # 跳过明显不是数据的行
            if self._should_skip_ocr_line(line_text):
                continue

            # 从列中提取数据
            item = self._extract_item_from_columns(line, col_ranges)
            if item and item.get("item_name"):
                items.append(item)

        return items

    def _determine_column_ranges(self, header_line: list) -> dict:
        """确定表格列的X坐标范围"""
        # 找到各关键词的X位置
        col_keywords = ["序号", "物品", "数量", "单价", "备注"]
        col_positions = {}

        for item in header_line:
            text = item[1][0]
            x = item[0][0][0]  # 左边X坐标

            for keyword in col_keywords:
                if keyword in text:
                    if keyword not in col_positions or x < col_positions[keyword]:
                        col_positions[keyword] = x

        # 根据关键词位置确定列范围
        ranges = {
            "serial": (col_positions.get("序号", 0), col_positions.get("物品", 1000)),
            "item_name": (col_positions.get("物品", 0), col_positions.get("数量", 1000)),
            "quantity": (col_positions.get("数量", 0), col_positions.get("单价", 1000)),
            "remark": (col_positions.get("备注", 0), 9999),
        }

        return ranges

    def _extract_item_from_columns(self, line: list, col_ranges: dict) -> Optional[dict]:
        """从列中提取物品信息"""
        # 按X坐标分类
        item_name_parts = []
        quantity_text = ""
        remark_text = ""

        for item in line:
            text = item[1][0]
            x = item[0][0][0]

            # 判断属于哪一列
            if col_ranges["item_name"][0] <= x <= col_ranges["item_name"][1]:
                # 物品名称列
                if re.search(r'[\u4e00-\u9fff]', text):
                    item_name_parts.append(text)
            elif col_ranges["quantity"][0] <= x <= col_ranges["quantity"][1]:
                # 数量列
                qty_match = re.search(r'(\d+(?:\.\d+)?)', text)
                if qty_match:
                    quantity_text = qty_match.group(1)
            elif col_ranges["remark"][0] <= x <= col_ranges["remark"][1]:
                # 备注列
                remark_text += " " + text

        # 合并物品名称
        item_name = " ".join(item_name_parts).strip()
        item_name = self._clean_item_name(item_name)
        if not item_name:
            return None

        # 解析数量
        quantity = 1
        if quantity_text:
            try:
                qty = float(quantity_text)
                if 0 < qty <= 1000:
                    quantity = int(qty) if qty == int(qty) else qty
            except (ValueError, TypeError):
                pass

        # 提取链接
        purchase_link = None
        url_match = re.search(r'(?:https?://|www\.)[^\s\u4e00-\u9fff]+', remark_text, re.IGNORECASE)
        if url_match:
            purchase_link = self._normalize_purchase_link(url_match.group(0))

        return {
            "item_name": item_name,
            "quantity": quantity,
            "purchase_link": purchase_link
        }

    def _extract_items_simple(self, lines: list) -> list[dict]:
        """简单提取物品（没有表头时的备用方法）"""
        items = []

        for line in lines:
            line_text = " ".join([item[1][0] for item in line])

            # 跳过非数据行
            if self._should_skip_ocr_line(line_text):
                continue

            item = self._parse_ocr_coord_line_smart(line, line_text)
            if item:
                items.append(item)

        return items

    def _should_skip_ocr_line(self, line_text: str) -> bool:
        """判断是否应该跳过该行"""
        for kw in self.OCR_SKIP_KEYWORDS:
            if kw in line_text:
                return True

        # 跳过纯数字行（可能是数量列）
        if re.match(r'^\d+\.?\d*$', line_text.strip()):
            return True

        return False

    def _parse_ocr_coord_line_smart(self, line: list, line_text: str) -> Optional[dict]:
        """智能解析OCR坐标行"""
        # 查找数量（通常是小数格式的纯文本）
        quantity = None
        qty_match = re.search(r'\b(\d+\.?\d*)\b', line_text)
        if qty_match:
            potential_qty = float(qty_match.group(1))
            # 只把看起来像数量的值当作数量（1-1000之间的小数或整数）
            if 0 < potential_qty <= 1000:
                # 检查是否是独立的数量（不是型号的一部分）
                # 如果行中有单位词，或者数字单独出现
                if re.search(r'个|本|支|盒|包|只|条|件|台|把|套', line_text):
                    # 从行文本中智能提取数量
                    quantity = self._smart_extract_quantity_from_line(line_text)

        # 提取物品名称（最左侧的中文字符）
        item_name = ""
        for item in line:
            text = item[1][0]
            # 跳过明显的数字/数量文本
            if re.match(r'^\d+\.?\d*$', text):
                continue
            if re.search(r'[\u4e00-\u9fff]', text):
                item_name = text
                break

        if not item_name:
            item_name = line_text.split()[0] if line_text.split() else ""

        # 清理物品名称
        item_name = self._clean_item_name(item_name)
        if not item_name:
            return None

        # 如果没有找到数量，使用默认值1
        if quantity is None:
            quantity = 1

        # 提取链接
        purchase_link = None
        url_match = re.search(r'(?:https?://|www\.)[^\s\u4e00-\u9fff]+', line_text, re.IGNORECASE)
        if url_match:
            purchase_link = self._normalize_purchase_link(url_match.group(0))

        return {
            "item_name": item_name,
            "quantity": quantity,
            "purchase_link": purchase_link
        }

    def _smart_extract_quantity_from_line(self, line_text: str) -> Union[int, float]:
        """从行文本中智能提取数量"""
        # 优先匹配带单位的数字
        unit_patterns = [
            r'(\d+\.?\d*)\s*(?:个|本|支|盒|包|只|条|件|台|把|套)',
        ]

        for pattern in unit_patterns:
            match = re.search(pattern, line_text)
            if match:
                try:
                    qty = float(match.group(1))
                    if 0 < qty <= 1000:
                        return int(qty) if qty == int(qty) else qty
                except (ValueError, TypeError):
                    pass

        # 如果没有找到，返回1
        return 1

    def _get_empty_result(self) -> dict:
        """返回空结果"""
        return {
            "serial_number": "",
            "department": "",
            "handler": "",
            "request_date": "",
            "items": []
        }

    def _parse_from_tables_and_text(self) -> dict:
        """从表格和文本中解析数据"""
        result = self._get_empty_result()

        # 从文本中提取表头信息
        header_info = self._extract_header_info()
        result.update(header_info)

        # 从表格中提取明细
        items = []
        if self.tables:
            items = self._extract_items_from_tables()
        if not items and self.text:
            items = self._extract_items_from_text_lines(self.text.split('\n'))
        result["items"] = self._deduplicate_items(items)

        return result

    def _parse_from_text_only(self) -> dict:
        """仅从文本中解析（用于图片OCR）"""
        result = self._get_empty_result()

        # 提取表头信息
        header_info = self._extract_header_info()
        result.update(header_info)

        # 按行解析明细
        lines = self.text.split('\n')
        items = self._extract_items_from_text_lines(lines)
        result["items"] = items

        return result

    def _extract_header_info(self) -> dict:
        """提取表头信息"""
        info = {
            "serial_number": "",
            "department": "",
            "handler": "",
            "request_date": ""
        }

        # 流水号
        for pattern in self.PATTERNS["serial_number"]:
            match = re.search(pattern, self.text, re.IGNORECASE)
            if match:
                info["serial_number"] = match.group(1).strip()
                break

        # 部门：严格锚定“申领部门”，优先从顶部表格取右侧值
        info["department"] = self._extract_department()

        # 经办人
        info["handler"] = self._extract_handler()

        # 日期
        info["request_date"] = self._extract_request_date()

        return info

    def _clean_department_text(self, value: str) -> str:
        """清理部门文本，严格执行换行/空格清洗并去掉干扰字段。"""
        if not value:
            return ""
        value = str(value).replace('\n', '').replace(' ', '')
        value = value.replace('\r', '').replace('\t', '')
        value = re.sub(r'^申领部门[：:\s]*', '', value)
        value = re.split(
            r'(?:经办人|申领人|申请人|申领日期|日期|时间|流水号|单号|编号|联系电话|部门领导意见|管理员意见|审批意见)',
            value,
            maxsplit=1
        )[0]
        value = value.strip("：:，,。；;")
        if any(kw in value for kw in ("部门领导", "领导意见", "管理员意见", "审批意见", "同意", "审批", "意见")):
            return ""
        if not value or re.fullmatch(r'[\W_]+', value):
            return ""
        return value

    def _extract_department_from_text(self) -> str:
        """从文本中提取申领部门，严格锚定“申领部门”标签。"""
        lines = [line for line in self.text.splitlines() if line and line.strip()]
        stop_labels = r'(?:经办人|申领人|申请人|申领日期|日期|时间|流水号|单号|编号|联系电话|部门领导意见|管理员意见|审批意见)'

        def has_unclosed_bracket(text: str) -> bool:
            return (text.count("（") + text.count("(")) > (text.count("）") + text.count(")"))

        for idx, line in enumerate(lines):
            if "申领部门" in line and "部门领导意见" not in line and "管理员意见" not in line:
                current = re.sub(r'^.*?申领部门[：:\s]*', '', line, count=1)
                parts = [current] if current else []
                if not current or has_unclosed_bracket(current):
                    for next_line in lines[idx + 1: idx + 4]:
                        if re.search(stop_labels, next_line) and "申领部门" not in next_line:
                            break
                        parts.append(next_line)
                        if not has_unclosed_bracket("".join(parts)):
                            break
                    current = "".join(parts)
                dept = self._clean_department_text(current)
                if dept:
                    return dept

        patterns = [
            rf'申领部门[：:\s]*([\s\S]{{1,80}}?)(?={stop_labels}[：:\s]|$)',
        ]
        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                dept = self._clean_department_text(match.group(1))
                if dept:
                    return dept

        # 兜底：保留原有模式匹配
        for pattern in self.PATTERNS["department"]:
            match = re.search(pattern, self.text)
            if match:
                dept = self._clean_department_text(match.group(1))
                if dept:
                    return dept
        return ""

    def _extract_department_from_tables(self) -> str:
        """从PDF表格中提取申领部门（严格取“申领部门”右侧单元格或同格值）。"""
        if not self.tables:
            return ""

        for table in self.tables:
            for row_index, row in enumerate(table):
                if not row:
                    continue
                for idx, cell in enumerate(row):
                    cell_text = str(cell or "").strip()
                    if not cell_text:
                        continue

                    if "部门领导意见" in cell_text or "管理员意见" in cell_text:
                        continue

                    if "申领部门" in cell_text:
                        # 情况1：同单元格“申领部门: XXX”
                        inline_match = re.search(r'申领部门[：:\s]*(.+)', cell_text)
                        if inline_match:
                            dept = self._clean_department_text(inline_match.group(1))
                            if dept:
                                return dept

                        # 情况2：值在相邻单元格
                        if idx + 1 < len(row):
                            dept = self._clean_department_text(str(row[idx + 1] or ""))
                            if dept:
                                return dept

                        # 情况3：下一行首列是值（处理表格换行）
                        if row_index + 1 < len(table):
                            next_row = table[row_index + 1]
                            if next_row:
                                dept = self._clean_department_text(str(next_row[0] or ""))
                                if dept:
                                    return dept
        return ""

    def _extract_department(self) -> str:
        """综合提取申领部门：表格优先，其次文本。"""
        dept = self._extract_department_from_tables()
        if dept:
            return dept
        return self._extract_department_from_text()

    def _extract_handler(self) -> str:
        """提取经办人信息，避免被其他“意见”字段干扰。"""
        patterns = [
            r'经办人[：:\s]*([^\s\n（(，,。；;]+)',
            r'申领人[：:\s]*([^\s\n（(，,。；;]+)',
            r'申请人[：:\s]*([^\s\n（(，,。；;]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                return match.group(1).strip()
        return ""

    def _extract_request_date(self) -> str:
        """提取申领日期，统一转为 YYYY-MM-DD。"""
        for pattern in self.PATTERNS["date"]:
            match = re.search(pattern, self.text)
            if match:
                year, month, day = match.groups()
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        return ""

    def _extract_items_from_tables(self) -> list[dict]:
        """从表格中提取明细"""
        items = []

        for table in self.tables:
            # 找到表头行
            header_row_idx = self._find_header_row(table)
            if header_row_idx == -1:
                continue

            # 找到列映射
            col_mapping = self._find_column_mapping(table[header_row_idx])

            # 解析数据行
            for row in table[header_row_idx + 1:]:
                item = self._parse_table_row(row, col_mapping)
                if item:
                    items.append(item)

        return items

    def _find_header_row(self, table: list) -> int:
        """找到表头行"""
        for idx, row in enumerate(table):
            row_text = " ".join([str(cell or "") for cell in row])
            if any(keyword in row_text for keyword in ["物品名称", "品名", "序号"]):
                if "数量" in row_text or "备注" in row_text:
                    return idx
        return -1

    def _find_column_mapping(self, header_row: list) -> dict:
        """找到列的映射关系"""
        mapping = {
            "serial": None,
            "item_name": None,
            "quantity": None,
            "unit_price": None,
            "remark": None
        }

        for idx, cell in enumerate(header_row):
            cell_text = str(cell or "").strip()
            if "序号" in cell_text or "编号" in cell_text:
                mapping["serial"] = idx
            elif "物品" in cell_text or "品名" in cell_text or "名称" in cell_text:
                mapping["item_name"] = idx
            elif "数量" in cell_text:
                mapping["quantity"] = idx
            elif "单价" in cell_text:
                mapping["unit_price"] = idx
            elif "备注" in cell_text:
                mapping["remark"] = idx

        return mapping

    def _parse_table_row(self, row: list, col_mapping: dict) -> Optional[dict]:
        """解析表格行"""
        # 跳过空行
        if not any(row):
            return None

        # 提取各列数据
        serial = self._get_cell_value(row, col_mapping.get("serial"))
        item_name = self._get_cell_value(row, col_mapping.get("item_name"))
        quantity = self._get_cell_value(row, col_mapping.get("quantity"))
        unit_price = self._get_cell_value(row, col_mapping.get("unit_price"))
        remark = self._get_cell_value(row, col_mapping.get("remark"))

        # 如果没有找到列映射，尝试智能识别
        if not item_name:
            item_name = self._smart_extract_item_name(row)

        # 跳过无效行
        if not item_name or self._should_skip_row(item_name, serial):
            return None

        # 提取数量（从整行文本中）
        quantity_value = self._parse_quantity(quantity)

        # 查找购买链接
        purchase_link = self._extract_link_from_row(row)

        # 清理物品名称
        item_name = self._clean_item_name(item_name)

        if not item_name:
            return None

        return {
            "item_name": item_name,
            "quantity": quantity_value,
            "purchase_link": purchase_link
        }

    def _get_cell_value(self, row: list, col_idx: Optional[int]) -> str:
        """获取单元格值（处理空单元格，查找相邻列）"""
        if col_idx is None or col_idx >= len(row):
            return ""
        cell = row[col_idx]
        if cell is None or str(cell).strip() == "":
            # 如果是空单元格，尝试查找相邻列（处理合并单元格）
            for offset in [1, -1, 2, -2]:
                new_idx = col_idx + offset
                if 0 <= new_idx < len(row):
                    adj_cell = row[new_idx]
                    if adj_cell and str(adj_cell).strip():
                        return str(adj_cell).strip()
            return ""
        return str(cell).strip()

    def _smart_extract_item_name(self, row: list) -> str:
        """智能提取物品名称"""
        # 找到包含中文且最长的单元格
        candidates = []
        for cell in row:
            if cell:
                cell_str = str(cell).strip()
                if re.search(r'[\u4e00-\u9fff]', cell_str):
                    # 排除明显不是物品名称的单元格
                    if not any(kw in cell_str for kw in ["部门", "经办", "日期", "链接"]):
                        candidates.append(cell_str)

        # 返回最长的候选
        if candidates:
            return max(candidates, key=len)
        return ""

    def _should_skip_row(self, item_name: str, serial: str) -> bool:
        """判断是否应该跳过该行"""
        # 检查物品名称
        if any(kw in item_name for kw in self.SKIP_KEYWORDS):
            return True

        # 检查序号
        if serial and not serial.isdigit():
            if any(kw in serial for kw in self.SKIP_KEYWORDS):
                return True

        # 空行
        if not item_name or len(item_name) < 2:
            return True

        # 纯数字或特殊字符
        if re.match(r'^[\d\s\-\/\.]+$', item_name):
            return True

        return False

    def _parse_quantity(self, quantity_str: str) -> Union[int, float]:
        """解析数量"""
        if not quantity_str:
            return 1

        # 去除空白
        quantity_str = (
            str(quantity_str)
            .replace("，", ".")
            .replace("。", ".")
            .replace("０", "0")
            .replace("１", "1")
            .replace("２", "2")
            .replace("３", "3")
            .replace("４", "4")
            .replace("５", "5")
            .replace("６", "6")
            .replace("７", "7")
            .replace("８", "8")
            .replace("９", "9")
            .strip()
        )

        # 直接提取数字
        match = re.search(r'(\d+(?:\.\d+)?)', quantity_str)
        if match:
            try:
                qty = float(match.group(1))
                if 0 < qty < 10000:
                    return int(qty) if qty == int(qty) else qty
            except (ValueError, TypeError):
                pass

        return 1

    def _deduplicate_items(self, items: list[dict]) -> list[dict]:
        """去重并做轻量规范化，避免多页/多策略重复提取。"""
        unique_items = []
        seen = set()
        for raw in items:
            item_name = self._clean_item_name(str((raw or {}).get("item_name") or ""))
            if not item_name:
                continue
            quantity = self._parse_quantity(str((raw or {}).get("quantity") or "1"))
            purchase_link = self._normalize_purchase_link((raw or {}).get("purchase_link") or "")
            key = (item_name, quantity, purchase_link or "")
            if key in seen:
                continue
            seen.add(key)
            unique_items.append({
                "item_name": item_name,
                "quantity": quantity,
                "purchase_link": purchase_link,
            })
        return unique_items

    def _extract_link_from_row(self, row: list) -> Optional[str]:
        """从行中提取链接（处理cemall等需要拼接ID的情况）"""
        for cell in row:
            if cell:
                cell_str = str(cell)
                # 查找URL和可能的商品ID
                url_match = re.search(r'((?:https?://|www\.)[^\s\u4e00-\u9fff]+)', cell_str, re.IGNORECASE)
                if url_match:
                    url = url_match.group(0).strip()

                    # 检查是否需要拼接商品ID（cemall特殊处理）
                    if 'cemall.com.cn/goods/' in url:
                        # 查找URL后面的数字ID（在换行符或空格后）
                        id_match = re.search(r'[\s\n]+(\d{10,})', cell_str[url_match.end():])
                        if id_match:
                            product_id = id_match.group(1)
                            # 拼接ID到商品号后面
                            url = re.sub(r'/goods/(\d+)', lambda m: f'/goods/{m.group(1)}{product_id}', url)

                    normalized = self._normalize_purchase_link(url)
                    if normalized:
                        return normalized

        return None

    def _normalize_purchase_link(self, value: str) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        text = (
            text.replace("：", ":")
            .replace("／", "/")
            .replace("．", ".")
            .replace("　", " ")
            .strip()
        )
        text = re.sub(r"\s+", "", text)
        text = re.sub(r'[，。；;、）)\]>》]+$', '', text)
        if re.match(r"^www\.", text, re.IGNORECASE):
            text = f"https://{text}"
        if not re.match(r"^https?://", text, re.IGNORECASE):
            return None
        return text

    def _clean_item_name(self, name: str) -> Optional[str]:
        """清理物品名称"""
        if not name:
            return None

        # 移除换行符和多余空白
        name = re.sub(r'[\n\r\t]+', '', name)
        # 处理多余空格（但保留单个空格）
        name = re.sub(r' {2,}', ' ', name).strip()

        # 移除序号
        name = re.sub(r'^\d+[\.\s、]*', '', name)

        # 移除URL
        name = re.sub(r'https?://[^\s]+', '', name)

        # 移除单位标注（更全面的处理）
        unit_patterns = [
            r'\s*[（\(]?\s*单位[:：]?\s*[^\））]*[\）)]?\s*$',
            r'\s*[（\(]单位[^\））]*[\）)]\s*',
            r'\s*单位[:：][^\s]*',
            r'\s*京东\s*', r'\s*淘宝\s*', r'\s*购买\s*',
        ]
        for pattern in unit_patterns:
            name = re.sub(pattern, '', name)

        # 移除链接相关
        for kw in ["链接", "http", "www", "购买"]:
            if kw in name:
                name = name.split(kw)[0]

        name = name.strip()

        # 验证是否为有效物品名称
        if not self._is_valid_item_name(name):
            return None

        return name

    def _is_valid_item_name(self, name: str) -> bool:
        """检查是否为有效的物品名称"""
        if not name or len(name) < 2:
            return False

        # 必须包含中文
        if not re.search(r'[\u4e00-\u9fff]', name):
            return False

        # 排除特定模式
        exclude_patterns = [
            r'^插入项$', r'^删除项$', r'^总金额', r'^合计',
            r'^【.*】$', r'^\[.*\]$', r'.*意见.*', r'.*审批.*',
            r'^办公用品$', r'^归属月份',
        ]

        for pattern in exclude_patterns:
            if re.search(pattern, name):
                return False

        return True

    def _extract_items_from_text_lines(self, lines: list[str]) -> list[dict]:
        """从文本行中提取明细（用于图片OCR）"""
        items = []

        for line in lines:
            line = line.strip()
            if not line or self._should_skip_row(line, ""):
                continue

            # 简单的行解析
            item = self._parse_text_line(line)
            if item:
                items.append(item)

        return items

    def _parse_text_line(self, line: str) -> Optional[dict]:
        """解析单行文本"""
        # 提取链接
        url_match = re.search(r'(?:https?://|www\.)[^\s]+', line, re.IGNORECASE)
        purchase_link = self._normalize_purchase_link(url_match.group(0)) if url_match else None

        # 移除URL后的文本
        if url_match:
            line = line.replace(url_match.group(0), "")

        # 提取数量
        quantity = self._parse_quantity(line)

        # 清理物品名称
        item_name = self._clean_item_name(line)

        if not item_name:
            return None

        return {
            "item_name": item_name,
            "quantity": quantity,
            "purchase_link": purchase_link
        }


def parse_document(file_path: str) -> dict:
    """解析文档的入口函数"""
    parser = DocumentParser(file_path)
    return parser.parse()
