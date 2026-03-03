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
                initOcrEngineSettings() {
                    try {
                        const engine = (window.localStorage.getItem('ocr_engine') || '').trim().toLowerCase();
                        this.ocrEngine = (engine === 'cloud' || engine === 'local')
                            ? engine
                            : ((engine === 'gemini') ? 'cloud' : 'local');
                        const protocol = (window.localStorage.getItem('llm_protocol') || '').trim().toLowerCase();
                        this.llmProtocol = (protocol === 'google' || protocol === 'openai' || protocol === 'anthropic')
                            ? protocol
                            : 'openai';
                        this.llmApiKey = window.localStorage.getItem('llm_api_key')
                            || window.localStorage.getItem('gemini_api_key')
                            || '';
                        this.llmModelName = window.localStorage.getItem('llm_model_name')
                            || window.localStorage.getItem('gemini_model_name')
                            || '';
                        this.llmBaseUrl = window.localStorage.getItem('llm_base_url')
                            || window.localStorage.getItem('gemini_base_url')
                            || '';
                    } catch (_) {
                        this.ocrEngine = 'local';
                        this.llmProtocol = 'openai';
                        this.llmApiKey = '';
                        this.llmModelName = '';
                        this.llmBaseUrl = '';
                    }
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
                isValidView(view) {
                    return ['dashboard', 'ledger', 'execution', 'reports', 'audit', 'settings'].includes(view);
                },
                normalizeView(view) {
                    return this.isValidView(view) ? view : 'dashboard';
                },
                getViewFromHash() {
                    const raw = (window.location.hash || '')
                        .replace(/^#\/?/, '')
                        .trim()
                        .toLowerCase();
                    return this.normalizeView(raw || 'dashboard');
                },
                setViewHash(view, replace = false) {
                    const normalized = this.normalizeView(view);
                    const hash = `#/${normalized}`;
                    if (window.location.hash === hash) return;
                    if (replace && window.history?.replaceState) {
                        const base = `${window.location.pathname}${window.location.search}`;
                        window.history.replaceState(null, '', `${base}${hash}`);
                    } else {
                        window.location.hash = hash;
                    }
                },
                ensureViewData(view, forceReload = false) {
                    const normalized = this.normalizeView(view);
                    if (normalized === 'execution') {
                        if (forceReload || !this.executionInitialized) {
                            this.loadExecutionBoard();
                        }
                        return;
                    }
                    if (normalized === 'reports') {
                        if (forceReload || !this.reportsInitialized) {
                            this.loadAmountReport();
                        }
                        return;
                    }
                    if (normalized === 'audit') {
                        if (forceReload || !this.auditInitialized) {
                            this.historyPage = 1;
                            this.loadHistory();
                        }
                    }
                },
                switchView(view, forceReload = false, syncHash = true) {
                    const normalized = this.normalizeView(view);
                    this.currentView = normalized;
                    if (syncHash) {
                        this.setViewHash(normalized);
                    }
                    this.ensureViewData(normalized, forceReload);
                },
                handleHashChange() {
                    const nextView = this.getViewFromHash();
                    this.switchView(nextView, false, false);
                },
                initViewRouting() {
                    const nextView = this.getViewFromHash();
                    this.switchView(nextView, false, false);
                    this.setViewHash(nextView, true);
                    if (this.hashChangeListener) {
                        window.removeEventListener('hashchange', this.hashChangeListener);
                    }
                    this.hashChangeListener = () => this.handleHashChange();
                    window.addEventListener('hashchange', this.hashChangeListener);
                },
                async loadExecutionBoard() {
                    this.executionInitialized = true;
                    this.executionLoading = true;
                    try {
                        const params = {
                            limit_per_status: this.executionBoard.limitPerStatus || 80,
                        };
                        if (this.boardKeyword) params.keyword = this.boardKeyword;
                        if (this.boardDepartment) params.department = this.boardDepartment;
                        if (this.boardMonth) params.month = this.boardMonth;
                        const res = await axios.get('/api/execution-board', { params });
                        const data = res.data || {};
                        this.executionBoard = {
                            columns: Array.isArray(data.columns) ? data.columns : [],
                            total: Number(data.total) || 0,
                            limitPerStatus: Number(data.limit_per_status) || 80,
                        };
                        this.draggingExecutionId = null;
                        this.draggingExecutionFromKey = '';
                        this.executionDropTargetKey = '';
                    } catch (e) {
                        this.showApiError('加载执行看板失败', e);
                    } finally {
                        this.executionLoading = false;
                    }
                },
                async refreshExecutionBoardIfNeeded() {
                    if (!this.executionInitialized) return;
                    await this.loadExecutionBoard();
                },
                async refreshDataViews(options = {}) {
                    const {
                        items = true,
                        stats = true,
                        execution = true,
                        autocomplete = false,
                    } = options;
                    const tasks = [];
                    if (items) tasks.push(this.loadItems());
                    if (stats) tasks.push(this.loadStats());
                    if (execution) tasks.push(this.refreshExecutionBoardIfNeeded());
                    if (autocomplete) tasks.push(this.loadAutocomplete());
                    if (!tasks.length) return;
                    await Promise.all(tasks);
                },
                getErrorDetail(error, fallback = '未知错误') {
                    return error?.response?.data?.detail || error?.message || fallback;
                },
                showApiError(prefix, error) {
                    this.showToast(`${prefix}: ${this.getErrorDetail(error)}`, 'error');
                },
                applyExecutionFilter() {
                    this.loadExecutionBoard();
                },
                clearExecutionFilter() {
                    this.boardKeyword = '';
                    this.boardDepartment = '';
                    this.boardMonth = '';
                    this.loadExecutionBoard();
                },
                onExecutionDragStart(event, item, column) {
                    if (!item?.id) return;
                    this.draggingExecutionId = Number(item.id);
                    this.draggingExecutionFromKey = column?.key || '';
                    this.executionDropTargetKey = '';
                    if (event?.dataTransfer) {
                        event.dataTransfer.effectAllowed = 'move';
                        event.dataTransfer.dropEffect = 'move';
                        event.dataTransfer.setData('text/plain', String(item.id));
                        event.dataTransfer.setData('application/x-office-item-id', String(item.id));
                        event.dataTransfer.setData(
                            'application/x-office-from-column',
                            this.draggingExecutionFromKey
                        );
                    }
                },
                onExecutionDragOver(event, column) {
                    if (event?.dataTransfer) {
                        event.dataTransfer.dropEffect = 'move';
                    }
                    this.executionDropTargetKey = column?.key || '';
                },
                onExecutionDragEnter(column) {
                    this.executionDropTargetKey = column?.key || '';
                },
                onExecutionDragLeave(event, column) {
                    const currentTarget = event?.currentTarget;
                    const relatedTarget = event?.relatedTarget;
                    if (
                        currentTarget &&
                        relatedTarget &&
                        typeof currentTarget.contains === 'function' &&
                        currentTarget.contains(relatedTarget)
                    ) {
                        return;
                    }
                    if (this.executionDropTargetKey === (column?.key || '')) {
                        this.executionDropTargetKey = '';
                    }
                },
                onExecutionDragEnd() {
                    this.draggingExecutionId = null;
                    this.draggingExecutionFromKey = '';
                    this.executionDropTargetKey = '';
                },
                extractExecutionDragId(event) {
                    const transfer = event?.dataTransfer;
                    const rawValue = (
                        transfer?.getData('application/x-office-item-id') ||
                        transfer?.getData('text/plain') ||
                        this.draggingExecutionId
                    );
                    const itemId = Number(rawValue);
                    if (!Number.isFinite(itemId) || itemId <= 0) return null;
                    return itemId;
                },
                findExecutionItemById(itemId) {
                    const id = Number(itemId);
                    const columns = Array.isArray(this.executionBoard?.columns)
                        ? this.executionBoard.columns
                        : [];
                    for (const column of columns) {
                        const list = Array.isArray(column?.items) ? column.items : [];
                        const found = list.find((row) => Number(row?.id) === id);
                        if (found) {
                            return found;
                        }
                    }
                    return null;
                },
                buildExecutionDragTransition(item, targetStatus) {
                    const nextStatus = this.normalizeText(targetStatus);
                    const currentStatus = this.normalizeText(item?.status);
                    if (!nextStatus || !item?.id || currentStatus === nextStatus) {
                        return null;
                    }
                    if (nextStatus === '待分发') {
                        const arrivalDate = this.normalizeDateText(
                            item.arrival_date || this.todayDateText()
                        );
                        if (!/^\d{4}-\d{2}-\d{2}$/.test(arrivalDate)) {
                            throw new Error('请先填写有效的到货日期，再拖拽到“待分发”');
                        }
                        return {
                            patch: {
                                status: nextStatus,
                                arrival_date: arrivalDate,
                            },
                            successMessage: '已拖拽流转到“待分发”',
                        };
                    }
                    return {
                        patch: { status: nextStatus },
                        successMessage: `已拖拽流转到“${nextStatus}”`,
                    };
                },
                async onExecutionDrop(event, column) {
                    const targetKey = column?.key || '';
                    const targetStatus = column?.status || '';
                    const itemId = this.extractExecutionDragId(event);
                    const sourceKey = (
                        this.draggingExecutionFromKey ||
                        event?.dataTransfer?.getData('application/x-office-from-column') ||
                        ''
                    );

                    this.executionDropTargetKey = '';
                    if (!itemId || !targetStatus || (sourceKey && sourceKey === targetKey)) {
                        this.onExecutionDragEnd();
                        return;
                    }

                    const item = this.findExecutionItemById(itemId);
                    if (!item) {
                        this.onExecutionDragEnd();
                        return;
                    }

                    try {
                        const transition = this.buildExecutionDragTransition(item, targetStatus);
                        if (!transition) {
                            return;
                        }
                        await this.updateExecutionItem(
                            item,
                            transition.patch,
                            transition.successMessage
                        );
                    } catch (e) {
                        this.showToast(
                            '拖拽流转失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'),
                            'error'
                        );
                    } finally {
                        this.onExecutionDragEnd();
                    }
                },
                todayDateText() {
                    const now = new Date();
                    const mm = String(now.getMonth() + 1).padStart(2, '0');
                    const dd = String(now.getDate()).padStart(2, '0');
                    return `${now.getFullYear()}-${mm}-${dd}`;
                },
                async updateExecutionItem(item, patch, successMessage = '状态已更新') {
                    if (!item?.id) return false;
                    const ok = await this.updateItem(item.id, patch);
                    if (!ok) return false;
                    await this.refreshDataViews({ items: false });
                    this.showToast(successMessage, 'success');
                    return true;
                },
                async moveToOrdered(item) {
                    await this.updateExecutionItem(item, { status: '已下单' }, '已流转到“已下单”');
                },
                async moveToPendingArrival(item) {
                    await this.updateExecutionItem(item, { status: '待到货' }, '已流转到“待到货”');
                },
                async markArrived(item) {
                    const arrivalDate = this.normalizeDateText(item.arrival_date || this.todayDateText());
                    if (!/^\d{4}-\d{2}-\d{2}$/.test(arrivalDate)) {
                        this.showToast('请填写有效的到货日期', 'error');
                        return;
                    }
                    item.arrival_date = arrivalDate;
                    await this.updateExecutionItem(
                        item,
                        { status: '待分发', arrival_date: arrivalDate },
                        '已标记到货，流转到“待分发”'
                    );
                },
                async completeDistribution(item) {
                    const distributionDate = this.normalizeDateText(item.distribution_date || this.todayDateText());
                    if (!/^\d{4}-\d{2}-\d{2}$/.test(distributionDate)) {
                        this.showToast('请填写有效的分发日期', 'error');
                        return;
                    }
                    const signoffNote = this.normalizeText(item.signoff_note);
                    item.distribution_date = distributionDate;
                    item.signoff_note = signoffNote;
                    await this.updateExecutionItem(
                        item,
                        {
                            status: '已分发',
                            distribution_date: distributionDate,
                            signoff_note: signoffNote || null,
                        },
                        '已完成分发闭环'
                    );
                },
                isInlineEditing(id, field) {
                    return this.inlineEditId === id && this.inlineEditField === field;
                },
                setInlineEditRef(id, field, el) {
                    const key = `${id}:${field}`;
                    if (el) {
                        this.inlineEditRefs[key] = el;
                    } else {
                        delete this.inlineEditRefs[key];
                    }
                },
                startInlineEdit(id, field) {
                    this.inlineEditId = id;
                    this.inlineEditField = field;
                    this.inlineEditCommitting = false;
                    this.$nextTick(() => {
                        const key = `${id}:${field}`;
                        const input = this.inlineEditRefs[key];
                        if (input) {
                            input.focus();
                            if (typeof input.select === 'function') {
                                input.select();
                            }
                        }
                    });
                },
                cancelInlineEdit() {
                    this.inlineEditId = null;
                    this.inlineEditField = '';
                    this.inlineEditCommitting = false;
                },
                showToast(message, type = 'success', duration = 2200, action = null) {
                    const text = (message || '').toString().trim();
                    if (!text) return;
                    const id = this.nextToastId++;
                    const toast = { id, message: text, type };
                    if (action && action.label && typeof action.handler === 'function') {
                        toast.actionLabel = action.label;
                        toast.actionHandler = action.handler;
                    }
                    this.toasts.push(toast);
                    const timer = setTimeout(() => {
                        this.toasts = this.toasts.filter((toast) => toast.id !== id);
                        this.toastTimers = this.toastTimers.filter((t) => t !== timer);
                    }, duration);
                    this.toastTimers.push(timer);
                },
                async triggerToastAction(toastId) {
                    const toast = this.toasts.find((t) => t.id === toastId);
                    if (!toast || typeof toast.actionHandler !== 'function') return;
                    this.toasts = this.toasts.filter((t) => t.id !== toastId);
                    try {
                        await toast.actionHandler();
                    } catch (e) {
                        this.showToast('操作失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'), 'error');
                    }
                },
                showSuccessToast(message) {
                    this.showToast(message || '更新成功', 'success');
                },
                openConfirmDialog(options = {}) {
                    const {
                        title = '请确认',
                        message = '确认继续此操作？',
                        confirmText = '确认',
                        cancelText = '取消',
                        danger = false,
                    } = options;

                    if (this.confirmModalResolver) {
                        this.confirmModalResolver(false);
                    }

                    this.confirmModalTitle = title;
                    this.confirmModalMessage = message;
                    this.confirmModalConfirmText = confirmText;
                    this.confirmModalCancelText = cancelText;
                    this.confirmModalDanger = !!danger;
                    this.confirmModalVisible = true;

                    return new Promise((resolve) => {
                        this.confirmModalResolver = resolve;
                    });
                },
                resolveConfirmDialog(result) {
                    const resolver = this.confirmModalResolver;
                    this.confirmModalVisible = false;
                    this.confirmModalResolver = null;
                    if (resolver) resolver(!!result);
                },
                cancelConfirmDialog() {
                    this.resolveConfirmDialog(false);
                },
                acceptConfirmDialog() {
                    this.resolveConfirmDialog(true);
                },
                async commitInlineEdit(item, field) {
                    if (!item || !this.isInlineEditing(item.id, field) || this.inlineEditCommitting) {
                        return;
                    }
                    this.inlineEditCommitting = true;
                    const ok = await this.updateItem(item.id, { [field]: item[field] });
                    this.inlineEditCommitting = false;
                    this.inlineEditId = null;
                    this.inlineEditField = '';
                    if (ok) {
                        this.showSuccessToast(field === 'quantity' ? '数量已更新' : '单价已更新');
                    }
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
                normalizeKeepBackups(value) {
                    const parsed = Number(value);
                    if (!Number.isFinite(parsed) || parsed < 0) {
                        return 0;
                    }
                    return Math.min(365, Math.floor(parsed));
                },
                async loadWebdavConfig() {
                    try {
                        const res = await axios.get('/api/webdav/config');
                        const config = res.data || {};
                        this.webdavConfig = {
                            configured: !!config.configured,
                            baseUrl: config.base_url || '',
                            username: config.username || '',
                            password: '',
                            remoteDir: config.remote_dir || '',
                            keepBackups: this.normalizeKeepBackups(config.keep_backups),
                            hasPassword: !!config.has_password,
                        };
                    } catch (e) {
                        this.showApiError('加载 WebDAV 配置失败', e);
                    }
                },
                async saveWebdavConfig(showAlert = true, manageLoading = true) {
                    if (manageLoading) this.webdavLoading = true;
                    try {
                        const payload = {
                            base_url: (this.webdavConfig.baseUrl || '').toString().trim(),
                            username: (this.webdavConfig.username || '').toString().trim(),
                            password: this.webdavConfig.password || '',
                            remote_dir: (this.webdavConfig.remoteDir || '').toString().trim(),
                            keep_backups: this.normalizeKeepBackups(this.webdavConfig.keepBackups),
                        };
                        const res = await axios.put('/api/webdav/config', payload);
                        if (showAlert) {
                            this.showToast(res.data?.message || 'WebDAV 配置已保存', 'success');
                        }
                        const config = res.data?.config || {};
                        this.webdavConfig.configured = !!config.configured;
                        this.webdavConfig.hasPassword = !!config.has_password;
                        this.webdavConfig.keepBackups = this.normalizeKeepBackups(config.keep_backups);
                        this.webdavConfig.password = '';
                        return config;
                    } catch (e) {
                        if (showAlert) {
                            this.showApiError('保存 WebDAV 配置失败', e);
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
                        this.showToast(res.data?.message || '连接测试通过', 'success');
                    } catch (e) {
                        this.showApiError('WebDAV 测试失败', e);
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
                        this.showApiError('加载 WebDAV 备份列表失败', e);
                    } finally {
                        this.webdavLoading = false;
                    }
                },
                async uploadBackupToWebdav() {
                    this.webdavLoading = true;
                    try {
                        await this.saveWebdavConfig(false, false);
                        const res = await axios.post('/api/webdav/backup');
                        this.showToast(res.data?.message || '上传成功', 'success');
                        await this.loadWebdavBackups();
                    } catch (e) {
                        this.showApiError('上传 WebDAV 失败', e);
                    } finally {
                        this.webdavLoading = false;
                    }
                },
                async restoreFromWebdav(filename) {
                    const name = (filename || '').toString().trim();
                    if (!name) {
                        this.showToast('请先选择要恢复的备份', 'error');
                        return;
                    }
                    const ok = await this.openConfirmDialog({
                        title: '确认恢复云端备份',
                        message: `将从 ${name} 恢复；恢复前会自动执行健康检查，是否继续？`,
                        confirmText: '确认恢复',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) {
                        return;
                    }
                    this.webdavLoading = true;
                    this.restoring = true;
                    try {
                        await this.saveWebdavConfig(false, false);
                        const res = await axios.post('/api/webdav/restore', { filename: name });
                        this.showToast(res.data?.message || '恢复成功', 'success');
                        await this.refreshDataViews({ autocomplete: true });
                    } catch (e) {
                        this.showApiError('从 WebDAV 恢复失败', e);
                    } finally {
                        this.webdavLoading = false;
                        this.restoring = false;
                    }
                },
                async loadAmountReport() {
                    this.reportsInitialized = true;
                    this.amountReportLoading = true;
                    try {
                        const params = {};
                        if (this.filterKeyword) params.keyword = this.filterKeyword;
                        if (this.filterStatus) params.status = this.filterStatus;
                        if (this.filterDepartment) params.department = this.filterDepartment;
                        if (this.filterMonth) params.month = this.filterMonth;
                        const [amountResult, operationsResult] = await Promise.allSettled([
                            axios.get('/api/reports/amount', { params }),
                            axios.get('/api/reports/operations', { params }),
                        ]);
                        if (amountResult.status !== 'fulfilled') {
                            throw amountResult.reason;
                        }

                        const data = amountResult.value?.data || {};
                        const operations = operationsResult.status === 'fulfilled'
                            ? (operationsResult.value?.data || {})
                            : {};

                        if (operationsResult.status !== 'fulfilled') {
                            this.showToast('执行分析图加载失败，已展示金额报表', 'error');
                        }
                        this.amountReport = {
                            summary: {
                                totalRecords: data.summary?.total_records || 0,
                                totalAmount: data.summary?.total_amount || 0,
                                pricedAmount: data.summary?.priced_amount || 0,
                                missingPriceRecords: data.summary?.missing_price_records || 0
                            },
                            byDepartment: Array.isArray(data.by_department) ? data.by_department : [],
                            byStatus: Array.isArray(data.by_status) ? data.by_status : [],
                            byMonth: Array.isArray(data.by_month) ? data.by_month : []
                        };
                        this.operationsReport = {
                            funnel: Array.isArray(operations.funnel) ? operations.funnel : [],
                            cycleDistribution: {
                                requestToArrival: {
                                    buckets: Array.isArray(operations.cycle_distribution?.request_to_arrival?.buckets)
                                        ? operations.cycle_distribution.request_to_arrival.buckets
                                        : [],
                                    averageDays: Number(operations.cycle_distribution?.request_to_arrival?.average_days) || 0,
                                    sampleSize: Number(operations.cycle_distribution?.request_to_arrival?.sample_size) || 0,
                                },
                                arrivalToDistribution: {
                                    buckets: Array.isArray(operations.cycle_distribution?.arrival_to_distribution?.buckets)
                                        ? operations.cycle_distribution.arrival_to_distribution.buckets
                                        : [],
                                    averageDays: Number(operations.cycle_distribution?.arrival_to_distribution?.average_days) || 0,
                                    sampleSize: Number(operations.cycle_distribution?.arrival_to_distribution?.sample_size) || 0,
                                },
                            },
                            monthlyAmountTrend: Array.isArray(operations.monthly_amount_trend)
                                ? operations.monthly_amount_trend.map((row) => ({
                                    month: row.month || '',
                                    totalAmount: Number(row.total_amount) || 0,
                                    paidAmount: Number(row.paid_amount) || 0,
                                    unpaidAmount: Number(row.unpaid_amount) || 0,
                                    recordCount: Number(row.record_count) || 0,
                                }))
                                : [],
                        };
                    } catch (e) {
                        this.showApiError('加载金额报表失败', e);
                    } finally {
                        this.amountReportLoading = false;
                    }
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
                        arrival_date: '到货日期',
                        distribution_date: '分发日期',
                        signoff_note: '签收备注',
                        deleted_at: '删除时间',
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
                    this.auditInitialized = true;
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
                        this.showApiError('加载变更历史失败', e);
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
                canRollbackHistory(row) {
                    const itemId = Number(row?.item_id);
                    if (!Number.isFinite(itemId) || itemId <= 0) return false;
                    return row?.action === 'update' || row?.action === 'delete';
                },
                async rollbackHistoryRow(row) {
                    const itemId = Number(row?.item_id);
                    const historyId = Number(row?.id);
                    if (!this.canRollbackHistory(row) || !Number.isFinite(historyId) || historyId <= 0) {
                        this.showToast('该历史记录不支持回滚', 'error');
                        return;
                    }
                    const ok = await this.openConfirmDialog({
                        title: '确认回滚记录',
                        message: `将物品 #${itemId} 回滚到该历史版本，是否继续？`,
                        confirmText: '确认回滚',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) return;
                    try {
                        await axios.post(`/api/items/${itemId}/rollback`, { history_id: historyId });
                        this.showToast('回滚成功', 'success');
                        await Promise.all([
                            this.refreshDataViews({ autocomplete: true }),
                            this.loadHistory(),
                        ]);
                    } catch (e) {
                        this.showApiError('回滚失败', e);
                    }
                },
                async openRecycleBinModal() {
                    this.showRecycleBinModal = true;
                    this.recycleBinPage = 1;
                    await this.loadRecycleBin();
                },
                closeRecycleBinModal() {
                    this.showRecycleBinModal = false;
                },
                async loadRecycleBin() {
                    this.recycleBinLoading = true;
                    try {
                        const params = {
                            page: this.recycleBinPage,
                            page_size: this.recycleBinPageSize,
                        };
                        if (this.recycleBinKeyword) params.keyword = this.recycleBinKeyword;
                        const res = await axios.get('/api/recycle-bin', { params });
                        this.recycleBinItems = Array.isArray(res.data?.items) ? res.data.items : [];
                        this.recycleBinTotal = Number(res.data?.total) || 0;
                        const maxPage = Math.max(
                            1,
                            Math.ceil(this.recycleBinTotal / this.recycleBinPageSize)
                        );
                        if (this.recycleBinPage > maxPage) {
                            this.recycleBinPage = maxPage;
                            await this.loadRecycleBin();
                            return;
                        }
                    } catch (e) {
                        this.showApiError('加载回收站失败', e);
                    } finally {
                        this.recycleBinLoading = false;
                    }
                },
                async restoreFromRecycleBin(item) {
                    const itemId = Number(item?.id);
                    if (!Number.isFinite(itemId) || itemId <= 0) return;
                    const ok = await this.openConfirmDialog({
                        title: '确认恢复记录',
                        message: `将“${item?.item_name || `ID ${itemId}`}”恢复到台账，是否继续？`,
                        confirmText: '确认恢复',
                        cancelText: '取消',
                    });
                    if (!ok) return;
                    try {
                        await axios.post(`/api/items/${itemId}/restore`);
                        this.showToast('记录已恢复', 'success');
                        await Promise.all([
                            this.loadRecycleBin(),
                            this.refreshDataViews({ autocomplete: true }),
                        ]);
                    } catch (e) {
                        this.showApiError('恢复失败', e);
                    }
                },
                async purgeFromRecycleBin(item) {
                    const itemId = Number(item?.id);
                    if (!Number.isFinite(itemId) || itemId <= 0) return;
                    const ok = await this.openConfirmDialog({
                        title: '确认彻底删除',
                        message: `将彻底删除“${item?.item_name || `ID ${itemId}`}”，此操作不可撤销，是否继续？`,
                        confirmText: '彻底删除',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) return;
                    try {
                        await axios.delete(`/api/recycle-bin/${itemId}`);
                        this.showToast('已彻底删除', 'success');
                        await this.loadRecycleBin();
                    } catch (e) {
                        this.showApiError('彻底删除失败', e);
                    }
                },
                qualityIssueLabel(code) {
                    const labels = {
                        missing_department: '缺少部门',
                        missing_handler: '缺少经办人',
                        missing_request_date: '缺少申领日期',
                        invalid_quantity: '数量无效',
                        missing_purchase_link: '缺少采购链接',
                        invalid_purchase_link: '采购链接无效',
                        invalid_request_date_format: '日期格式异常',
                        duplicate_active_keys: '存在重复主键组',
                    };
                    return labels[code] || code;
                },
                async openDataQualityModal() {
                    this.showDataQualityModal = true;
                    await this.loadDataQualityReport();
                },
                closeDataQualityModal() {
                    this.showDataQualityModal = false;
                },
                async loadDataQualityReport() {
                    this.dataQualityLoading = true;
                    try {
                        const limit = Math.max(1, Math.min(1000, Number(this.dataQualityLimit) || 200));
                        this.dataQualityLimit = limit;
                        const res = await axios.get('/api/data-quality', {
                            params: { limit },
                        });
                        const report = res.data || {};
                        this.dataQualityReport = {
                            summary: report.summary || {},
                            issues: Array.isArray(report.issues) ? report.issues : [],
                            duplicates: Array.isArray(report.duplicates) ? report.duplicates : [],
                            scannedRows: Number(report.scanned_rows) || 0,
                        };
                    } catch (e) {
                        this.showApiError('加载数据质量报告失败', e);
                    } finally {
                        this.dataQualityLoading = false;
                    }
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

                    const headerTokens = ['序号', '物品', '名称', '数量', '关联链接', '采购链接', '备注', '操作'];
                    const hitCount = headerTokens.reduce(
                        (count, token) => count + (normalized.includes(token) ? 1 : 0),
                        0
                    );
                    if (hitCount >= 2) return true;
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
                    try {
                        const res = await axios.get('/api/stats');
                        const data = res.data || {};
                        this.stats = {
                            total: Number(data.total) || 0,
                            statusCount: data.status_count || {},
                            paymentCount: data.payment_count || {},
                            invoiceCount: {
                                issued: Number(data.invoice_count?.issued) || 0,
                                notIssued: Number(data.invoice_count?.not_issued) || 0,
                            },
                        };
                    }
                    catch(e) { console.error(e); }
                },
                handleFilter() {
                    this.currentPage = 1;
                    this.reportsInitialized = false;
                    this.loadItems();
                    if (this.currentView === 'reports') {
                        this.loadAmountReport();
                    }
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
                        signoff_note: '签收备注',
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
                    for (const field of ['signoff_note']) {
                        if (Object.prototype.hasOwnProperty.call(payload, field)) {
                            const value = this.normalizeText(payload[field]);
                            payload[field] = value || null;
                        }
                    }
                    for (const field of ['arrival_date', 'distribution_date']) {
                        if (Object.prototype.hasOwnProperty.call(payload, field)) {
                            const rawValue = (payload[field] || '').toString().trim();
                            if (!rawValue) {
                                payload[field] = null;
                                continue;
                            }
                            const normalizedDate = this.normalizeDateText(rawValue);
                            if (!/^\d{4}-\d{2}-\d{2}$/.test(normalizedDate)) {
                                throw new Error(`${field === 'arrival_date' ? '到货日期' : '分发日期'}格式应为 YYYY-MM-DD`);
                            }
                            payload[field] = normalizedDate;
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
                        await this.refreshDataViews({ items: false, execution: false });
                        return true;
                    }
                    catch(e) {
                        this.showApiError('更新失败', e);
                        await this.refreshDataViews({ stats: false });
                        return false;
                    }
                },
                async deleteItem(id) {
                    const ok = await this.openConfirmDialog({
                        title: '确认删除记录',
                        message: '记录将移入回收站，可在回收站恢复，是否继续？',
                        confirmText: '移入回收站',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) return;
                    try {
                        await axios.delete(`/api/items/${id}`);
                        await this.refreshDataViews();
                    }
                    catch(e) { this.showApiError('删除失败', e); }
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
                        this.showToast('请选择 .zip 备份文件', 'error');
                        return;
                    }
                    const ok = await this.openConfirmDialog({
                        title: '确认恢复本地备份',
                        message: '恢复前将自动执行健康检查；通过后会覆盖当前数据库和上传文件，是否继续？',
                        confirmText: '确认恢复',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) {
                        return;
                    }

                    this.restoring = true;
                    try {
                        const formData = new FormData();
                        formData.append('file', file);
                        const res = await axios.post('/api/restore', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' }
                        });
                        this.showToast(res.data.message || '恢复成功', 'success');
                        await this.refreshDataViews({ autocomplete: true });
                    } catch(e) {
                        this.showApiError('恢复失败', e);
                    } finally {
                        this.restoring = false;
                    }
                },
                clearUploadTaskPolling() {
                    if (this.uploadPollTimer) {
                        clearInterval(this.uploadPollTimer);
                        this.uploadPollTimer = null;
                    }
                    this.uploadPollInFlight = false;
                },
                updateUploadStatusText(status) {
                    if (status === 'pending') {
                        this.uploadStatusText = '任务排队中，等待后台解析...';
                        return;
                    }
                    if (status === 'processing') {
                        this.uploadStatusText = '正在提取关键字段...';
                        return;
                    }
                    if (status === 'completed') {
                        this.uploadStatusText = '解析完成，正在生成预览...';
                        return;
                    }
                    if (status === 'failed') {
                        this.uploadStatusText = '解析失败，请重试';
                        return;
                    }
                    this.uploadStatusText = '智能深度扫描中，请稍候';
                },
                async pollUploadTaskStatus(taskId) {
                    if (!taskId || this.uploadPollInFlight) return;
                    this.uploadPollInFlight = true;
                    try {
                        const res = await axios.get(`/api/tasks/${encodeURIComponent(taskId)}`);
                        const payload = res.data || {};
                        const status = (payload.status || '').toString().toLowerCase();
                        const result = payload.result || null;

                        if (status === 'pending' || status === 'processing') {
                            this.updateUploadStatusText(status);
                            return;
                        }

                        if (status === 'completed') {
                            this.updateUploadStatusText(status);
                            this.clearUploadTaskPolling();
                            this.uploading = false;
                            this.uploadTaskId = '';
                            this.parseResult = result?.parsed_data || null;
                            if (!this.parseResult) {
                                throw new Error('解析任务已完成，但未返回预览数据');
                            }
                            this.openImportPreview(this.parseResult);
                            this.showToast(result?.message || '解析完成，请确认后导入', 'success');
                            return;
                        }

                        if (status === 'failed') {
                            this.updateUploadStatusText(status);
                            this.clearUploadTaskPolling();
                            this.uploading = false;
                            this.uploadTaskId = '';
                            const detail = result?.detail || '解析失败，请稍后重试';
                            this.error = detail;
                            this.showToast(detail, 'error');
                            return;
                        }

                        throw new Error(`未知任务状态: ${payload.status}`);
                    } catch (e) {
                        this.clearUploadTaskPolling();
                        this.uploading = false;
                        this.uploadTaskId = '';
                        const detail = e?.response?.data?.detail || e?.message || '未知错误';
                        this.error = `任务查询失败: ${detail}`;
                        this.showToast(this.error, 'error');
                    } finally {
                        this.uploadPollInFlight = false;
                    }
                },
                startUploadTaskPolling(taskId) {
                    this.clearUploadTaskPolling();
                    this.uploadPollTimer = setInterval(() => {
                        this.pollUploadTaskStatus(taskId);
                    }, 2000);
                },
                handleFileSelect(e) {
                    const files = e.target.files;
                    if (files.length) this.uploadFile(files[0]);
                    e.target.value = '';
                },
                async uploadFile(file) {
                    if (this.uploading) {
                        this.showToast('已有解析任务正在执行，请稍候', 'error');
                        return;
                    }
                    const engine = (this.ocrEngine === 'cloud') ? 'cloud' : 'local';
                    const protocol = (this.llmProtocol === 'google' || this.llmProtocol === 'anthropic')
                        ? this.llmProtocol
                        : 'openai';
                    const apiKey = (this.llmApiKey || '').toString().trim();
                    const modelName = (this.llmModelName || '').toString().trim();
                    const baseUrl = (this.llmBaseUrl || '').toString().trim();
                    if (engine === 'cloud' && !apiKey) {
                        this.showToast('请先在系统设置中填写云端协议 API Key', 'error');
                        return;
                    }
                    const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
                    const validExts = ['pdf', 'png', 'jpg', 'jpeg', 'jfif'];
                    const ext = (file.name.split('.').pop() || '').toLowerCase();
                    if (!validTypes.includes(file.type) && !validExts.includes(ext)) {
                        this.error = '仅支持 PDF 或 图片格式';
                        this.showToast(this.error, 'error');
                        return;
                    }
                    this.clearUploadTaskPolling();
                    this.uploading = true;
                    this.uploadTaskId = '';
                    this.uploadStatusText = '正在上传文件并创建解析任务...';
                    this.error = null;
                    this.parseResult = null;
                    try {
                        const formData = new FormData();
                        formData.append('file', file);
                        formData.append('engine', engine);
                        formData.append('protocol', protocol);
                        formData.append('api_key', apiKey);
                        formData.append('model_name', modelName);
                        formData.append('base_url', baseUrl);
                        const res = await axios.post('/api/upload-ocr', formData, {
                            headers: { 'Content-Type': 'multipart/form-data' }
                        });
                        const taskId = (res.data?.task_id || '').toString().trim();
                        if (taskId) {
                            this.uploadTaskId = taskId;
                            this.uploadStatusText = '任务已创建，等待后台解析...';
                            await this.pollUploadTaskStatus(taskId);
                            if (this.uploading && this.uploadTaskId) {
                                this.startUploadTaskPolling(taskId);
                            }
                            return;
                        }

                        // 兼容同步返回（历史版本接口）
                        if (res.data?.parsed_data) {
                            this.uploading = false;
                            this.openImportPreview(res.data.parsed_data);
                            return;
                        }

                        throw new Error('服务端未返回 task_id');
                    } catch(e) {
                        console.error('上传错误:', e);
                        this.error = '上传失败: ' + (e.response?.data?.detail || e.message);
                        this.showToast(this.error, 'error');
                        this.clearUploadTaskPolling();
                        this.uploadTaskId = '';
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
                        const selectedIds = [...this.selectedItems];
                        const updatedField = Object.keys(updates)[0];
                        const previousValues = this.items
                            .filter((item) => selectedIds.includes(item.id))
                            .map((item) => ({ id: item.id, value: item[updatedField] }));
                        const ok = await this.openConfirmDialog({
                            title: '确认批量修改',
                            message: `确认批量修改 ${this.selectedItems.length} 条记录？`,
                            confirmText: '确认修改',
                            cancelText: '取消',
                            danger: false,
                        });
                        if (!ok) return;
                        const res = await axios.post('/api/items/batch-update', {
                            ids: this.selectedItems,
                            updates,
                        });
                        this.showToast(
                            res.data?.message || '批量修改完成',
                            'success',
                            8000,
                            {
                                label: '撤销',
                                handler: async () => {
                                    await Promise.all(
                                        previousValues.map(({ id, value }) =>
                                            axios.put(`/api/items/${id}`, this.normalizeItemUpdatePayload({ [updatedField]: value }))
                                        )
                                    );
                                    await this.refreshDataViews({ autocomplete: true });
                                    this.showToast('已撤销本次批量修改', 'success');
                                },
                            }
                        );
                        await this.refreshDataViews({ autocomplete: true });
                        this.batchEditValue = '';
                    } catch (e) {
                        this.showApiError('批量修改失败', e);
                    }
                },
                async batchDelete() {
                    const ok = await this.openConfirmDialog({
                        title: '确认批量删除',
                        message: `将 ${this.selectedItems.length} 条记录移入回收站，是否继续？`,
                        confirmText: '确认删除',
                        cancelText: '取消',
                        danger: true,
                    });
                    if (!ok) return;
                    try {
                        await Promise.all(this.selectedItems.map(id => axios.delete(`/api/items/${id}`)));
                        this.selectedItems = [];
                        this.batchEditValue = '';
                        await this.refreshDataViews();
                    }
                    catch(e) { this.showApiError('删除失败', e); }
                },
                async submitImport(duplicateAction = null) {
                    const source = duplicateAction ? this.pendingParsedData : this.importPreview;
                    if (!source) {
                        this.showToast('没有可导入的数据', 'error');
                        return;
                    }
                    const payload = this.sanitizeImportPayload(source);
                    try {
                        this.validateImportPayload(payload);
                    } catch (e) {
                        this.showToast(e.message, 'error');
                        return;
                    }
                    if (!payload.items.length) {
                        this.showToast('请至少保留一条有效物品明细', 'error');
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
                        await this.refreshDataViews();
                        this.showToast(res.data?.message || '导入完成', 'success');
                    } catch(e) {
                        this.showApiError('导入失败', e);
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
                            this.showToast('数量必须大于 0', 'error');
                            return;
                        }

                        const requestDate = this.normalizeDateText(this.newItem.request_date);
                        const department = this.normalizeText(this.newItem.department);
                        const handler = this.normalizeText(this.newItem.handler);
                        const itemName = this.normalizeText(this.newItem.item_name);
                        if (!requestDate || !department || !handler || !itemName) {
                            this.showToast('请补全 申领日期 / 申领部门 / 经办人 / 物品名称', 'error');
                            return;
                        }

                        const rawLink = (this.newItem.purchase_link || '').toString().trim();
                        const normalizedLink = this.normalizeUrlText(rawLink);
                        if (rawLink && !normalizedLink) {
                            this.showToast('采购链接必须是有效的 http(s) URL', 'error');
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
                        await this.refreshDataViews();
                        this.showToast('添加成功', 'success');
                    } catch(e) {
                        this.showApiError('添加失败', e);
                    }
                }
            },
    };
})(window);
