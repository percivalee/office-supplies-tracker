(function (global) {
    global.AppState = {
        data() {
                return {
                    items: [],
                    totalItems: 0,
                    stats: { total: 0, status_count: {}, payment_count: {}, invoice_count: { issued: 0, not_issued: 0 }},
                    statuses: ['待采购', '已采购', '已到货', '已发放'],
                    departments: [],
                    handlers: [],
                    paymentStatuses: ['未付款', '已付款', '已报销'],
                    filterKeyword: '',
                    filterStatus: '',
                    filterDepartment: '',
                    filterMonth: '',
                    currentPage: 1,
                    pageSize: 20,
                    pageSizeOptions: [20, 50, 100],
                    jumpPage: null,
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
                    showAmountReportModal: false,
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
                    showHistoryModal: false,
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
                historyTotalPages() {
                    return Math.max(1, Math.ceil(this.historyTotal / this.historyPageSize));
                },
            },
        mounted() {
                this.loadAutocomplete();
                this.loadItems();
                this.loadStats();
            },
    };
})(window);
