frappe.pages['cashout-requests'].on_page_load = function(wrapper) {
    if (!frappe.user_roles.includes('Accounts Manager')) {
        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Cashout Requests',
            single_column: true
        });

        page.main.html(`
            <div class="text-center mt-5">
                <div class="alert alert-warning">
                    <h4>Access Denied</h4>
                    <p>You do not have permission to access this page. Please contact your administrator to get the "Accounts Manager" role.</p>
                </div>
            </div>
        `);
        return;
    }

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Cashout Requests',
        single_column: true
    });

    new FlashCashoutManager(page);
};

const CashoutStatus = {
    PENDING: "Pending",
    PAID: "Paid",
    CANCELLED: "Cancelled",
    FAILED: "Failed"
};

const CASHOUT_STATUS_BADGE_MAP = {
    [CashoutStatus.PENDING]: 'cashout-badge-pending',
    [CashoutStatus.PAID]: 'cashout-badge-paid',
    [CashoutStatus.CANCELLED]: 'cashout-badge-cancelled',
    [CashoutStatus.FAILED]: 'cashout-badge-failed'
};

function getCashoutStatusBadgeClass(status) {
    return CASHOUT_STATUS_BADGE_MAP[status] || 'cashout-badge-pending';
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

class FlashCashoutManager {
    constructor(page) {
        this.page = page;
        this.selected_request = null;
        this.cashout_requests = [];
        this.current_page = 1;
        this.page_size = 10;
        this.total_pages = 1;
        this.total_count = 0;
        this.$cache = {};
        this.setup_page();
    }

    setup_page() {
        this.create_layout();
        this.cache_elements();
        this.bind_events();
        this.load_cashout_requests();
    }

    cache_elements() {
        const main = this.page.main;
        this.$cache = {
            searchInput: main.find('.search-input'),
            requestsLoading: main.find('.requests-loading'),
            requestsTable: main.find('.requests-list table'),
            noRequests: main.find('.no-requests'),
            requestDetails: main.find('.request-details'),
            paginationControls: main.find('.pagination-controls'),
            requestsTbody: main.find('.requests-tbody'),
            searchLoading: main.find('.search-loading'),
            searchError: main.find('.search-error'),
            filterStatus: main.find('#filter-status')
        };
    }

    create_layout() {
        this.page.main.html(`
            <style>
                .flash-cashout-manager {
                    --color-primary: #007856;
                    --color-background: #F1F1F1;
                    --color-layer: #FFFFFF;
                    --color-text01: #212121;
                    --color-text02: #939998;
                    --color-border01: #DDE3E1;
                    --color-green: #00A700;
                    --color-error: #DC2626;
                    --color-warning: #F59E0B;
                }

                .flash-cashout-manager {
                    max-width: 1400px;
                    margin: 0 auto;
                }

                .flash-cashout-manager .modern-search-card {
                    background: var(--color-layer);
                    border-radius: 16px;
                    padding: 24px;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
                    border: 1px solid var(--color-border01);
                    margin-bottom: 24px;
                }

                .flash-cashout-manager .modern-search-wrapper {
                    display: flex;
                    gap: 12px;
                    align-items: center;
                }

                .flash-cashout-manager .modern-search-input {
                    flex: 1;
                    max-width: 450px;
                    padding: 12px 16px;
                    border: 2px solid var(--color-border01);
                    border-radius: 12px;
                    font-size: 15px;
                    transition: all 0.2s ease;
                    background: var(--color-layer);
                    color: var(--color-text01);
                }

                .flash-cashout-manager .modern-search-input:focus {
                    outline: none;
                    border-color: var(--color-primary);
                    box-shadow: 0 0 0 3px rgba(0, 120, 86, 0.1);
                }

                .flash-cashout-manager .modern-search-input::placeholder {
                    color: var(--color-text02);
                }

                .flash-cashout-manager .modern-search-select {
                    max-width: 250px;
                }

                .flash-cashout-manager .modern-btn {
                    padding: 12px 24px;
                    border-radius: 12px;
                    font-weight: 500;
                    font-size: 15px;
                    border: none;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    display: inline-flex;
                    align-items: center;
                    gap: 8px;
                }

                .flash-cashout-manager .modern-btn-primary {
                    background: var(--color-primary);
                    color: white;
                }

                .flash-cashout-manager .modern-btn-primary:hover {
                    background: #005a42;
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0, 120, 86, 0.2);
                }

                .flash-cashout-manager .modern-btn-secondary {
                    background: var(--color-layer);
                    color: var(--color-text01);
                    border: 2px solid var(--color-border01);
                }

                .flash-cashout-manager .modern-btn-secondary:hover {
                    background: var(--color-background);
                    border-color: var(--color-text02);
                }

                .flash-cashout-manager .modern-requests-card {
                    background: var(--color-layer);
                    border-radius: 16px;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
                    border: 1px solid var(--color-border01);
                    overflow: hidden;
                    margin-bottom: 24px;
                }

                .flash-cashout-manager .modern-card-header {
                    padding: 20px 24px;
                    background: linear-gradient(135deg, var(--color-primary) 0%, #005a42 100%);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }

                .flash-cashout-manager .modern-card-title {
                    font-size: 20px;
                    font-weight: 600;
                    color: white;
                    margin: 0;
                }

                .flash-cashout-manager .modern-table-wrapper {
                    overflow-x: auto;
                }

                .flash-cashout-manager .modern-table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                }

                .flash-cashout-manager .modern-table thead {
                    background: var(--color-background);
                }

                .flash-cashout-manager .modern-table th {
                    padding: 16px 20px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border-bottom: 2px solid var(--color-border01);
                }

                .flash-cashout-manager .modern-table tbody tr {
                    cursor: pointer;
                    transition: all 0.2s ease;
                    border-bottom: 1px solid var(--color-border01);
                }

                .flash-cashout-manager .modern-table tbody tr:hover {
                    background: rgba(0, 120, 86, 0.03);
                }

                .flash-cashout-manager .modern-table tbody tr.selected {
                    background: rgba(0, 120, 86, 0.15) !important;
                    border-left: 4px solid var(--color-primary);
                }

                .flash-cashout-manager .modern-table td {
                    padding: 16px 20px;
                    color: var(--color-text01);
                    font-size: 14px;
                }

                .flash-cashout-manager .modern-badge {
                    display: inline-flex;
                    align-items: center;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }

                .flash-cashout-manager .cashout-badge-pending {
                    background: rgba(245, 158, 11, 0.15);
                    color: var(--color-warning);
                }

                .flash-cashout-manager .cashout-badge-paid {
                    background: #d4f7d9;
                    color: #15803d;
                }

                .flash-cashout-manager .cashout-badge-cancelled {
                    background: rgba(100, 116, 139, 0.15);
                    color: #475569;
                }

                .flash-cashout-manager .cashout-badge-failed {
                    background: #fde2e2;
                    color: #b91c1c;
                }

                .flash-cashout-manager .no-requests {
                    padding: 60px 20px;
                    text-align: center;
                    color: var(--color-text02);
                }

                .flash-cashout-manager .no-requests-icon {
                    font-size: 48px;
                    margin-bottom: 16px;
                    opacity: 0.3;
                }

                .flash-cashout-manager .loading-spinner {
                    padding: 60px 20px;
                    text-align: center;
                }

                .flash-cashout-manager .spinner {
                    width: 40px;
                    height: 40px;
                    border: 3px solid var(--color-border01);
                    border-top-color: var(--color-primary);
                    border-radius: 50%;
                    animation: cashout-spin 0.8s linear infinite;
                    margin: 0 auto 16px;
                }

                @keyframes cashout-spin {
                    to { transform: rotate(360deg); }
                }

                .flash-cashout-manager .section-header {
                    font-size: 16px;
                    font-weight: 600;
                    color: var(--color-text01);
                    margin-bottom: 16px;
                    padding-bottom: 12px;
                    border-bottom: 2px solid var(--color-border01);
                }

                .flash-cashout-manager .detail-item {
                    margin-bottom: 16px;
                    display: flex;
                    flex-direction: column;
                    gap: 4px;
                }

                .flash-cashout-manager .detail-label {
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }

                .flash-cashout-manager .detail-value {
                    font-size: 15px;
                    color: var(--color-text01);
                    font-weight: 500;
                }

                .flash-cashout-manager .detail-link {
                    color: var(--color-primary);
                    text-decoration: none;
                    font-weight: 600;
                }

                .flash-cashout-manager .detail-link:hover {
                    text-decoration: underline;
                }

                .flash-cashout-manager .amount-display {
                    font-size: 20px;
                    font-weight: 700;
                    color: var(--color-primary);
                }

                @media (max-width: 768px) {
                    .flash-cashout-manager .modern-search-wrapper {
                        flex-direction: column;
                        align-items: stretch;
                    }

                    .flash-cashout-manager .modern-search-input {
                        max-width: 100%;
                        width: 100%;
                    }

                    .flash-cashout-manager .modern-btn {
                        width: 100%;
                        justify-content: center;
                    }

                    .flash-cashout-manager .modern-table th,
                    .flash-cashout-manager .modern-table td {
                        padding: 12px 10px;
                        font-size: 13px;
                    }

                    .flash-cashout-manager .modern-table-wrapper {
                        overflow-x: auto;
                    }

                    .flash-cashout-manager .request-details .card-body {
                        padding: 16px !important;
                    }

                    .flash-cashout-manager .request-details .d-flex {
                        flex-direction: column;
                    }

                    .flash-cashout-manager .request-details .d-flex button {
                        width: 100%;
                    }
                }
            </style>

            <div class="flash-cashout-manager m-3">
                <!-- Search & Filter -->
                <div class="modern-search-card">
                    <div class="modern-search-wrapper" style="margin-bottom: 20px;">
                        <input
                            type="text"
                            class="modern-search-input search-input"
                            placeholder="Enter username or phone number"
                        >
                        <button class="modern-btn modern-btn-primary btn-search">
                            <i class="fa fa-search"></i>
                            Search
                        </button>
                    </div>
                    <div class="modern-search-wrapper">
                        <select id="filter-status" class="modern-search-input modern-search-select">
                            <option value="">Status (All)</option>
                            <option value="${CashoutStatus.PENDING}">Pending</option>
                            <option value="${CashoutStatus.PAID}">Paid</option>
                            <option value="${CashoutStatus.CANCELLED}">Cancelled</option>
                            <option value="${CashoutStatus.FAILED}">Failed</option>
                        </select>
                    </div>
                </div>

                <!-- Cashout Requests Table -->
                <div class="modern-requests-card">
                    <div class="modern-card-header">
                        <h5 class="modern-card-title">
                            <i class="fa fa-money" style="margin-right: 10px;"></i>
                            Cashout Requests
                        </h5>
                        <button class="modern-btn modern-btn-secondary btn-refresh">
                            <i class="fa fa-refresh"></i>
                            Refresh
                        </button>
                    </div>
                    <div class="modern-table-wrapper">
                        <div class="requests-loading loading-spinner" style="display: none;">
                            <div class="spinner"></div>
                            <p style="color: var(--color-text02);">Loading requests...</p>
                        </div>

                        <div class="requests-list">
                            <table class="modern-table">
                                <thead>
                                    <tr>
                                        <th>Username</th>
                                        <th>Phone</th>
                                        <th>Send (USD)</th>
                                        <th>Receive (JMD)</th>
                                        <th>Status</th>
                                        <th>Submitted</th>
                                    </tr>
                                </thead>
                                <tbody class="requests-tbody">
                                    <!-- Populated dynamically -->
                                </tbody>
                            </table>
                            <div class="no-requests" style="display: none;">
                                <div class="no-requests-icon">💸</div>
                                <p style="font-size: 16px; font-weight: 500;">No cashout requests found</p>
                                <p style="font-size: 14px;">Cashout requests will appear here when submitted</p>
                            </div>
                        </div>
                    </div>
                    <!-- Pagination Controls -->
                    <div class="pagination-controls" style="display: none; padding: 16px 24px; border-top: 1px solid var(--color-border01); justify-content: space-between; align-items: center;">
                        <div class="pagination-info" style="color: var(--color-text02); font-size: 14px;">
                            Showing <span class="page-start">1</span>-<span class="page-end">10</span> of <span class="total-count">0</span> requests
                        </div>
                        <div class="pagination-buttons" style="display: flex; gap: 8px; align-items: center;">
                            <button class="modern-btn modern-btn-secondary btn-first-page" title="First page" style="padding: 8px 12px;">
                                <i class="fa fa-angle-double-left"></i>
                            </button>
                            <button class="modern-btn modern-btn-secondary btn-prev-page" title="Previous page" style="padding: 8px 12px;">
                                <i class="fa fa-angle-left"></i>
                            </button>
                            <span class="page-indicator" style="padding: 8px 16px; font-weight: 500; color: var(--color-text01);">
                                Page <span class="current-page">1</span> of <span class="total-pages">1</span>
                            </span>
                            <button class="modern-btn modern-btn-secondary btn-next-page" title="Next page" style="padding: 8px 12px;">
                                <i class="fa fa-angle-right"></i>
                            </button>
                            <button class="modern-btn modern-btn-secondary btn-last-page" title="Last page" style="padding: 8px 12px;">
                                <i class="fa fa-angle-double-right"></i>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Request Details Panel -->
                <div class="request-details modern-requests-card" style="display: none;">
                    <div class="modern-card-header">
                        <h5 class="modern-card-title">
                            <i class="fa fa-file-text-o" style="margin-right: 10px;"></i>
                            Cashout Details
                        </h5>
                        <button class="modern-btn modern-btn-secondary btn-close-details">
                            <i class="fa fa-times"></i>
                            Close
                        </button>
                    </div>
                    <div class="card-body" style="padding: 24px;">

                        <!-- User Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-user" style="margin-right: 8px; color: var(--color-primary);"></i>
                                User Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Username</span>
                                        <span class="detail-value detail-username"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Full Name</span>
                                        <span class="detail-value detail-fullname"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Phone</span>
                                        <span class="detail-value detail-phone"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Email</span>
                                        <span class="detail-value detail-email"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Cashout Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-exchange" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Cashout Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Offer ID</span>
                                        <span class="detail-value detail-offer-id"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Wallet ID</span>
                                        <span class="detail-value detail-wallet-id"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Send (USD)</span>
                                        <span class="detail-value amount-display detail-send"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Flash Fee</span>
                                        <span class="detail-value detail-flash-fee"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Exchange Rate</span>
                                        <span class="detail-value detail-exchange-rate"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Receive (JMD)</span>
                                        <span class="detail-value amount-display detail-receive-jmd"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Receive (USD)</span>
                                        <span class="detail-value detail-receive-usd"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Journal Entry</span>
                                        <span class="detail-value detail-journal-entry"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Bank Account -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-bank" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Bank Account
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Bank Account</span>
                                        <span class="detail-value detail-bank-account"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Bank Name</span>
                                        <span class="detail-value detail-bank-name"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Account Number</span>
                                        <span class="detail-value detail-account-number"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Account Type</span>
                                        <span class="detail-value detail-account-type"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Payment Entry (shown only when recorded) -->
                        <div class="detail-section detail-payment-entry-section mb-4" style="display: none;">
                            <h6 class="section-header">
                                <i class="fa fa-credit-card" style="margin-right: 8px; color: var(--color-green);"></i>
                                Payment Entry
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Payment Entry</span>
                                        <span class="detail-value detail-payment-entry"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Payment Amount</span>
                                        <span class="detail-value detail-pe-amount"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Payment Date</span>
                                        <span class="detail-value detail-pe-date"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Mode of Payment</span>
                                        <span class="detail-value detail-pe-mode"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Other Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-info-circle" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Other Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Status</span>
                                        <span class="detail-value detail-status"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Request ID</span>
                                        <span class="detail-value detail-request-id"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Submitted</span>
                                        <span class="detail-value detail-submitted"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Last Modified</span>
                                        <span class="detail-value detail-modified"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="d-flex gap-2 justify-content-end" style="gap: 12px;">
                            <button class="modern-btn modern-btn-primary btn-record-payment" style="background: var(--color-green);">
                                <i class="fa fa-credit-card"></i>
                                Record Payment Entry
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Search States -->
                <div class="search-loading loading-spinner" style="display: none;">
                    <div class="spinner"></div>
                    <p style="color: var(--color-text02);">Searching...</p>
                </div>

                <div class="search-error modern-search-card" style="display: none; background: rgba(220, 38, 38, 0.05); border-color: var(--color-error);">
                    <div style="color: var(--color-error); display: flex; align-items: center; gap: 12px;">
                        <i class="fa fa-exclamation-circle" style="font-size: 24px;"></i>
                        <span class="error-message"></span>
                    </div>
                </div>
            </div>
        `);
    }

    bind_events() {
        const main = this.page.main;

        const debouncedSearch = debounce(() => {
            if (this.$cache.searchInput.val().trim()) {
                this.search();
            } else {
                this.$cache.searchError.hide();
                this.load_cashout_requests();
            }
        }, 300);

        main.find('.btn-search').on('click', () => this.search());
        this.$cache.searchInput.on('keypress', (e) => { if (e.which === 13) this.search(); });
        this.$cache.searchInput.on('input', debouncedSearch);

        main.find('.btn-refresh').on('click', () => this.load_cashout_requests());
        main.find('.btn-close-details').on('click', () => this.close_details());
        main.find('.btn-record-payment').on('click', () => this.record_payment_entry(this.selected_request));

        this.$cache.filterStatus.on('change', () => { this.current_page = 1; this.load_cashout_requests(); });

        main.find('.btn-first-page').on('click', () => this.go_to_page(1));
        main.find('.btn-prev-page').on('click', () => this.go_to_page(this.current_page - 1));
        main.find('.btn-next-page').on('click', () => this.go_to_page(this.current_page + 1));
        main.find('.btn-last-page').on('click', () => this.go_to_page(this.total_pages));
    }

    create_request_row(req) {
        const statusBadge = getCashoutStatusBadgeClass(req.status);
        const displayStatus = req.status || CashoutStatus.PENDING;
        const sendDisplay = req.send != null
            ? `USD ${parseFloat(req.send).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
            : '-';
        const receiveJmdDisplay = req.receive_jmd != null
            ? `JMD ${parseFloat(req.receive_jmd).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
            : '-';

        const row = $(`
            <tr class="cashout-row" data-request-id="${req.name}">
                <td><strong>${req.username || '-'}</strong></td>
                <td>${this.formatPhone(req.phone_number)}</td>
                <td><strong>${sendDisplay}</strong></td>
                <td>${receiveJmdDisplay}</td>
                <td><span class="modern-badge ${statusBadge}">${displayStatus}</span></td>
                <td>${this.formatDateTime(req.creation)}</td>
            </tr>
        `);

        row.on('click', () => {
            this.page.main.find('.cashout-row').removeClass('selected');
            row.addClass('selected');
            this.show_request_details(req);
        });

        return row;
    }

    go_to_page(page) {
        if (page < 1 || page > this.total_pages) return;
        this.current_page = page;
        this.load_cashout_requests();
    }

    load_cashout_requests() {
        this.$cache.requestsLoading.show();
        this.$cache.requestsTable.hide();
        this.$cache.noRequests.hide();
        this.$cache.requestDetails.hide();
        this.$cache.paginationControls.hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.get_cashout_requests',
            args: {
                status: this.$cache.filterStatus.val(),
                page: this.current_page,
                page_size: this.page_size
            },
            callback: (response) => {
                this.$cache.requestsLoading.hide();
                const result = response.message || {};
                this.cashout_requests = result.data || [];
                this.total_count = result.total || 0;
                this.total_pages = result.total_pages || 1;
                this.current_page = result.page || 1;
                this.render_requests();
                this.update_pagination();
            },
            error: () => {
                this.$cache.requestsLoading.hide();
                frappe.show_alert({ message: 'Failed to load cashout requests', indicator: 'red' }, 5);
            }
        });
    }

    update_pagination() {
        if (this.total_count === 0) {
            this.$cache.paginationControls.hide();
            return;
        }

        this.$cache.paginationControls.css('display', 'flex');

        const start = (this.current_page - 1) * this.page_size + 1;
        const end = Math.min(this.current_page * this.page_size, this.total_count);
        const main = this.page.main;

        main.find('.page-start').text(start);
        main.find('.page-end').text(end);
        main.find('.total-count').text(this.total_count);
        main.find('.current-page').text(this.current_page);
        main.find('.total-pages').text(this.total_pages);

        main.find('.btn-first-page, .btn-prev-page').prop('disabled', this.current_page <= 1);
        main.find('.btn-next-page, .btn-last-page').prop('disabled', this.current_page >= this.total_pages);
    }

    render_requests() {
        this.$cache.requestsTbody.empty();

        if (this.cashout_requests.length === 0) {
            this.$cache.requestsTable.hide();
            this.$cache.noRequests.show();
            return;
        }

        this.$cache.requestsTable.show();
        this.$cache.noRequests.hide();

        this.cashout_requests.forEach((req) => {
            this.$cache.requestsTbody.append(this.create_request_row(req));
        });
    }

    show_request_details(req) {
        this.selected_request = req;
        const panel = this.page.main.find('.request-details');

        // User Information
        panel.find('.detail-username').text(req.username || '-');
        panel.find('.detail-fullname').text(req.full_name || '-');
        panel.find('.detail-phone').text(this.formatPhone(req.phone_number) || '-');
        panel.find('.detail-email').text(req.email || '-');

        // Cashout Information
        panel.find('.detail-offer-id').text(req.offer_id || '-');
        panel.find('.detail-wallet-id').text(req.wallet_id || '-');
        panel.find('.detail-send').text(
            req.send != null ? `USD ${parseFloat(req.send).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
        );
        panel.find('.detail-flash-fee').text(
            req.flash_fee != null ? `USD ${parseFloat(req.flash_fee).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
        );
        panel.find('.detail-exchange-rate').text(
            req.exchange_rate != null ? parseFloat(req.exchange_rate).toLocaleString('en-US', { minimumFractionDigits: 4 }) : '-'
        );
        panel.find('.detail-receive-jmd').text(
            req.receive_jmd != null ? `JMD ${parseFloat(req.receive_jmd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
        );
        panel.find('.detail-receive-usd').text(
            req.receive_usd != null ? `USD ${parseFloat(req.receive_usd).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '-'
        );
        if (req.journal_entry) {
            panel.find('.detail-journal-entry').html(
                `<a class="detail-link" href="/app/journal-entry/${req.journal_entry}" target="_blank">${req.journal_entry}</a>`
            );
        } else {
            panel.find('.detail-journal-entry').text('-');
        }

        // Bank Account
        if (req.bank_account) {
            panel.find('.detail-bank-account').html(
                `<a class="detail-link" href="/app/bank-account/${req.bank_account}" target="_blank">${req.bank_account}</a>`
            );
        } else {
            panel.find('.detail-bank-account').text('-');
        }
        panel.find('.detail-bank-name').text(req.bank_name || '-');
        panel.find('.detail-account-number').text(req.account_number || '-');
        panel.find('.detail-account-type').text(req.account_type || '-');

        // Payment Entry section (shown only when recorded)
        const paymentSection = panel.find('.detail-payment-entry-section');
        if (req.payment_entry) {
            panel.find('.detail-payment-entry').html(
                `<a class="detail-link" href="/app/payment-entry/${req.payment_entry}" target="_blank">${req.payment_entry}</a>`
            );
            panel.find('.detail-pe-amount').text(
                req.pe_paid_amount != null
                    ? `${req.pe_currency || ''} ${parseFloat(req.pe_paid_amount).toLocaleString('en-US', { minimumFractionDigits: 2 })}`.trim()
                    : '-'
            );
            panel.find('.detail-pe-date').text(req.pe_posting_date ? frappe.datetime.str_to_user(req.pe_posting_date) : '-');
            panel.find('.detail-pe-mode').text(req.pe_mode_of_payment || '-');
            paymentSection.show();
        } else {
            paymentSection.hide();
        }

        // Other Information
        panel.find('.detail-status').html(
            `<span class="modern-badge ${getCashoutStatusBadgeClass(req.status)}">${req.status || '-'}</span>`
        );
        panel.find('.detail-request-id').text(req.name || '-');
        panel.find('.detail-submitted').text(this.formatDateTime(req.creation));
        panel.find('.detail-modified').text(this.formatDateTime(req.modified));

        // Record Payment Entry button — only for Pending without a payment entry
        const recordBtn = panel.find('.btn-record-payment');
        if (req.status === CashoutStatus.PENDING && !req.payment_entry) {
            recordBtn.show();
        } else {
            recordBtn.hide();
        }

        panel.show();

        const row = this.page.main.find(`tr[data-request-id="${req.name}"]`);
        if (row.length) {
            row[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    record_payment_entry(req) {
        if (!req) return;

        const sendDisplay = req.send != null
            ? `USD ${parseFloat(req.send).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
            : 'this cashout';

        frappe.confirm(
            `Are you sure you want to record a payment of <strong>${sendDisplay}</strong> for <strong>${req.username}</strong>?<br><br>This will create a Payment Entry linked to ${req.journal_entry || 'the cashout request'}.`,
            () => {
                const btn = this.page.main.find('.btn-record-payment');
                btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Processing...');

                frappe.call({
                    method: 'admin_panel.api.admin_api.record_cashout_payment',
                    args: { cashout_id: req.name },
                    freeze: true,
                    freeze_message: 'Creating Payment Entry...',
                    callback: (r) => {
                        btn.prop('disabled', false).html('<i class="fa fa-credit-card"></i> Record Payment Entry');
                        const result = r.message || {};
                        if (result.success) {
                            frappe.msgprint({
                                title: 'Payment Recorded',
                                indicator: 'green',
                                message: result.message || 'Payment Entry created successfully.'
                            });
                            // Update local data and refresh
                            req.status = CashoutStatus.PAID;
                            req.payment_entry = result.payment_entry;
                            this.show_request_details(req);
                            this.load_cashout_requests();
                        } else {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: result.error || 'Failed to create Payment Entry.'
                            });
                        }
                    },
                    error: (err) => {
                        btn.prop('disabled', false).html('<i class="fa fa-credit-card"></i> Record Payment Entry');
                        const msg = err?.responseJSON?.exception || err?.responseJSON?.message || 'Failed to create Payment Entry';
                        frappe.msgprint({ title: 'Error', indicator: 'red', message: msg });
                    }
                });
            }
        );
    }

    close_details() {
        this.$cache.requestDetails.hide();
        this.selected_request = null;
    }

    search() {
        const input = this.$cache.searchInput.val().trim();
        if (!input) {
            frappe.show_alert({ message: 'Please enter a username or phone number', indicator: 'orange' }, 3);
            return;
        }

        this.$cache.searchLoading.show();
        this.$cache.searchError.hide();
        this.$cache.requestDetails.hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.search_cashout_account',
            args: { id: input },
            callback: (res) => {
                this.$cache.searchLoading.hide();
                const results = res.message;
                if (!results || results.error) {
                    this.show_search_error(results?.error || 'Account not found');
                    return;
                }
                this.show_search_results(Array.isArray(results) ? results : []);
            },
            error: (e) => {
                this.$cache.searchLoading.hide();
                this.show_search_error(e.message || 'Account not found');
            }
        });
    }

    show_search_results(results) {
        this.$cache.requestsTbody.empty();
        this.$cache.searchError.hide();
        this.$cache.paginationControls.hide();

        if (!results || !results.length) {
            this.$cache.noRequests.show();
            this.$cache.requestsTable.hide();
            this.show_search_error('No cashout requests found');
            return;
        }

        this.$cache.noRequests.hide();
        this.$cache.requestsTable.show();

        results.forEach(req => {
            this.$cache.requestsTbody.append(this.create_request_row(req));
        });
    }

    show_search_error(msg) {
        this.$cache.searchLoading.hide();
        this.$cache.searchError.show();
        this.page.main.find('.error-message').text(msg);
    }

    formatPhone(phone) {
        if (!phone) return '-';
        return phone.replace(/^(\d{3})(\d{3})(\d{2})(\d{2})$/, '+$1 $2 $3 $4');
    }

    formatDateTime(dt) {
        return dt ? frappe.datetime.str_to_user(dt) : '-';
    }
}
