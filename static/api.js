(function (global) {
    global.AppApi = {
        methods: {
                openAddModal() {
                    this.showImportPreviewModal = false;
                    this.showDuplicateModal = false;
                    this.showAddModal = true;
                },
                closeAddModal() {
                    this.showAddModal = false;
                },
                formatCurrency(value) {
                    const amount = Number(value);
                    if (!Number.isFinite(amount)) return '0.00';
                    return amount.toLocaleString('zh-CN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                    });
                },
                formatFileSize(size) {
                    const value = Number(size);
                    if (!Number.isFinite(value) || value < 0) return '-';
                    if (value < 1024) return `${value} B`;
                    const kb = value / 1024;
                    if (kb < 1024) return `${kb.toFixed(1)} KB`;
                    const mb = kb / 1024;
                    if (mb < 1024) return `${mb.toFixed(1)} MB`;
                    const gb = mb / 1024;
                    return `${gb.toFixed(2)} GB`;
                },
                async openWebdavModal() {
                    this.showWebdavModal = true;
                    this.webdavSelectedBackup = '';
                    await this.loadWebdavConfig();
                    if (this.webdavConfig.configured) {
                        await this.loadWebdavBackups();
                    } else {
                        this.webdavBackups = [];
                    }
                },
                closeWebdavModal() {
                    this.showWebdavModal = false;
                    this.webdavConfig.password = '';
                    this.webdavSelectedBackup = '';
                },
                async loadWebdavConfig() {
                    try {
                        const res = await axios.get('/api/webdav/config');
                        const config = res.data || {};
                        this.webdavConfig = {
                            configured: !!config.configured,
                            base_url: config.base_url || '',
                            username: config.username || '',
                            password: '',
                            remote_dir: config.remote_dir || '',
                            has_password: !!config.has_password,
                        };
                    } catch (e) {
                        alert('加载 WebDAV 配置失败: ' + (e.response?.data?.detail || e.message));
                    }
                },
                async saveWebdavConfig(showAlert = true, manageLoading = true) {
                    if (manageLoading) this.webdavLoading = true;
                    try {
                        const payload = {
                            base_url: (this.webdavConfig.base_url || '').toString().trim(),
                            username: (this.webdavConfig.username || '').toString().trim(),
                            password: this.webdavConfig.password || '',
                            remote_dir: (this.webdavConfig.remote_dir || '').toString().trim(),
                        };
                        const res = await axios.put('/api/webdav/config', payload);
                        if (showAlert) {
                            alert(res.data?.message || 'WebDAV 配置已保存');
                        }
                        const config = res.data?.config || {};
                        this.webdavConfig.configured = !!config.configured;
                        this.webdavConfig.has_password = !!config.has_password;
                        this.webdavConfig.password = '';
                        return config;
                    } catch (e) {
                        if (showAlert) {
                            alert('保存 WebDAV 配置失败: ' + (e.response?.data?.detail || e.message));
                        }
                        throw e;
                    } finally {
                        if (manageLoading) this.webdavLoading = false;
                    }
                },
                async testWebdavConnection() {
                    this.webdavLoading = true;
                    try {
                        await this.saveWebdavConfig(false, false);
                        const res = await axios.post('/api/webdav/test');
                        alert(res.data?.message || '连接测试通过');
                    } catch (e) {
                        alert('WebDAV 测试失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.webdavLoading = false;
                    }
                },
                async loadWebdavBackups() {
                    this.webdavLoading = true;
                    try {
                        const res = await axios.get('/api/webdav/backups');
                        this.webdavBackups = Array.isArray(res.data?.items) ? res.data.items : [];
                        if (this.webdavSelectedBackup && !this.webdavBackups.find((f) => f.name === this.webdavSelectedBackup)) {
                            this.webdavSelectedBackup = '';
                        }
                    } catch (e) {
                        alert('加载 WebDAV 备份列表失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.webdavLoading = false;
                    }
                },
                async uploadBackupToWebdav() {
                    this.webdavLoading = true;
                    try {
                        await this.saveWebdavConfig(false, false);
                        const res = await axios.post('/api/webdav/backup');
                        alert(res.data?.message || '上传成功');
                        await this.loadWebdavBackups();
                    } catch (e) {
                        alert('上传 WebDAV 失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.webdavLoading = false;
                    }
                },
                async restoreFromWebdav(filename) {
                    const name = (filename || '').toString().trim();
                    if (!name) {
                        alert('请先选择要恢复的备份');
                        return;
                    }
                    if (!confirm(`确认从 WebDAV 恢复备份 ${name}？这会覆盖当前数据。`)) {
                        return;
                    }
                    this.webdavLoading = true;
                    this.restoring = true;
                    try {
                        await this.saveWebdavConfig(false, false);
                        const res = await axios.post('/api/webdav/restore', { filename: name });
                        alert(res.data?.message || '恢复成功');
                        await this.loadAutocomplete();
                        await this.loadItems();
                        await this.loadStats();
                    } catch (e) {
                        alert('从 WebDAV 恢复失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.webdavLoading = false;
                        this.restoring = false;
                    }
                },
                openAmountReportModal() {
                    this.showAmountReportModal = true;
                    this.loadAmountReport();
                },
                closeAmountReportModal() {
                    this.showAmountReportModal = false;
                },
                async loadAmountReport() {
                    this.amountReportLoading = true;
                    try {
                        const params = {};
                        if (this.filterKeyword) params.keyword = this.filterKeyword;
                        if (this.filterStatus) params.status = this.filterStatus;
                        if (this.filterDepartment) params.department = this.filterDepartment;
                        if (this.filterMonth) params.month = this.filterMonth;
                        const res = await axios.get('/api/reports/amount', { params });
                        const data = res.data || {};
                        this.amountReport = {
                            summary: {
                                total_records: data.summary?.total_records || 0,
                                total_amount: data.summary?.total_amount || 0,
                                priced_amount: data.summary?.priced_amount || 0,
                                missing_price_records: data.summary?.missing_price_records || 0
                            },
                            by_department: Array.isArray(data.by_department) ? data.by_department : [],
                            by_status: Array.isArray(data.by_status) ? data.by_status : [],
                            by_month: Array.isArray(data.by_month) ? data.by_month : []
                        };
                    } catch (e) {
                        alert('加载金额报表失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.amountReportLoading = false;
                    }
                },
                openHistoryModal() {
                    this.showHistoryModal = true;
                    this.historyPage = 1;
                    this.loadHistory();
                },
                closeHistoryModal() {
                    this.showHistoryModal = false;
                },
                historyActionLabel(action) {
                    const labels = { create: '新增', update: '修改', delete: '删除' };
                    return labels[action] || action || '-';
                },
                historyFieldLabel(field) {
                    const labels = {
                        serial_number: '流水号',
                        department: '申领部门',
                        handler: '经办人',
                        request_date: '申领日期',
                        item_name: '物品名称',
                        quantity: '数量',
                        purchase_link: '购买链接',
                        unit_price: '单价',
                        status: '状态',
                        invoice_issued: '发票',
                        payment_status: '付款状态',
                    };
                    return labels[field] || field;
                },
                formatHistoryValue(field, value) {
                    if (value === null || value === undefined || value === '') return '空';
                    if (field === 'invoice_issued') {
                        if (value === true || value === 1) return '是';
                        if (value === false || value === 0) return '否';
                    }
                    if (typeof value === 'number') return String(value);
                    return String(value);
                },
                historyDetailText(row) {
                    if (row.action === 'create') return '新增记录';
                    if (row.action === 'delete') return '删除记录';
                    const fields = Array.isArray(row.changed_fields) ? row.changed_fields : [];
                    if (!fields.length) return '-';
                    const beforeData = row.before_data || {};
                    const afterData = row.after_data || {};
                    const parts = fields.slice(0, 3).map((field) => {
                        const beforeValue = this.formatHistoryValue(field, beforeData[field]);
                        const afterValue = this.formatHistoryValue(field, afterData[field]);
                        return `${this.historyFieldLabel(field)}: ${beforeValue} -> ${afterValue}`;
                    });
                    if (fields.length > 3) {
                        parts.push(`等 ${fields.length} 项`);
                    }
                    return parts.join('；');
                },
                async loadHistory() {
                    this.historyLoading = true;
                    try {
                        const params = {
                            page: this.historyPage,
                            page_size: this.historyPageSize,
                        };
                        if (this.historyKeyword) params.keyword = this.historyKeyword;
                        if (this.historyAction) params.action = this.historyAction;
                        if (this.historyMonth) params.month = this.historyMonth;
                        const res = await axios.get('/api/history', { params });
                        this.historyItems = Array.isArray(res.data.items) ? res.data.items : [];
                        this.historyTotal = Number(res.data.total) || 0;
                        const maxPage = Math.max(1, Math.ceil(this.historyTotal / this.historyPageSize));
                        if (this.historyPage > maxPage) {
                            this.historyPage = maxPage;
                            await this.loadHistory();
                        }
                    } catch (e) {
                        alert('加载变更历史失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.historyLoading = false;
                    }
                },
                applyHistoryFilter() {
                    this.historyPage = 1;
                    this.loadHistory();
                },
                clearHistoryFilters() {
                    this.historyKeyword = '';
                    this.historyAction = '';
                    this.historyMonth = '';
                    this.applyHistoryFilter();
                },
                goHistoryPage(page) {
                    if (page < 1 || page > this.historyTotalPages || page === this.historyPage) return;
                    this.historyPage = page;
                    this.loadHistory();
                },
                normalizeDateText(value) {
                    const raw = (value || '').toString().trim();
                    if (!raw) return '';
                    let normalized = raw
                        .replace(/年/g, '-')
                        .replace(/月/g, '-')
                        .replace(/[日号]/g, '')
                        .replace(/[/.]/g, '-')
                        .replace(/T/g, ' ')
                        .trim();
                    if (normalized.includes(' ')) {
                        normalized = normalized.split(/\s+/, 1)[0];
                    }
                    normalized = normalized.replace(/-+/g, '-').replace(/^-+|-+$/g, '');

                    let year;
                    let month;
                    let day;
                    let matched = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
                    if (matched) {
                        year = Number(matched[1]);
                        month = Number(matched[2]);
                        day = Number(matched[3]);
                    } else {
                        matched = normalized.match(/^(\d{4})(\d{2})(\d{2})$/);
                        if (!matched) return raw;
                        year = Number(matched[1]);
                        month = Number(matched[2]);
                        day = Number(matched[3]);
                    }

                    const date = new Date(year, month - 1, day);
                    if (
                        date.getFullYear() !== year ||
                        date.getMonth() !== month - 1 ||
                        date.getDate() !== day
                    ) {
                        return raw;
                    }
                    const mm = String(month).padStart(2, '0');
                    const dd = String(day).padStart(2, '0');
                    return `${year}-${mm}-${dd}`;
                },
                normalizeDateField(target, field) {
                    if (!target || !field) return;
                    const normalized = this.normalizeDateText(target[field]);
                    target[field] = normalized;
                },
                normalizeText(value) {
                    return (value || '')
                        .toString()
                        .replace(/　/g, ' ')
                        .trim()
                        .replace(/\s+/g, ' ');
                },
                normalizeSerial(value) {
                    return this.normalizeText(value).toUpperCase().replace(/\s+/g, '');
                },
                normalizeUrlText(value) {
                    let text = (value || '').toString().trim();
                    if (!text) return '';
                    text = text
                        .replace(/：/g, ':')
                        .replace(/／/g, '/')
                        .replace(/．/g, '.')
                        .replace(/　/g, '')
                        .replace(/\s+/g, '')
                        .replace(/[，。；;、）)\]>》]+$/g, '');
                    if (/^www\./i.test(text)) {
                        text = `https://${text}`;
                    }
                    try {
                        const url = new URL(text);
                        if (!/^https?:$/i.test(url.protocol)) return '';
                        return url.toString();
                    } catch (_) {
                        return '';
                    }
                },
                isPreviewRowNoise(itemName) {
                    const normalized = this.normalizeText(itemName).replace(/\s+/g, '');
                    if (!normalized) return true;
                    if (/^[#＃]+$/.test(normalized)) return true;

                    const exactNoise = new Set([
                        '物品名称',
                        '数量',
                        '关联链接',
                        '采购链接',
                        '备注',
                        '序号',
                        '操作',
                    ]);
                    if (exactNoise.has(normalized)) return true;

                    if (
                        normalized.includes('物品名称')
                        && normalized.includes('数量')
                        && (normalized.includes('关联链接') || normalized.includes('采购链接'))
                    ) {
                        return true;
                    }
                    return false;
                },
                normalizePreviewData(data) {
                    const items = Array.isArray(data?.items) ? data.items : [];
                    return {
                        serial_number: this.normalizeSerial(data?.serial_number),
                        department: this.normalizeText(data?.department),
                        handler: this.normalizeText(data?.handler),
                        request_date: this.normalizeDateText(data?.request_date),
                        items: items
                            .map((item) => {
                                const qty = Number(item?.quantity);
                                const rawLink = (item?.purchase_link || '').toString();
                                const normalizedLink = this.normalizeUrlText(rawLink);
                                return {
                                    item_name: this.normalizeText(item?.item_name),
                                    quantity: Number.isFinite(qty) && qty > 0 ? qty : 1,
                                    purchase_link: normalizedLink || this.normalizeText(rawLink),
                                };
                            })
                            .filter((item) => !this.isPreviewRowNoise(item.item_name))
                    };
                },
                openImportPreview(data) {
                    this.importPreview = this.normalizePreviewData(data);
                    this.showAddModal = false;
                    this.showDuplicateModal = false;
                    this.showImportPreviewModal = true;
                },
                closeImportPreview() {
                    this.showImportPreviewModal = false;
                    this.pendingDuplicates = [];
                    this.pendingParsedData = null;
                    this.importSubmitting = false;
                },
                addPreviewItem() {
                    this.importPreview.items.push({
                        item_name: '',
                        quantity: 1,
                        purchase_link: '',
                    });
                },
                removePreviewItem(index) {
                    this.importPreview.items.splice(index, 1);
                },
                sanitizeImportPayload(data) {
                    const normalized = this.normalizePreviewData(data);
                    const items = normalized.items
                        .filter((item) => item.item_name)
                        .map((item) => ({
                            item_name: this.normalizeText(item.item_name),
                            quantity: Number.isFinite(Number(item.quantity)) && Number(item.quantity) > 0 ? Number(item.quantity) : 1,
                            purchase_link: this.normalizeUrlText(item.purchase_link) || null,
                        }));
                    return {
                        serial_number: this.normalizeSerial(normalized.serial_number),
                        department: this.normalizeText(normalized.department),
                        handler: this.normalizeText(normalized.handler),
                        request_date: this.normalizeDateText(normalized.request_date),
                        items,
                    };
                },
                validateImportPayload(payload) {
                    const required = [
                        ['serial_number', '流水号'],
                        ['department', '申领部门'],
                        ['handler', '经办人'],
                        ['request_date', '申领日期'],
                    ];
                    const missing = required
                        .filter(([key]) => !this.normalizeText(payload[key]))
                        .map(([, label]) => label);
                    if (missing.length) {
                        throw new Error(`请先补全字段：${missing.join('、')}`);
                    }
                },
                closeDuplicateModal() {
                    this.showDuplicateModal = false;
                    if (this.pendingParsedData) {
                        this.openImportPreview(this.pendingParsedData);
                    }
                    this.pendingDuplicates = [];
                    this.pendingParsedData = null;
                },
                async loadAutocomplete() {
                    try {
                        const res = await axios.get('/api/autocomplete');
                        this.departments = res.data.departments || [];
                        this.handlers = res.data.handlers || [];
                        if (Array.isArray(res.data.statuses) && res.data.statuses.length) {
                            this.statuses = res.data.statuses;
                        }
                        if (Array.isArray(res.data.payment_statuses) && res.data.payment_statuses.length) {
                            this.paymentStatuses = res.data.payment_statuses;
                        }
                    } catch(e) {
                        console.error(e);
                    }
                },
                async loadItems() {
                    try {
                        const params = {
                            page: this.currentPage,
                            page_size: this.pageSize,
                        };
                        if (this.filterKeyword) params.keyword = this.filterKeyword;
                        if (this.filterStatus) params.status = this.filterStatus;
                        if (this.filterDepartment) params.department = this.filterDepartment;
                        if (this.filterMonth) params.month = this.filterMonth;
                        const res = await axios.get('/api/items', { params });
                        this.items = Array.isArray(res.data.items) ? res.data.items : [];
                        this.totalItems = typeof res.data.total === 'number' ? res.data.total : this.items.length;
                        this.selectedItems = [];
                        this.selectAll = false;

                        const maxPage = Math.max(1, Math.ceil(this.totalItems / this.pageSize));
                        if (this.currentPage > maxPage) {
                            this.currentPage = maxPage;
                            await this.loadItems();
                        }
                    }
                    catch(e) { console.error(e); }
                },
                async loadStats() {
                    try { const res = await axios.get('/api/stats'); this.stats = res.data; }
                    catch(e) { console.error(e); }
                },
                handleFilter() {
                    this.currentPage = 1;
                    this.loadItems();
                },
                goToPage(page) {
                    if (page < 1 || page > this.totalPages || page === this.currentPage) return;
                    this.currentPage = page;
                    this.loadItems();
                },
                changePageSize() {
                    if (!this.pageSize || this.pageSize < 1) this.pageSize = 20;
                    this.currentPage = 1;
                    this.loadItems();
                },
                jumpToPage() {
                    const page = Number(this.jumpPage);
                    if (!Number.isInteger(page)) return;
                    const target = Math.min(this.totalPages, Math.max(1, page));
                    this.jumpPage = null;
                    this.goToPage(target);
                },
                clearFilters() {
                    this.filterKeyword = '';
                    this.filterStatus = '';
                    this.filterDepartment = '';
                    this.filterMonth = '';
                    this.handleFilter();
                },
                exportExcel() {
                    const params = new URLSearchParams();
                    if (this.filterKeyword) params.append('keyword', this.filterKeyword);
                    if (this.filterStatus) params.append('status', this.filterStatus);
                    if (this.filterDepartment) params.append('department', this.filterDepartment);
                    if (this.filterMonth) params.append('month', this.filterMonth);
                    const query = params.toString();
                    const url = query ? `/api/export?${query}` : '/api/export';
                    const newWindow = window.open(url, '_blank');
                    if (!newWindow) window.location.href = url;
                },
                normalizeItemUpdatePayload(data) {
                    const payload = { ...data };
                    const fieldLabels = {
                        serial_number: '流水号',
                        department: '申领部门',
                        handler: '经办人',
                        item_name: '物品名称',
                        status: '状态',
                        payment_status: '付款状态',
                    };
                    for (const field of ['serial_number', 'department', 'handler', 'item_name', 'status', 'payment_status']) {
                        if (Object.prototype.hasOwnProperty.call(payload, field)) {
                            const value = this.normalizeText(payload[field]);
                            if (!value) {
                                throw new Error(`${fieldLabels[field] || field} 不能为空`);
                            }
                            payload[field] = field === 'serial_number' ? value.toUpperCase().replace(/\s+/g, '') : value;
                        }
                    }
                    if (Object.prototype.hasOwnProperty.call(payload, 'purchase_link')) {
                        const raw = (payload.purchase_link || '').toString().trim();
                        if (!raw) {
                            payload.purchase_link = null;
                        } else {
                            const normalizedUrl = this.normalizeUrlText(raw);
                            if (!normalizedUrl) {
                                throw new Error('采购链接必须是有效的 http(s) URL');
                            }
                            payload.purchase_link = normalizedUrl;
                        }
                    }
                    if (Object.prototype.hasOwnProperty.call(payload, 'quantity')) {
                        const qty = Number(payload.quantity);
                        if (!Number.isFinite(qty) || qty <= 0) {
                            throw new Error('数量必须大于 0');
                        }
                        payload.quantity = qty;
                    }
                    if (Object.prototype.hasOwnProperty.call(payload, 'unit_price')) {
                        if (payload.unit_price === '' || payload.unit_price === null || payload.unit_price === undefined) {
                            payload.unit_price = null;
                        } else {
                            const unitPrice = Number(payload.unit_price);
                            if (!Number.isFinite(unitPrice) || unitPrice < 0) {
                                throw new Error('单价不能为负数');
                            }
                            payload.unit_price = unitPrice;
                        }
                    }
                    return payload;
                },
                async updateItem(id, data) {
                    try {
                        const payload = this.normalizeItemUpdatePayload(data);
                        await axios.put(`/api/items/${id}`, payload);
                        await this.loadStats();
                    }
                    catch(e) {
                        alert('更新失败: ' + (e.response?.data?.detail || e.message));
                        await this.loadItems();
                    }
                },
                async deleteItem(id) {
                    if (!confirm('确定删除吗？')) return;
                    try { await axios.delete(`/api/items/${id}`); await this.loadItems(); await this.loadStats(); }
                    catch(e) { alert('删除失败'); }
                },
                async toggleInvoice(item) {
                    item.invoice_issued = !item.invoice_issued;
                    await this.updateItem(item.id, { invoice_issued: item.invoice_issued });
                },
                backupData() {
                    const url = '/api/backup';
                    const newWindow = window.open(url, '_blank');
                    if (!newWindow) window.location.href = url;
                },
                handleRestoreSelect(e) {
                    const files = e.target.files;
                    if (files.length) this.restoreFromBackup(files[0]);
                    e.target.value = '';
                },
                async restoreFromBackup(file) {
                    const ext = (file.name.split('.').pop() || '').toLowerCase();
                    if (ext !== 'zip') {
                        alert('请选择 .zip 备份文件');
                        return;
                    }
                    if (!confirm('恢复会覆盖当前数据库和上传文件，是否继续？')) {
                        return;
                    }

                    this.restoring = true;
                    try {
                        const formData = new FormData();
                        formData.append('file', file);
                        const res = await axios.post('/api/restore', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' }
                        });
                        alert(res.data.message || '恢复成功');
                        await this.loadAutocomplete();
                        await this.loadItems();
                        await this.loadStats();
                    } catch(e) {
                        alert('恢复失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.restoring = false;
                    }
                },
                handleFileSelect(e) { const files = e.target.files; if (files.length) this.uploadFile(files[0]); },
                async uploadFile(file) {
                    const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
                    const validExts = ['pdf', 'png', 'jpg', 'jpeg', 'jfif'];
                    const ext = (file.name.split('.').pop() || '').toLowerCase();
                    if (!validTypes.includes(file.type) && !validExts.includes(ext)) {
                        this.error = '仅支持 PDF 或 图片格式';
                        return;
                    }
                    this.uploading = true;
                    this.error = null;
                    this.parseResult = null;
                    try {
                        const formData = new FormData();
                        formData.append('file', file);
                        const res = await axios.post('/api/upload', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' }
                        });
                        this.openImportPreview(res.data.parsed_data);
                    } catch(e) {
                        console.error('上传错误:', e);
                        this.error = '上传失败: ' + (e.response?.data?.detail || e.message);
                    } finally {
                        this.uploading = false;
                    }
                },
                toggleSelectAll() { this.selectedItems = this.selectAll ? this.items.map(i => i.id) : []; },
                onBatchFieldChange() {
                    this.batchEditValue = '';
                },
                buildBatchUpdatePayload() {
                    if (!this.batchEditField) {
                        throw new Error('请先选择要批量修改的字段');
                    }
                    if (this.batchEditField === 'status' || this.batchEditField === 'payment_status') {
                        const value = (this.batchEditValue || '').toString().trim();
                        if (!value) throw new Error('请选择批量修改值');
                        return { [this.batchEditField]: value };
                    }
                    if (this.batchEditField === 'invoice_issued') {
                        if (this.batchEditValue !== '1' && this.batchEditValue !== '0') {
                            throw new Error('请选择发票状态');
                        }
                        return { invoice_issued: this.batchEditValue === '1' };
                    }
                    if (this.batchEditField === 'department' || this.batchEditField === 'handler') {
                        const value = (this.batchEditValue || '').toString().trim();
                        if (!value) throw new Error('批量修改值不能为空');
                        return { [this.batchEditField]: value };
                    }
                    throw new Error('不支持的批量修改字段');
                },
                async batchUpdate() {
                    if (!this.selectedItems.length) return;
                    try {
                        const updates = this.buildBatchUpdatePayload();
                        if (!confirm(`确认批量修改 ${this.selectedItems.length} 条记录？`)) return;
                        const res = await axios.post('/api/items/batch-update', {
                            ids: this.selectedItems,
                            updates,
                        });
                        alert(res.data?.message || '批量修改完成');
                        await this.loadItems();
                        await this.loadStats();
                        await this.loadAutocomplete();
                        this.batchEditValue = '';
                    } catch (e) {
                        alert('批量修改失败: ' + (e.response?.data?.detail || e.message));
                    }
                },
                async batchDelete() {
                    if (!confirm(`删除 ${this.selectedItems.length} 条记录？`)) return;
                    try {
                        await Promise.all(this.selectedItems.map(id => axios.delete(`/api/items/${id}`)));
                        this.selectedItems = [];
                        this.batchEditValue = '';
                        await this.loadItems();
                        await this.loadStats();
                    }
                    catch(e) { alert('删除失败'); }
                },
                async submitImport(duplicateAction = null) {
                    const source = duplicateAction ? this.pendingParsedData : this.importPreview;
                    if (!source) {
                        alert('没有可导入的数据');
                        return;
                    }
                    const payload = this.sanitizeImportPayload(source);
                    try {
                        this.validateImportPayload(payload);
                    } catch (e) {
                        alert(e.message);
                        return;
                    }
                    if (!payload.items.length) {
                        alert('请至少保留一条有效物品明细');
                        return;
                    }

                    this.importSubmitting = true;
                    try {
                        const res = await axios.post('/api/import/confirm', {
                            ...payload,
                            duplicate_action: duplicateAction,
                        });
                        if (res.data.has_duplicates) {
                            this.pendingDuplicates = res.data.duplicates || [];
                            this.pendingParsedData = payload;
                            this.showImportPreviewModal = false;
                            this.showDuplicateModal = true;
                            return;
                        }

                        this.showImportPreviewModal = false;
                        this.showDuplicateModal = false;
                        this.pendingDuplicates = [];
                        this.pendingParsedData = null;
                        this.parseResult = res.data.parsed_data;
                        this.importPreview = {
                            serial_number: '',
                            department: '',
                            handler: '',
                            request_date: '',
                            items: []
                        };
                        await this.loadItems();
                        await this.loadStats();
                    } catch(e) {
                        alert('导入失败: ' + (e.response?.data?.detail || e.message));
                    } finally {
                        this.importSubmitting = false;
                    }
                },
                async handleDuplicates(action) {
                    await this.submitImport(action);
                },
                async manualAdd() {
                    try {
                        const quantity = Number(this.newItem.quantity);
                        if (!Number.isFinite(quantity) || quantity <= 0) {
                            alert('数量必须大于 0');
                            return;
                        }

                        const requestDate = this.normalizeDateText(this.newItem.request_date);
                        const department = this.normalizeText(this.newItem.department);
                        const handler = this.normalizeText(this.newItem.handler);
                        const itemName = this.normalizeText(this.newItem.item_name);
                        if (!requestDate || !department || !handler || !itemName) {
                            alert('请补全 申领日期 / 申领部门 / 经办人 / 物品名称');
                            return;
                        }

                        const rawLink = (this.newItem.purchase_link || '').toString().trim();
                        const normalizedLink = this.normalizeUrlText(rawLink);
                        if (rawLink && !normalizedLink) {
                            alert('采购链接必须是有效的 http(s) URL');
                            return;
                        }

                        // 如果用户没填流水号，自动生成一个
                        let sn = this.normalizeSerial(this.newItem.serial_number);
                        if (!sn) {
                            const now = new Date();
                            const ts = now.toISOString().replace(/[-:T]/g, '').slice(2, 12);
                            sn = `REQ-${ts}`;
                        }

                        const payload = {
                            ...this.newItem,
                            serial_number: sn,
                            request_date: requestDate,
                            department,
                            handler,
                            item_name: itemName,
                            quantity,
                            purchase_link: normalizedLink || null,
                        };
                        
                        if (payload.unit_price === '' || payload.unit_price === undefined) {
                            payload.unit_price = null;
                        }
                        await axios.post('/api/items', payload);
                        this.closeAddModal();

                        // 商务友好重置：保留部门、经办人、日期，只清空物品、数量、单价和链接，方便连续录入
                        this.newItem = {
                            serial_number: '', 
                            department,
                            handler,
                            request_date: requestDate,
                            item_name: '',
                            quantity: 1,
                            unit_price: null,
                            purchase_link: ''
                        };
                        await this.loadItems();
                        await this.loadStats();
                    } catch(e) {
                        alert('添加失败: ' + (e.response?.data?.detail || e.message));
                    }
                }
            },
    };
})(window);
