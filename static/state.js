(function (global) {
    global.AppState = {
        data() {
                return {
                    items: [],
                    totalItems: 0,
                    stats: { total: 0, statusCount: {}, paymentCount: {}, invoiceCount: { issued: 0, notIssued: 0 }},
                    statuses: ['待采购', '待到货', '待分发', '已分发'],
                    departments: [],
                    handlers: [],
                    paymentStatuses: ['未付款', '已付款', '已报销'],
                    filterKeyword: '',
                    filterStatus: '',
                    filterDepartment: '',
                    filterMonth: '',
                    appVersion: '1.2.3',
                    currentView: 'dashboard',
                    executionLoading: false,
                    boardKeyword: '',
                    boardDepartment: '',
                    boardMonth: '',
                    executionBoard: {
                        columns: [],
                        total: 0,
                        limitPerStatus: 80,
                    },
                    draggingExecutionId: null,
                    draggingExecutionFromKey: '',
                    executionDropTargetKey: '',
                    reportsInitialized: false,
                    auditInitialized: false,
                    executionInitialized: false,
                    hashChangeListener: null,
                    currentPage: 1,
                    pageSize: 20,
                    pageSizeOptions: [20, 50, 100],
                    jumpPage: null,
                    inlineEditId: null,
                    inlineEditField: '',
                    inlineEditCommitting: false,
                    inlineEditRefs: {},
                    toasts: [],
                    nextToastId: 1,
                    toastTimers: [],
                    confirmModalVisible: false,
                    confirmModalTitle: '请确认',
                    confirmModalMessage: '',
                    confirmModalConfirmText: '确认',
                    confirmModalCancelText: '取消',
                    confirmModalDanger: false,
                    confirmModalResolver: null,
                    uploading: false,
                    ocrEngine: 'local',
                    llmProtocol: 'openai',
                    llmApiKey: '',
                    llmModelName: '',
                    llmBaseUrl: '',
                    uploadTaskId: '',
                    uploadPollTimer: null,
                    uploadPollInFlight: false,
                    uploadStatusText: '智能深度扫描中，请稍候',
                    restoring: false,
                    importSubmitting: false,
                    parseResult: null,
                    error: null,
                    showAddModal: false,
                    showWebdavModal: false,
                    webdavLoading: false,
                    webdavConfig: {
                        configured: false,
                        baseUrl: '',
                        username: '',
                        password: '',
                        remoteDir: '',
                        keepBackups: 0,
                        hasPassword: false,
                    },
                    webdavBackups: [],
                    webdavSelectedBackup: '',
                    showRecycleBinModal: false,
                    recycleBinLoading: false,
                    recycleBinKeyword: '',
                    recycleBinItems: [],
                    recycleBinTotal: 0,
                    recycleBinPage: 1,
                    recycleBinPageSize: 20,
                    showDataQualityModal: false,
                    dataQualityLoading: false,
                    dataQualityLimit: 200,
                    dataQualityReport: {
                        summary: {},
                        issues: [],
                        duplicates: [],
                        scannedRows: 0,
                    },
                    focusedLedgerItemId: null,
                    focusedLedgerItemTimer: null,
                    showImportPreviewModal: false,
                    selectedItems: [],
                    selectAll: false,
                    batchEditField: '',
                    batchEditValue: '',
                    showDuplicateModal: false,
                    pendingDuplicates: [],
                    pendingParsedData: null,
                    amountReportLoading: false,
                    amountReport: {
                        summary: {
                            totalRecords: 0,
                            totalAmount: 0,
                            pricedAmount: 0,
                            missingPriceRecords: 0
                        },
                        byDepartment: [],
                        byStatus: [],
                        byMonth: []
                    },
                    operationsReport: {
                        funnel: [],
                        cycleDistribution: {
                            requestToArrival: {
                                buckets: [],
                                averageDays: 0,
                                sampleSize: 0,
                            },
                            arrivalToDistribution: {
                                buckets: [],
                                averageDays: 0,
                                sampleSize: 0,
                            },
                        },
                        monthlyAmountTrend: [],
                    },
                    historyLoading: false,
                    historyItems: [],
                    historyTotal: 0,
                    historyPage: 1,
                    historyPageSize: 20,
                    historyKeyword: '',
                    historyAction: '',
                    historyMonth: '',
                    showLedgerDetailModal: false,
                    ledgerDetailItem: null,
                    ledgerDetailLoading: false,
                    ledgerDetailAuditLoading: false,
                    ledgerDetailAuditLogs: [],
                    ledgerDetailAuditTotal: 0,
                    ledgerDetailAuditPage: 1,
                    ledgerDetailAuditPageSize: 20,
                    importPreview: {
                        serial_number: '',
                        department: '',
                        handler: '',
                        request_date: '',
                        items: []
                    },
                    newItem: {
                        serial_number: '', department: '', handler: '',
                        request_date: new Date().toISOString().split('T')[0],
                        item_name: '', quantity: 1, unit_price: null, purchase_link: ''
                    }
                };
            },
        computed: {
                totalPages() { return Math.max(1, Math.ceil(this.totalItems / this.pageSize)); },
                latestItems() {
                    return [...(this.items || [])]
                        .sort((a, b) => (Number(b?.id) || 0) - (Number(a?.id) || 0))
                        .slice(0, 5);
                },
                pageRangeStart() {
                    if (!this.totalItems) return 0;
                    return (this.currentPage - 1) * this.pageSize + 1;
                },
                pageRangeEnd() {
                    if (!this.totalItems) return 0;
                    return Math.min(this.currentPage * this.pageSize, this.totalItems);
                },
                pageTokens() {
                    const total = this.totalPages;
                    const current = this.currentPage;
                    if (total <= 7) {
                        return Array.from({ length: total }, (_, i) => i + 1);
                    }

                    const pages = new Set([1, total, current - 1, current, current + 1]);
                    if (current <= 3) {
                        pages.add(2);
                        pages.add(3);
                        pages.add(4);
                    }
                    if (current >= total - 2) {
                        pages.add(total - 1);
                        pages.add(total - 2);
                        pages.add(total - 3);
                    }

                    const sorted = [...pages]
                        .filter((page) => page >= 1 && page <= total)
                        .sort((a, b) => a - b);

                    const tokens = [];
                    let prev = 0;
                    for (const page of sorted) {
                        if (prev && page - prev > 1) {
                            tokens.push('ellipsis');
                        }
                        tokens.push(page);
                        prev = page;
                    }
                    return tokens;
                },
                historyTotalPages() {
                    return Math.max(1, Math.ceil(this.historyTotal / this.historyPageSize));
                },
                ledgerDetailAuditTotalPages() {
                    return Math.max(1, Math.ceil(this.ledgerDetailAuditTotal / this.ledgerDetailAuditPageSize));
                },
                reportDepartmentRows() {
                    const rows = Array.isArray(this.amountReport?.byDepartment)
                        ? this.amountReport.byDepartment
                        : [];
                    const normalized = rows.map((row, idx) => {
                        const amount = Number(row?.total_amount) || 0;
                        return {
                            ...row,
                            _rank: idx + 1,
                            _amount: amount,
                        };
                    });
                    const maxAmount = normalized.reduce(
                        (max, row) => Math.max(max, row._amount),
                        0
                    );
                    const totalAmount = Number(this.amountReport?.summary?.totalAmount) || 0;
                    return normalized
                        .sort((a, b) => b._amount - a._amount)
                        .slice(0, 10)
                        .map((row, idx) => ({
                            ...row,
                            _rank: idx + 1,
                            _ratio: maxAmount > 0 ? (row._amount / maxAmount) * 100 : 0,
                            _share: totalAmount > 0 ? (row._amount / totalAmount) * 100 : 0,
                        }));
                },
                reportStatusRows() {
                    const palette = [
                        '#f59e0b',
                        '#2563eb',
                        '#0891b2',
                        '#4f46e5',
                        '#16a34a',
                        '#64748b',
                    ];
                    const rows = Array.isArray(this.amountReport?.byStatus)
                        ? this.amountReport.byStatus
                        : [];
                    const normalized = rows.map((row, idx) => ({
                        ...row,
                        _amount: Number(row?.total_amount) || 0,
                        _color: palette[idx % palette.length],
                    }));
                    const totalAmount = normalized.reduce((sum, row) => sum + row._amount, 0);
                    return normalized.map((row) => ({
                        ...row,
                        _share: totalAmount > 0 ? (row._amount / totalAmount) * 100 : 0,
                    }));
                },
                reportStatusDonutStyle() {
                    const rows = this.reportStatusRows;
                    if (!rows.length) {
                        return { background: '#e2e8f0' };
                    }
                    const totalShare = rows.reduce((sum, row) => sum + row._share, 0);
                    if (totalShare <= 0) {
                        return { background: '#e2e8f0' };
                    }
                    let cursor = 0;
                    const segments = rows.map((row) => {
                        const start = cursor;
                        cursor += row._share;
                        const end = Math.min(100, cursor);
                        return `${row._color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
                    });
                    return {
                        background: `conic-gradient(${segments.join(', ')})`,
                    };
                },
                reportMonthRows() {
                    const rows = Array.isArray(this.amountReport?.byMonth)
                        ? this.amountReport.byMonth
                        : [];
                    const normalized = rows
                        .map((row) => ({
                            ...row,
                            _amount: Number(row?.total_amount) || 0,
                        }))
                        .sort((a, b) => String(a?.month || '').localeCompare(String(b?.month || '')))
                        .slice(-12);
                    const maxAmount = normalized.reduce((max, row) => Math.max(max, row._amount), 0);
                    return normalized.map((row) => ({
                        ...row,
                        _barHeight: maxAmount > 0 ? Math.max(16, (row._amount / maxAmount) * 150) : 16,
                    }));
                },
                reportFunnelRows() {
                    const rows = Array.isArray(this.operationsReport?.funnel)
                        ? this.operationsReport.funnel
                        : [];
                    const normalized = rows.map((row) => ({
                        ...row,
                        _count: Number(row?.count) || 0,
                    }));
                    const maxCount = normalized.reduce((max, row) => Math.max(max, row._count), 0);
                    const firstCount = Number(normalized[0]?._count) || 0;
                    return normalized.map((row, idx) => ({
                        ...row,
                        _ratio: maxCount > 0 ? (row._count / maxCount) * 100 : 0,
                        _conversion: firstCount > 0 ? (row._count / firstCount) * 100 : 0,
                        _stepDrop: idx > 0 ? Math.max(0, (normalized[idx - 1]?._count || 0) - row._count) : 0,
                    }));
                },
                requestToArrivalRows() {
                    const rows = Array.isArray(this.operationsReport?.cycleDistribution?.requestToArrival?.buckets)
                        ? this.operationsReport.cycleDistribution.requestToArrival.buckets
                        : [];
                    const normalized = rows.map((row) => ({
                        ...row,
                        _count: Number(row?.count) || 0,
                    }));
                    const maxCount = normalized.reduce((max, row) => Math.max(max, row._count), 0);
                    return normalized.map((row) => ({
                        ...row,
                        _ratio: maxCount > 0 ? (row._count / maxCount) * 100 : 0,
                    }));
                },
                arrivalToDistributionRows() {
                    const rows = Array.isArray(this.operationsReport?.cycleDistribution?.arrivalToDistribution?.buckets)
                        ? this.operationsReport.cycleDistribution.arrivalToDistribution.buckets
                        : [];
                    const normalized = rows.map((row) => ({
                        ...row,
                        _count: Number(row?.count) || 0,
                    }));
                    const maxCount = normalized.reduce((max, row) => Math.max(max, row._count), 0);
                    return normalized.map((row) => ({
                        ...row,
                        _ratio: maxCount > 0 ? (row._count / maxCount) * 100 : 0,
                    }));
                },
                reportMonthlyTrendRows() {
                    const rows = Array.isArray(this.operationsReport?.monthlyAmountTrend)
                        ? this.operationsReport.monthlyAmountTrend
                        : [];
                    const normalized = rows
                        .map((row) => {
                            const totalAmount = Number(row?.totalAmount) || 0;
                            const paidAmount = Number(row?.paidAmount) || 0;
                            const unpaidAmount = Number(row?.unpaidAmount) || 0;
                            return {
                                ...row,
                                _totalAmount: totalAmount,
                                _paidAmount: paidAmount,
                                _unpaidAmount: unpaidAmount,
                            };
                        })
                        .sort((a, b) => String(a?.month || '').localeCompare(String(b?.month || '')))
                        .slice(-12);

                    const maxAmount = normalized.reduce((max, row) => Math.max(max, row._totalAmount), 0);
                    const maxHeight = 150;
                    return normalized.map((row) => {
                        const totalHeight = maxAmount > 0 ? (row._totalAmount / maxAmount) * maxHeight : 0;
                        const displayHeight = row._totalAmount > 0 ? Math.max(16, totalHeight) : 0;
                        const otherAmount = Math.max(0, row._totalAmount - row._paidAmount - row._unpaidAmount);
                        const baseAmount = row._totalAmount > 0 ? row._totalAmount : 1;
                        const paidHeight = displayHeight * (row._paidAmount / baseAmount);
                        const unpaidHeight = displayHeight * (row._unpaidAmount / baseAmount);
                        const otherHeight = displayHeight * (otherAmount / baseAmount);
                        return {
                            ...row,
                            _otherAmount: otherAmount,
                            _totalHeight: displayHeight,
                            _paidHeight: row._paidAmount > 0 ? paidHeight : 0,
                            _unpaidHeight: row._unpaidAmount > 0 ? unpaidHeight : 0,
                            _otherHeight: otherAmount > 0 ? otherHeight : 0,
                        };
                    });
                },
            },
        watch: {
                ocrEngine(next) {
                    // 设计意图：记录当前解析引擎，保证刷新后仍沿用用户选择。
                    try {
                        const value = (next === 'cloud' || next === 'local') ? next : 'local';
                        window.localStorage.setItem('ocr_engine', value);
                    } catch (_) {
                    }
                },
                llmApiKey(next) {
                    // 设计意图：按协议隔离存储 API Key，避免切换协议后串用凭证。
                    try {
                        if (typeof this.persistLlmProtocolField === 'function') {
                            this.persistLlmProtocolField('api_key', next);
                            return;
                        }
                        const protocol = (typeof this.normalizeLlmProtocol === 'function')
                            ? this.normalizeLlmProtocol(this.llmProtocol)
                            : ((this.llmProtocol === 'google' || this.llmProtocol === 'openai' || this.llmProtocol === 'anthropic')
                                ? this.llmProtocol
                                : 'openai');
                        window.localStorage.setItem(
                            `llm_${protocol}_api_key`,
                            (next || '').toString()
                        );
                    } catch (_) {
                    }
                },
                llmProtocol(next) {
                    // 设计意图：协议切换时自动装载该协议的专属配置，减少重复输入。
                    try {
                        const value = (typeof this.normalizeLlmProtocol === 'function')
                            ? this.normalizeLlmProtocol(next)
                            : ((next === 'google' || next === 'openai' || next === 'anthropic') ? next : 'openai');
                        window.localStorage.setItem('llm_protocol', value);
                        if (value === 'google' && typeof this.migrateLegacyGoogleConfig === 'function') {
                            this.migrateLegacyGoogleConfig();
                        }
                        if (typeof this.applyStoredLlmConfigForProtocol === 'function') {
                            this.applyStoredLlmConfigForProtocol(value);
                            return;
                        }
                        this.llmApiKey = window.localStorage.getItem(`llm_${value}_api_key`) || '';
                        this.llmModelName = window.localStorage.getItem(`llm_${value}_model_name`) || '';
                        this.llmBaseUrl = window.localStorage.getItem(`llm_${value}_base_url`) || '';
                    } catch (_) {
                    }
                },
                llmModelName(next) {
                    // 设计意图：模型名与协议绑定保存，便于不同供应商独立维护默认模型。
                    try {
                        if (typeof this.persistLlmProtocolField === 'function') {
                            this.persistLlmProtocolField('model_name', next);
                            return;
                        }
                        const protocol = (typeof this.normalizeLlmProtocol === 'function')
                            ? this.normalizeLlmProtocol(this.llmProtocol)
                            : ((this.llmProtocol === 'google' || this.llmProtocol === 'openai' || this.llmProtocol === 'anthropic')
                                ? this.llmProtocol
                                : 'openai');
                        window.localStorage.setItem(
                            `llm_${protocol}_model_name`,
                            (next || '').toString()
                        );
                    } catch (_) {
                    }
                },
                llmBaseUrl(next) {
                    // 设计意图：为每个协议单独保存中转地址/网关地址，避免误用。
                    try {
                        if (typeof this.persistLlmProtocolField === 'function') {
                            this.persistLlmProtocolField('base_url', next);
                            return;
                        }
                        const protocol = (typeof this.normalizeLlmProtocol === 'function')
                            ? this.normalizeLlmProtocol(this.llmProtocol)
                            : ((this.llmProtocol === 'google' || this.llmProtocol === 'openai' || this.llmProtocol === 'anthropic')
                                ? this.llmProtocol
                                : 'openai');
                        window.localStorage.setItem(
                            `llm_${protocol}_base_url`,
                            (next || '').toString()
                        );
                    } catch (_) {
                    }
                },
            },
        mounted() {
                if (typeof this.initOcrEngineSettings === 'function') {
                    this.initOcrEngineSettings();
                }
                this.loadAutocomplete();
                this.loadItems();
                this.loadStats();
                this.initViewRouting();
            },
        beforeUnmount() {
                if (this.hashChangeListener) {
                    window.removeEventListener('hashchange', this.hashChangeListener);
                    this.hashChangeListener = null;
                }
                for (const timer of this.toastTimers) {
                    clearTimeout(timer);
                }
                this.toastTimers = [];
                if (this.confirmModalResolver) {
                    this.confirmModalResolver(false);
                    this.confirmModalResolver = null;
                }
                if (this.uploadPollTimer) {
                    clearInterval(this.uploadPollTimer);
                    this.uploadPollTimer = null;
                }
                if (this.focusedLedgerItemTimer) {
                    clearTimeout(this.focusedLedgerItemTimer);
                    this.focusedLedgerItemTimer = null;
                }
            },
    };
})(window);
