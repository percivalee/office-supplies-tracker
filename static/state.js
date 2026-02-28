(function (global) {
    global.AppState = {
        data() {
                return {
                    items: [],
                    totalItems: 0,
                    stats: { total: 0, status_count: {}, payment_count: {}, invoice_count: { issued: 0, not_issued: 0 }},
                    statuses: ['待采购', '已下单', '待到货', '待分发', '已分发'],
                    departments: [],
                    handlers: [],
                    paymentStatuses: ['未付款', '已付款', '已报销'],
                    filterKeyword: '',
                    filterStatus: '',
                    filterDepartment: '',
                    filterMonth: '',
                    currentView: 'dashboard',
                    executionLoading: false,
                    boardKeyword: '',
                    boardDepartment: '',
                    boardMonth: '',
                    executionBoard: {
                        columns: [],
                        total: 0,
                        limit_per_status: 80,
                    },
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
                    restoring: false,
                    importSubmitting: false,
                    parseResult: null,
                    error: null,
                    showAddModal: false,  // 确保初始化为 false
                    showWebdavModal: false,
                    webdavLoading: false,
                    webdavConfig: {
                        configured: false,
                        base_url: '',
                        username: '',
                        password: '',
                        remote_dir: '',
                        has_password: false,
                    },
                    webdavBackups: [],
                    webdavSelectedBackup: '',
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
                            total_records: 0,
                            total_amount: 0,
                            priced_amount: 0,
                            missing_price_records: 0
                        },
                        by_department: [],
                        by_status: [],
                        by_month: []
                    },
                    historyLoading: false,
                    historyItems: [],
                    historyTotal: 0,
                    historyPage: 1,
                    historyPageSize: 20,
                    historyKeyword: '',
                    historyAction: '',
                    historyMonth: '',
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
            },
        mounted() {
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
            },
    };
})(window);
