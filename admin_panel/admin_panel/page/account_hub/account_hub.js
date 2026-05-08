frappe.pages['account-hub'].on_page_load = function(wrapper) {
    if (!frappe.user_roles.includes('Accounts Manager')) {
        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Account Hub',
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
        title: 'Account Hub',
        single_column: true
    });

    new AccountHub(page);
};

/* ─────────────────────────────────────────────
   Helpers
   ───────────────────────────────────────────── */
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

const ACCOUNT_LEVELS = {
    ZERO: 'ZERO',
    ONE: 'ONE',
    TWO: 'TWO',
    THREE: 'THREE'
};

const ACCOUNT_STATUSES = {
    NEW: 'NEW',
    PENDING: 'PENDING',
    ACTIVE: 'ACTIVE',
    LOCKED: 'LOCKED',
    CLOSED: 'CLOSED'
};

const ACCOUNT_LEVEL_LABELS = {
    [ACCOUNT_LEVELS.ZERO]: 'Trial',
    [ACCOUNT_LEVELS.ONE]: 'Personal',
    [ACCOUNT_LEVELS.TWO]: 'Pro',
    [ACCOUNT_LEVELS.THREE]: 'Merchant'
};

const ACCOUNT_LEVEL_BADGES = {
    [ACCOUNT_LEVELS.ZERO]: 'badge-trial',
    [ACCOUNT_LEVELS.ONE]: 'badge-personal',
    [ACCOUNT_LEVELS.TWO]: 'badge-business',
    [ACCOUNT_LEVELS.THREE]: 'badge-merchant'
};

const ACCOUNT_STATUS_LABELS = {
    [ACCOUNT_STATUSES.NEW]: 'New',
    [ACCOUNT_STATUSES.PENDING]: 'Pending',
    [ACCOUNT_STATUSES.ACTIVE]: 'Active',
    [ACCOUNT_STATUSES.LOCKED]: 'Locked',
    [ACCOUNT_STATUSES.CLOSED]: 'Closed'
};

const ACCOUNT_STATUS_BADGES = {
    [ACCOUNT_STATUSES.NEW]: 'badge-pending',
    [ACCOUNT_STATUSES.PENDING]: 'badge-pending',
    [ACCOUNT_STATUSES.ACTIVE]: 'badge-approved',
    [ACCOUNT_STATUSES.LOCKED]: 'badge-rejected',
    [ACCOUNT_STATUSES.CLOSED]: 'badge-closed'
};

function getLevelLabel(level) {
    return ACCOUNT_LEVEL_LABELS[level] || level;
}

function getLevelBadge(level) {
    return ACCOUNT_LEVEL_BADGES[level] || 'badge-trial';
}

function getStatusLabel(status) {
    return ACCOUNT_STATUS_LABELS[status] || status;
}

function getStatusBadge(status) {
    return ACCOUNT_STATUS_BADGES[status] || 'badge-pending';
}

function formatPhone(phone) {
    if (!phone) return '-';
    return phone.replace(/^\+?(\d{1})(\d{3})(\d{3})(\d{4})$/, '+$1 $2 $3 $4');
}

function formatDate(ts) {
    if (!ts) return '-';
    const d = new Date(ts * 1000);
    return frappe.datetime.global_date_format(d.toISOString().split('T')[0]) + ' ' + d.toLocaleTimeString();
}

function formatCurrency(cents, currency) {
    if (cents == null) return '-';
    const sym = currency === 'USD' ? '$' : (currency === 'USDT' ? '₮' : '$');
    return sym + (cents / 100).toFixed(2);
}

/* ─────────────────────────────────────────────
   AccountHub Class
   ───────────────────────────────────────────── */
class AccountHub {
    constructor(page) {
        this.page = page;
        this.current_account = null;
        this.default_results = [];
        this.$ = {};
        this.setup_page();
    }

    /* ── Page Setup ────────────────────────────────── */
    setup_page() {
        this.create_layout();
        this.cache_elements();
        this.bind_events();
        this.load_default_list();
    }

    create_layout() {
        this.page.main.html(`
            <style>
                .account-hub {
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

                .account-hub {
                    max-width: 1600px;
                    margin: 0 auto;
                }

                /* ── Layout ── */
                .ah-container {
                    display: flex;
                    gap: 24px;
                    align-items: flex-start;
                }

                .ah-left-panel {
                    width: 30%;
                    min-width: 300px;
                    flex-shrink: 0;
                }

                .ah-right-panel {
                    flex: 1;
                    min-width: 0;
                }

                /* ── Cards ── */
                .ah-card {
                    background: var(--color-layer);
                    border-radius: 16px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
                    border: 1px solid var(--color-border01);
                    overflow: hidden;
                }

                .ah-card-header {
                    padding: 16px 20px;
                    background: linear-gradient(135deg, var(--color-primary) 0%, #005a42 100%);
                    color: white;
                    font-size: 16px;
                    font-weight: 600;
                }

                .ah-card-body {
                    padding: 20px;
                }

                /* ── Search ── */
                .ah-search-wrapper {
                    padding: 20px;
                }

                .ah-search-input {
                    width: 100%;
                    padding: 12px 16px;
                    border: 2px solid var(--color-border01);
                    border-radius: 12px;
                    font-size: 15px;
                    transition: all 0.2s ease;
                    background: var(--color-layer);
                    color: var(--color-text01);
                    box-sizing: border-box;
                }

                .ah-search-input:focus {
                    outline: none;
                    border-color: var(--color-primary);
                    box-shadow: 0 0 0 3px rgba(0,120,86,0.1);
                }

                .ah-search-input::placeholder {
                    color: var(--color-text02);
                }

                /* ── Search Results Area ── */
                .ah-results-area {
                    border-top: 1px solid var(--color-border01);
                    min-height: 100px;
                }

                .ah-result-item {
                    padding: 14px 20px;
                    cursor: pointer;
                    transition: background 0.15s;
                    border-bottom: 1px solid var(--color-border01);
                    display: flex;
                    align-items: center;
                    gap: 12px;
                }

                .ah-result-item:last-child {
                    border-bottom: none;
                }

                .ah-result-item:hover {
                    background: rgba(0,120,86,0.03);
                }

                .ah-result-item.active {
                    background: rgba(0,120,86,0.1);
                    border-left: 4px solid var(--color-primary);
                }

                .ah-result-avatar {
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    background: var(--color-primary);
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: 600;
                    font-size: 16px;
                    flex-shrink: 0;
                }

                .ah-result-info {
                    flex: 1;
                    min-width: 0;
                }

                .ah-result-name {
                    font-weight: 600;
                    color: var(--color-text01);
                    font-size: 14px;
                }

                .ah-result-sub {
                    font-size: 12px;
                    color: var(--color-text02);
                    margin-top: 2px;
                }

                /* ── Tabs ── */
                .ah-tabs {
                    display: flex;
                    border-bottom: 2px solid var(--color-border01);
                    background: var(--color-layer);
                    padding: 0 4px;
                }

                .ah-tab {
                    padding: 14px 20px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    color: var(--color-text02);
                    border-bottom: 2px solid transparent;
                    margin-bottom: -2px;
                    transition: all 0.2s;
                    background: none;
                    border-top: none;
                    border-left: none;
                    border-right: none;
                }

                .ah-tab:hover {
                    color: var(--color-primary);
                    background: rgba(0,120,86,0.03);
                }

                .ah-tab.active {
                    color: var(--color-primary);
                    border-bottom-color: var(--color-primary);
                }

                .ah-tab-content {
                    display: none;
                    padding: 24px;
                }

                .ah-tab-content.active {
                    display: block;
                }

                /* ── Info Cards ── */
                .ah-info-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 24px;
                    margin-bottom: 20px;
                }

                .ah-info-card {
                    background: var(--color-layer);
                    border: 1px solid var(--color-border01);
                    border-radius: 12px;
                    padding: 20px;
                }

                .ah-info-card h6 {
                    font-size: 13px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin: 0 0 16px 0;
                    padding-bottom: 10px;
                    border-bottom: 1px solid var(--color-border01);
                }

                .ah-info-row {
                    display: flex;
                    justify-content: space-between;
                    padding: 6px 0;
                    font-size: 14px;
                }

                .ah-info-label {
                    color: var(--color-text02);
                }

                .ah-info-value {
                    color: var(--color-text01);
                    font-weight: 500;
                    text-align: right;
                }

                .ah-verified-badge {
                    background: rgba(0,167,0,0.1);
                    color: var(--color-green);
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 11px;
                    font-weight: 600;
                    margin-left: 6px;
                }

                /* ── Badges ── */
                .ah-badge {
                    display: inline-flex;
                    align-items: center;
                    padding: 4px 10px;
                    border-radius: 20px;
                    font-size: 11px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }

                .ah-badge.badge-trial {
                    background: rgba(148,163,159,0.15);
                    color: var(--color-text02);
                }
                .ah-badge.badge-personal {
                    background: rgba(0,120,86,0.1);
                    color: var(--color-primary);
                }
                .ah-badge.badge-business {
                    background: rgba(232,211,21,0.15);
                    color: #b8a00e;
                }
                .ah-badge.badge-merchant {
                    background: rgba(245,158,11,0.15);
                    color: var(--color-warning);
                }
                .ah-badge.badge-pending {
                    background: rgba(245,158,11,0.15);
                    color: var(--color-warning);
                }
                .ah-badge.badge-approved {
                    background: #d4f7d9;
                    color: #15803d;
                }
                .ah-badge.badge-rejected {
                    background: #fde2e2;
                    color: #b91c1c;
                }
                .ah-badge.badge-closed {
                    background: rgba(100,116,139,0.15);
                    color: #475569;
                }

                /* ── Action Toolbar ── */
                .ah-action-bar {
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    padding-top: 20px;
                    border-top: 1px solid var(--color-border01);
                    margin-top: 20px;
                }

                .ah-btn {
                    padding: 10px 18px;
                    border-radius: 10px;
                    font-weight: 500;
                    font-size: 14px;
                    border: none;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    display: inline-flex;
                    align-items: center;
                    gap: 6px;
                }

                .ah-btn-primary {
                    background: var(--color-primary);
                    color: white;
                }
                .ah-btn-primary:hover {
                    background: #005a42;
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0,120,86,0.2);
                }

                .ah-btn-success {
                    background: var(--color-green);
                    color: white;
                }
                .ah-btn-success:hover {
                    background: #008f00;
                }

                .ah-btn-danger {
                    background: var(--color-error);
                    color: white;
                }
                .ah-btn-danger:hover {
                    background: #b91c1c;
                }

                .ah-btn-secondary {
                    background: var(--color-layer);
                    color: var(--color-text01);
                    border: 2px solid var(--color-border01);
                }
                .ah-btn-secondary:hover {
                    background: var(--color-background);
                    border-color: var(--color-text02);
                }

                .ah-btn-sm {
                    padding: 6px 12px;
                    font-size: 12px;
                    border-radius: 8px;
                }

                /* ── Wallet Cards ── */
                .ah-wallet-card {
                    background: var(--color-layer);
                    border: 1px solid var(--color-border01);
                    border-radius: 12px;
                    padding: 20px;
                    margin-bottom: 16px;
                }

                .ah-wallet-row {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 6px 0;
                    font-size: 14px;
                }

                .ah-wallet-balance {
                    font-size: 28px;
                    font-weight: 700;
                    color: var(--color-text01);
                }

                .ah-wallet-currency-badge {
                    display: inline-flex;
                    align-items: center;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    background: rgba(0,120,86,0.1);
                    color: var(--color-primary);
                }

                /* ── Document Item ── */
                .ah-doc-item {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 16px;
                    background: var(--color-background);
                    border-radius: 10px;
                    margin-bottom: 8px;
                    border: 1px solid var(--color-border01);
                }

                .ah-doc-info {
                    font-size: 14px;
                    color: var(--color-text01);
                }

                /* ── Merchant Card ── */
                .ah-merchant-card {
                    background: var(--color-layer);
                    border: 1px solid var(--color-border01);
                    border-radius: 12px;
                    padding: 16px;
                    margin-bottom: 12px;
                }

                .ah-merchant-title {
                    font-size: 16px;
                    font-weight: 600;
                    color: var(--color-text01);
                    margin-bottom: 8px;
                }

                .ah-merchant-row {
                    font-size: 13px;
                    color: var(--color-text02);
                    padding: 3px 0;
                }

                .ah-merchant-actions {
                    margin-top: 12px;
                    display: flex;
                    gap: 8px;
                }

                /* ── Upgrade Table ── */
                .ah-table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                }

                .ah-table thead {
                    background: var(--color-background);
                }

                .ah-table th {
                    padding: 12px 16px;
                    text-align: left;
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border-bottom: 2px solid var(--color-border01);
                }

                .ah-table td {
                    padding: 12px 16px;
                    font-size: 14px;
                    color: var(--color-text01);
                    border-bottom: 1px solid var(--color-border01);
                }

                .ah-table tr:last-child td {
                    border-bottom: none;
                }

                /* ── Empty State ── */
                .ah-empty {
                    padding: 60px 20px;
                    text-align: center;
                    color: var(--color-text02);
                }

                .ah-empty-icon {
                    font-size: 40px;
                    margin-bottom: 12px;
                    opacity: 0.3;
                }

                .ah-empty-text {
                    font-size: 15px;
                    font-weight: 500;
                }

                .ah-empty-sub {
                    font-size: 13px;
                    margin-top: 4px;
                }

                /* ── Loading ── */
                .ah-loading {
                    padding: 40px 20px;
                    text-align: center;
                }

                .ah-spinner {
                    width: 36px;
                    height: 36px;
                    border: 3px solid var(--color-border01);
                    border-top-color: var(--color-primary);
                    border-radius: 50%;
                    animation: ah-spin 0.8s linear infinite;
                    margin: 0 auto 12px;
                }

                @keyframes ah-spin {
                    to { transform: rotate(360deg); }
                }

                .ah-error-msg {
                    padding: 16px 20px;
                    color: var(--color-error);
                    font-size: 14px;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    background: rgba(220,38,38,0.04);
                    border-top: 1px solid rgba(220,38,38,0.15);
                }

                /* ── Right Panel Hidden State ── */
                .ah-right-empty {
                    padding: 80px 20px;
                    text-align: center;
                    color: var(--color-text02);
                }

                .ah-right-empty-icon {
                    font-size: 56px;
                    margin-bottom: 16px;
                    opacity: 0.2;
                }

                .ah-right-empty-text {
                    font-size: 18px;
                    font-weight: 500;
                }

                .ah-right-empty-sub {
                    font-size: 14px;
                    margin-top: 4px;
                }

                @media (max-width: 900px) {
                    .ah-container {
                        flex-direction: column;
                    }
                    .ah-left-panel {
                        width: 100%;
                        min-width: 0;
                    }
                    .ah-info-grid {
                        grid-template-columns: 1fr;
                    }
                }
            </style>

            <div class="account-hub m-3">
                <div class="ah-container">
                    <!-- Left Panel: Search + Results -->
                    <div class="ah-left-panel">
                        <div class="ah-card">
                            <div class="ah-card-header">
                                <i class="fa fa-search" style="margin-right: 8px;"></i>
                                Search Account
                            </div>
                            <div class="ah-search-wrapper">
                                <input type="text" class="ah-search-input search-input" placeholder="Search by phone (+1...), email, username, or account ID">
                                <div class="ah-search-hint" style="font-size:11px;color:var(--color-text02);margin-top:6px;">
                                    <i class="fa fa-info-circle"></i> Press Enter or pause to search
                                </div>
                            </div>
                            <div class="ah-results-area">
                                <div class="ah-loading search-loading" style="display:none;">
                                    <div class="ah-spinner"></div>
                                    <p style="color:var(--color-text02);font-size:14px;">Searching...</p>
                                </div>
                                <div class="ah-error-msg search-error" style="display:none;">
                                    <i class="fa fa-exclamation-circle"></i>
                                    <span class="error-text"></span>
                                </div>
                                <div class="search-results-list">
                                    <!-- Populated dynamically -->
                                </div>
                                <div class="ah-empty search-empty" style="display:none;">
                                    <div class="ah-empty-icon">🔍</div>
                                    <div class="ah-empty-text">No accounts found</div>
                                    <div class="ah-empty-sub">Recent upgrade requests will appear here. Use the search bar to find specific accounts.</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Right Panel: Detail View -->
                    <div class="ah-right-panel">
                        <div class="ah-card">
                            <!-- Empty State (shown when no account selected) -->
                            <div class="ah-right-empty right-empty-state">
                                <div class="ah-right-empty-icon">👤</div>
                                <div class="ah-right-empty-text">No account selected</div>
                                <div class="ah-right-empty-sub">Search for an account on the left to view details</div>
                            </div>

                            <!-- Detail Content (shown when account is selected) -->
                            <div class="ah-detail-content" style="display:none;">
                                <div class="ah-card-header detail-account-title" style="display:flex;align-items:center;gap:10px;">
                                    <i class="fa fa-user"></i>
                                    <span class="detail-username-display"></span>
                                    <span class="ah-badge detail-level-badge" style="margin-left:auto;"></span>
                                    <span class="ah-badge detail-status-badge"></span>
                                </div>

                                <!-- Tabs -->
                                <div class="ah-tabs">
                                    <button class="ah-tab active" data-tab="overview">Overview</button>
                                    <button class="ah-tab" data-tab="wallets">Wallets</button>
                                    <button class="ah-tab" data-tab="documents">Documents</button>
                                    <button class="ah-tab" data-tab="merchant">Merchant</button>
                                    <button class="ah-tab" data-tab="upgrade">Upgrade History</button>
                                </div>

                                <!-- Tab: Overview -->
                                <div class="ah-tab-content active" data-tab="overview">
                                    <div class="ah-info-grid">
                                        <!-- Identity Card -->
                                        <div class="ah-info-card">
                                            <h6><i class="fa fa-id-card" style="margin-right:6px;color:var(--color-primary);"></i> Identity</h6>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Phone</span>
                                                <span class="ah-info-value detail-ov-phone"></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Email</span>
                                                <span class="ah-info-value detail-ov-email"></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Username</span>
                                                <span class="ah-info-value detail-ov-username"></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">npub</span>
                                                <span class="ah-info-value detail-ov-npub" style="font-size:12px;word-break:break-all;"></span>
                                            </div>
                                        </div>

                                        <!-- Account State Card -->
                                        <div class="ah-info-card">
                                            <h6><i class="fa fa-shield" style="margin-right:6px;color:var(--color-primary);"></i> Account State</h6>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Level</span>
                                                <span class="ah-info-value"><span class="ah-badge detail-ov-level-badge"></span></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Status</span>
                                                <span class="ah-info-value"><span class="ah-badge detail-ov-status-badge"></span></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">ERP Party</span>
                                                <span class="ah-info-value detail-ov-erp-party"></span>
                                            </div>
                                            <div class="ah-info-row">
                                                <span class="ah-info-label">Created</span>
                                                <span class="ah-info-value detail-ov-created"></span>
                                            </div>
                                        </div>
                                    </div>

                                    <!-- Action Bar -->
                                    <div class="ah-action-bar">
                                        <div class="btn-group">
                                            <button class="ah-btn ah-btn-primary btn-change-level">
                                                <i class="fa fa-level-up"></i> Change Level
                                            </button>
                                        </div>
                                        <button class="ah-btn ah-btn-danger btn-lock-account" style="display:none;">
                                            <i class="fa fa-lock"></i> Lock Account
                                        </button>
                                        <button class="ah-btn ah-btn-success btn-activate-account" style="display:none;">
                                            <i class="fa fa-unlock"></i> Activate Account
                                        </button>
                                        <button class="ah-btn ah-btn-secondary btn-update-phone">
                                            <i class="fa fa-phone"></i> Update Phone
                                        </button>
                                    </div>
                                </div>

                                <!-- Tab: Wallets -->
                                <div class="ah-tab-content" data-tab="wallets">
                                    <div class="wallets-container"></div>
                                </div>

                                <!-- Tab: Documents -->
                                <div class="ah-tab-content" data-tab="documents">
                                    <div class="documents-container"></div>
                                </div>

                                <!-- Tab: Merchant -->
                                <div class="ah-tab-content" data-tab="merchant">
                                    <div class="merchant-container"></div>
                                </div>

                                <!-- Tab: Upgrade History -->
                                <div class="ah-tab-content" data-tab="upgrade">
                                    <div class="upgrade-container"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);
    }

    cache_elements() {
        const main = this.page.main;
        this.$ = {
            searchInput: main.find('.search-input'),
            searchLoading: main.find('.search-loading'),
            searchError: main.find('.search-error'),
            searchErrorText: main.find('.search-error .error-text'),
            searchEmpty: main.find('.search-empty'),
            searchResultsList: main.find('.search-results-list'),
            rightEmpty: main.find('.right-empty-state'),
            detailContent: main.find('.ah-detail-content'),
            detailUsername: main.find('.detail-username-display'),
            detailLevelBadge: main.find('.detail-level-badge'),
            detailStatusBadge: main.find('.detail-status-badge'),
            tabs: main.find('.ah-tab'),
            tabContents: main.find('.ah-tab-content'),
            // Overview
            ovPhone: main.find('.detail-ov-phone'),
            ovEmail: main.find('.detail-ov-email'),
            ovUsername: main.find('.detail-ov-username'),
            ovNpub: main.find('.detail-ov-npub'),
            ovLevelBadge: main.find('.detail-ov-level-badge'),
            ovStatusBadge: main.find('.detail-ov-status-badge'),
            ovErpParty: main.find('.detail-ov-erp-party'),
            ovCreated: main.find('.detail-ov-created'),
            // Action buttons
            btnChangeLevel: main.find('.btn-change-level'),
            btnLockAccount: main.find('.btn-lock-account'),
            btnActivateAccount: main.find('.btn-activate-account'),
            btnUpdatePhone: main.find('.btn-update-phone'),
            // Containers
            walletsContainer: main.find('.wallets-container'),
            documentsContainer: main.find('.documents-container'),
            merchantContainer: main.find('.merchant-container'),
            upgradeContainer: main.find('.upgrade-container')
        };
    }

    bind_events() {
        const main = this.page.main;

        // Search: Enter key — calls API
        this.$.searchInput.on('keypress', (e) => {
            if (e.which === 13) {
                this.perform_search();
            }
        });

        // Search: input — filter local list, debounce API call for longer queries
        const debouncedSearch = debounce(() => {
            const val = this.$.searchInput.val().trim();
            if (val) {
                this.perform_search();
            }
        }, 600);

        this.$.searchInput.on('input', () => {
            const val = this.$.searchInput.val().trim();
            // Filter local default list in real-time
            this.filter_local_list(val);
            // Debounce remote search if there's a query
            if (val) {
                debouncedSearch();
            }
        });

        // Tab switching
        this.$.tabs.on('click', function() {
            const tab = $(this).data('tab');
            main.find('.ah-tab').removeClass('active');
            $(this).addClass('active');
            main.find('.ah-tab-content').removeClass('active');
            main.find(`.ah-tab-content[data-tab="${tab}"]`).addClass('active');
        });

        // Action buttons
        this.$.btnChangeLevel.on('click', () => this.change_level());
        this.$.btnLockAccount.on('click', () => this.change_status(ACCOUNT_STATUSES.LOCKED));
        this.$.btnActivateAccount.on('click', () => this.change_status(ACCOUNT_STATUSES.ACTIVE));
        this.$.btnUpdatePhone.on('click', () => this.update_phone());
    }

    /* ── Default User List ────────────────────────────── */

    load_default_list() {
        this.$.searchLoading.show();
        this.$.searchError.hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.get_upgrade_requests',
            args: { page: 1, page_size: 50 },
            callback: (res) => {
                this.$.searchLoading.hide();
                const result = res.message;
                const requests = (result && result.data) || [];

                if (requests.length === 0) {
                    this.$.searchEmpty.show();
                    return;
                }

                this.default_results = requests;
                this.$.searchEmpty.hide();
                this.render_result_list(requests);
            },
            error: () => {
                this.$.searchLoading.hide();
                this.$.searchEmpty.show();
            }
        });
    }

    render_result_list(items) {
        this.$.searchError.hide();
        this.$.searchResultsList.empty();

        items.forEach(account => {
            // Use username if available, fallback to phone/email/name
            const displayName = account.username || account.phone || account.email_id || account.name || 'Unknown';
            const subInfo = [account.phone, account.email_id].filter(Boolean).join(' · ') || '—';
            const level = account.requested_level || 'ZERO';
            const initial = (displayName || '?')[0].toUpperCase();
            const levelLabel = getLevelLabel(level);
            const levelBadge = getLevelBadge(level);

            const item = $(`
                <div class="ah-result-item" data-id="${frappe.utils.escape_html(account.name)}" data-username="${frappe.utils.escape_html(account.username || '')}" data-phone="${frappe.utils.escape_html(account.phone || '')}" data-email="${frappe.utils.escape_html(account.email_id || '')}">
                    <div class="ah-result-avatar">${initial}</div>
                    <div class="ah-result-info">
                        <div class="ah-result-name">${frappe.utils.escape_html(displayName)}</div>
                        <div class="ah-result-sub">${frappe.utils.escape_html(subInfo)}</div>
                    </div>
                    <span class="ah-badge ${levelBadge}">${levelLabel}</span>
                </div>
            `);

            item.on('click', () => this.on_result_click(account, item));
            this.$.searchResultsList.append(item);
        });

        if (items.length === 0) {
            this.$.searchEmpty.show();
        }
    }

    filter_local_list(query) {
        if (!query) {
            this.render_result_list(this.default_results);
            return;
        }

        const q = query.toLowerCase();
        const filtered = this.default_results.filter(r => {
            return (r.username && r.username.toLowerCase().includes(q)) ||
                   (r.phone && r.phone.toLowerCase().includes(q)) ||
                   (r.email_id && r.email_id.toLowerCase().includes(q)) ||
                   (r.name && r.name.toLowerCase().includes(q));
        });

        this.render_result_list(filtered);
    }

    on_result_click(account, itemEl) {
        this.$.searchResultsList.find('.ah-result-item').removeClass('active');
        itemEl.addClass('active');

        // Build a fallback object from local data in case Flash API doesn't have this account
        const fallback = {
            uuid: account.name,
            username: account.username || account.phone || account.email_id || account.name,
            level: account.requested_level || 'ZERO',
            status: account.status || 'ACTIVE',
            owner: {
                phone: account.phone,
                email: { address: account.email_id, verified: false }
            },
            wallets: [],
            merchants: [],
            createdAt: null
        };

        if (account.username) {
            this.fetch_account_details(account.username, fallback);
        } else {
            this.show_account(fallback);
        }
    }

    fetch_account_details(username, fallback) {
        /* Fetch full account details without modifying the result list.
           Falls back to local data if the Flash API can't find the account. */
        frappe.call({
            method: 'admin_panel.api.admin_api.search_account_smart',
            args: { query: username },
            callback: (res) => {
                const result = res.message;
                if (!result || result.error) {
                    if (fallback) {
                        this.show_account(fallback);
                    }
                    return;
                }
                this.show_account(result);
            },
            error: () => {
                if (fallback) {
                    this.show_account(fallback);
                }
            }
        });
    }

    /* ── Search ─────────────────────────────────────── */

    perform_search() {
        const query = this.$.searchInput.val().trim();
        if (!query) return;
        this.perform_search_with_query(query, true);
    }

    perform_search_with_query(query, clearLocal) {
        if (!query) return;

        this.$.searchLoading.show();
        this.$.searchError.hide();
        if (clearLocal) {
            this.$.searchResultsList.empty();
        }

        frappe.call({
            method: 'admin_panel.api.admin_api.search_account_smart',
            args: { query: query },
            callback: (res) => {
                this.$.searchLoading.hide();
                const result = res.message;
                if (!result || result.error) {
                    this.show_search_error(result?.error || 'Account not found. Try searching by phone (+1...), email, username, or account ID.');
                    return;
                }
                this.show_search_result(result);
            },
            error: () => {
                this.$.searchLoading.hide();
                this.show_search_error('Network error. Please try again.');
            }
        });
    }

    show_search_error(msg) {
        this.$.searchError.show();
        this.$.searchErrorText.text(msg);
        // Don't clear the search results list — keep the last result visible
    }

    show_search_result(account) {
        this.$.searchError.hide();
        this.$.searchResultsList.empty();
        this.$.searchEmpty.hide();

        const initial = (account.username || '?')[0].toUpperCase();
        const subInfo = account.owner?.phone || account.owner?.email?.address || account.username || account.id;
        const levelLabel = getLevelLabel(account.level);
        const levelBadge = getLevelBadge(account.level);

        const item = $(`
            <div class="ah-result-item" data-uuid="${account.uuid}">
                <div class="ah-result-avatar">${initial}</div>
                <div class="ah-result-info">
                    <div class="ah-result-name">${frappe.utils.escape_html(account.username || 'Unknown')}</div>
                    <div class="ah-result-sub">${frappe.utils.escape_html(subInfo)}</div>
                </div>
                <span class="ah-badge ${levelBadge}">${levelLabel}</span>
            </div>
        `);

        item.on('click', () => {
            this.$.searchResultsList.find('.ah-result-item').removeClass('active');
            item.addClass('active');
            this.show_account(account);
        });

        this.$.searchResultsList.append(item);
        item.click(); // Auto-select search result
    }

    /* ── Show Account ────────────────────────────────── */

    show_account(account) {
        this.current_account = account;

        // Switch to detail view
        this.$.rightEmpty.hide();
        this.$.detailContent.show();

        // Update header
        this.$.detailUsername.text(account.username || 'Unknown');
        this.$.detailLevelBadge
            .text(getLevelLabel(account.level))
            .attr('class', 'ah-badge ' + getLevelBadge(account.level));
        this.$.detailStatusBadge
            .text(getStatusLabel(account.status))
            .attr('class', 'ah-badge ' + getStatusBadge(account.status));

        // Activate first tab
        this.$.tabs.removeClass('active');
        this.$.tabs.first().addClass('active');
        this.$.tabContents.removeClass('active');
        this.$.tabContents.first().addClass('active');

        // Populate all tabs
        this.populate_overview(account);
        this.populate_wallets(account);
        this.populate_documents(account);
        this.populate_merchant(account);
        this.populate_upgrade_history(account);
    }

    clear_account() {
        this.current_account = null;
        this.$.detailContent.hide();
        this.$.rightEmpty.show();
        this.$.searchResultsList.find('.ah-result-item').removeClass('active');
    }

    refresh_current_account() {
        if (!this.current_account) return;
        const account = this.current_account;
        frappe.call({
            method: 'admin_panel.api.admin_api.search_account_smart',
            args: { query: account.username || account.uuid },
            callback: (res) => {
                const result = res.message;
                if (result && !result.error) {
                    this.$.searchResultsList.find('.ah-result-item').remove();
                    this.show_search_result(result);
                }
            },
            error: () => {}
        });
    }

    /* ── Tab: Overview ───────────────────────────────── */

    populate_overview(account) {
        // Identity
        const phone = account.owner?.phone;
        this.$.ovPhone.html(phone
            ? `<a href="tel:${frappe.utils.escape_html(phone)}" style="color:var(--color-primary);text-decoration:none;">${formatPhone(phone)}</a>`
            : '-'
        );

        const email = account.owner?.email;
        if (email && email.address) {
            const badge = email.verified
                ? '<span class="ah-verified-badge"><i class="fa fa-check-circle"></i> Verified</span>'
                : '<span class="ah-verified-badge" style="background:rgba(245,158,11,0.1);color:var(--color-warning);"><i class="fa fa-clock-o"></i> Unverified</span>';
            this.$.ovEmail.html(`${frappe.utils.escape_html(email.address)} ${badge}`);
        } else {
            this.$.ovEmail.text('-');
        }

        this.$.ovUsername.text(account.username || '-');
        this.$.ovNpub.text(account.npub || '-');

        // Account State
        this.$.ovLevelBadge
            .text(getLevelLabel(account.level))
            .attr('class', 'ah-badge ' + getLevelBadge(account.level));
        this.$.ovStatusBadge
            .text(getStatusLabel(account.status))
            .attr('class', 'ah-badge ' + getStatusBadge(account.status));
        this.$.ovErpParty.text(account.erpParty || '-');
        this.$.ovCreated.text(formatDate(account.createdAt));

        // Action buttons visibility
        this.$.btnLockAccount.toggle(account.status === ACCOUNT_STATUSES.ACTIVE);
        this.$.btnActivateAccount.toggle(account.status === ACCOUNT_STATUSES.LOCKED);
    }

    /* ── Tab: Wallets ────────────────────────────────── */

    populate_wallets(account) {
        const container = this.$.walletsContainer;
        container.empty();

        const wallets = account.wallets || [];
        if (wallets.length === 0) {
            container.html(`
                <div class="ah-empty">
                    <div class="ah-empty-icon">💰</div>
                    <div class="ah-empty-text">No wallet information available</div>
                </div>
            `);
            return;
        }

        // Sort: USD first, then others
        const sorted = [...wallets].sort((a, b) => {
            if (a.walletCurrency === 'USD') return -1;
            if (b.walletCurrency === 'USD') return 1;
            return 0;
        });

        sorted.forEach(w => {
            const cur = w.walletCurrency || 'USD';
            const card = $(`
                <div class="ah-wallet-card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
                        <span class="ah-wallet-currency-badge">${frappe.utils.escape_html(cur)}</span>
                    </div>
                    <div class="ah-wallet-row">
                        <span class="ah-info-label">Balance</span>
                        <span class="ah-wallet-balance">${formatCurrency(w.balance, cur)}</span>
                    </div>
                    <div class="ah-wallet-row">
                        <span class="ah-info-label">Pending Incoming</span>
                        <span style="font-weight:500;color:var(--color-text01);">${formatCurrency(w.pendingIncomingBalance, cur)}</span>
                    </div>
                    <div class="ah-wallet-row" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--color-border01);">
                        <span class="ah-info-label">Wallet ID</span>
                        <span style="font-size:12px;color:var(--color-text02);font-family:monospace;">${frappe.utils.escape_html(w.id)}</span>
                    </div>
                </div>
            `);
            container.append(card);
        });
    }

    /* ── Tab: Documents ──────────────────────────────── */

    populate_documents(account) {
        const container = this.$.documentsContainer;
        container.empty();

        const username = account.username;
        if (!username) {
            container.html(`
                <div class="ah-empty">
                    <div class="ah-empty-icon">📄</div>
                    <div class="ah-empty-text">No documents uploaded</div>
                </div>
            `);
            return;
        }

        container.html(`<div class="ah-loading"><div class="ah-spinner"></div><p style="color:var(--color-text02);font-size:14px;">Loading documents...</p></div>`);

        frappe.call({
            method: 'admin_panel.api.admin_api.get_upgrade_requests_by_account',
            args: { username: username },
            callback: (res) => {
                container.empty();
                const result = res.message;
                const requests = (result && result.data) || [];
                const docRequests = requests.filter(r => r.id_document);

                if (docRequests.length === 0) {
                    container.html(`
                        <div class="ah-empty">
                            <div class="ah-empty-icon">📄</div>
                            <div class="ah-empty-text">No documents uploaded</div>
                        </div>
                    `);
                    return;
                }

                docRequests.forEach(r => {
                    const item = $(`
                        <div class="ah-doc-item">
                            <div>
                                <div class="ah-doc-info"><i class="fa fa-file-image-o" style="margin-right:6px;color:var(--color-primary);"></i> ${frappe.utils.escape_html(r.requested_level || 'Unknown')} Upgrade</div>
                                <div style="font-size:12px;color:var(--color-text02);margin-top:2px;">Submitted ${frappe.utils.escape_html(r.creation || '')}</div>
                            </div>
                            <button class="ah-btn ah-btn-secondary ah-btn-sm btn-view-doc" data-file-key="${frappe.utils.escape_html(r.id_document)}">
                                <i class="fa fa-eye"></i> View
                            </button>
                        </div>
                    `);

                    const requestName = r.name;
                    item.find('.btn-view-doc').on('click', () => {
                        window.open('/app/account-upgrade-request/' + encodeURIComponent(requestName), '_blank');
                    });

                    container.append(item);
                });
            },
            error: () => {
                container.html(`
                    <div class="ah-empty">
                        <div class="ah-empty-icon">⚠️</div>
                        <div class="ah-empty-text">Failed to load documents</div>
                        <div class="ah-empty-sub">An error occurred while fetching document data</div>
                    </div>
                `);
            }
        });
    }

    /* ── Tab: Merchant ───────────────────────────────── */

    populate_merchant(account) {
        const container = this.$.merchantContainer;
        container.empty();

        const merchants = account.merchants || [];
        if (merchants.length === 0) {
            container.html(`
                <div class="ah-empty">
                    <div class="ah-empty-icon">🏪</div>
                    <div class="ah-empty-text">No merchant information</div>
                </div>
            `);
            return;
        }

        merchants.forEach(m => {
            const validBadge = m.validated
                ? '<span class="ah-badge badge-approved"><i class="fa fa-check"></i> Validated</span>'
                : '<span class="ah-badge badge-pending"><i class="fa fa-clock-o"></i> Not Validated</span>';

            let mapLink = '-';
            const coords = m.coordinates || {};
            if (coords.latitude != null && coords.longitude != null) {
                mapLink = `<a href="https://www.google.com/maps?q=${coords.latitude},${coords.longitude}" target="_blank" style="color:var(--color-primary);text-decoration:none;">${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}</a>`;
            }

            const card = $(`
                <div class="ah-merchant-card">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div class="ah-merchant-title">
                            <i class="fa fa-shopping-cart" style="margin-right:6px;color:var(--color-primary);"></i>
                            ${frappe.utils.escape_html(m.title || 'Unnamed')}
                        </div>
                        ${validBadge}
                    </div>
                    <div class="ah-merchant-row"><strong>Username:</strong> ${frappe.utils.escape_html(m.username || '-')}</div>
                    <div class="ah-merchant-row"><strong>Coordinates:</strong> ${mapLink}</div>
                    <div class="ah-merchant-row"><strong>Created:</strong> ${formatDate(m.createdAt)}</div>
                </div>
            `);

            // Action buttons for unvalidated merchants
            if (!m.validated) {
                const actionsDiv = $(`<div class="ah-merchant-actions"></div>`);

                const validateBtn = $(`<button class="ah-btn ah-btn-success ah-btn-sm"><i class="fa fa-check"></i> Validate</button>`);
                validateBtn.on('click', () => this.validate_merchant(m.id));

                const deleteBtn = $(`<button class="ah-btn ah-btn-danger ah-btn-sm"><i class="fa fa-trash"></i> Delete</button>`);
                deleteBtn.on('click', () => this.delete_merchant(m.id));

                actionsDiv.append(validateBtn, deleteBtn);
                card.append(actionsDiv);
            }

            container.append(card);
        });
    }

    /* ── Tab: Upgrade History ────────────────────────── */

    populate_upgrade_history(account) {
        const container = this.$.upgradeContainer;
        container.empty();

        const username = account.username;
        if (!username) {
            container.html(`
                <div class="ah-empty">
                    <div class="ah-empty-icon">📋</div>
                    <div class="ah-empty-text">No upgrade requests for this account</div>
                </div>
            `);
            return;
        }

        container.html(`<div class="ah-loading"><div class="ah-spinner"></div><p style="color:var(--color-text02);font-size:14px;">Loading upgrade history...</p></div>`);

        frappe.call({
            method: 'admin_panel.api.admin_api.get_upgrade_requests_by_account',
            args: { username: username },
            callback: (res) => {
                container.empty();
                const result = res.message;
                const requests = (result && result.data) || [];

                if (requests.length === 0) {
                    container.html(`
                        <div class="ah-empty">
                            <div class="ah-empty-icon">📋</div>
                            <div class="ah-empty-text">No upgrade requests for this account</div>
                        </div>
                    `);
                    return;
                }

                const table = $(`
                    <table class="ah-table">
                        <thead>
                            <tr>
                                <th>Requested Level</th>
                                <th>Status</th>
                                <th>Submitted</th>
                                <th>Reviewed</th>
                                <th>Support Note</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                `);

                const tbody = table.find('tbody');
                requests.forEach(r => {
                    const statusLabel = getStatusLabel(r.status || 'PENDING');
                    const statusBadge = getStatusBadge(r.status || 'PENDING');
                    const levelLabel = getLevelLabel(r.requested_level);
                    const levelBadge = getLevelBadge(r.requested_level);

                    const row = $(`
                        <tr>
                            <td><span class="ah-badge ${levelBadge}">${levelLabel}</span></td>
                            <td><span class="ah-badge ${statusBadge}">${statusLabel}</span></td>
                            <td>${r.creation ? frappe.datetime.str_to_user(r.creation) : '-'}</td>
                            <td>${r.modified ? frappe.datetime.str_to_user(r.modified) : '-'}</td>
                            <td style="max-width:250px;white-space:normal;word-break:break-word;">${r.support_note ? frappe.utils.escape_html(r.support_note) : '-'}</td>
                        </tr>
                    `);
                    tbody.append(row);
                });

                container.append(table);
            },
            error: () => {
                container.html(`
                    <div class="ah-empty">
                        <div class="ah-empty-icon">⚠️</div>
                        <div class="ah-empty-text">Failed to load upgrade history</div>
                        <div class="ah-empty-sub">An error occurred while fetching upgrade data</div>
                    </div>
                `);
            }
        });
    }

    /* ── Actions: Change Level ────────────────────────── */

    change_level() {
        if (!this.current_account) return;
        const account = this.current_account;

        const currentLevel = account.level;
        const options = Object.keys(ACCOUNT_LEVEL_LABELS).filter(k => k !== currentLevel).map(k => ({
            label: ACCOUNT_LEVEL_LABELS[k],
            value: k
        }));

        if (options.length === 0) {
            frappe.msgprint({ title: 'Info', indicator: 'blue', message: 'No other levels available to change to.' });
            return;
        }

        const d = new frappe.ui.Dialog({
            title: 'Change Account Level',
            fields: [
                {
                    fieldname: 'new_level',
                    fieldtype: 'Select',
                    label: 'New Level',
                    reqd: 1,
                    options: options.map(o => o.label),
                    default: options[0].label
                }
            ],
            primary_action_label: 'Update Level',
            primary_action: (values) => {
                const selectedOption = options.find(o => o.label === values.new_level);
                if (!selectedOption) return;

                d.hide();
                frappe.call({
                    method: 'admin_panel.api.admin_api.update_account_level',
                    args: {
                        uid: account.uuid,
                        level: selectedOption.value
                    },
                    freeze: true,
                    freeze_message: 'Updating account level...',
                    callback: (res) => {
                        const result = res.message || {};
                        if (result.errors) {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: Array.isArray(result.errors) ? result.errors.join(', ') : result.errors
                            });
                        } else {
                            frappe.show_alert({ message: `Account level updated to ${ACCOUNT_LEVEL_LABELS[selectedOption.value]}`, indicator: 'green' }, 5);
                            this.refresh_current_account();
                        }
                    },
                    error: (err) => {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: err?.responseJSON?.exception || err?.message || 'Failed to update account level'
                        });
                    }
                });
            }
        });

        d.show();
    }

    /* ── Actions: Change Status ───────────────────────── */

    change_status(newStatus) {
        if (!this.current_account) return;
        const account = this.current_account;
        const isLock = newStatus === ACCOUNT_STATUSES.LOCKED;

        const d = new frappe.ui.Dialog({
            title: isLock ? 'Lock Account' : 'Activate Account',
            fields: [
                {
                    fieldname: 'comment',
                    fieldtype: 'Small Text',
                    label: isLock ? 'Reason for locking' : 'Comment (optional)',
                    reqd: isLock ? 1 : 0
                }
            ],
            primary_action_label: isLock ? 'Lock Account' : 'Activate Account',
            primary_action: (values) => {
                d.hide();
                frappe.call({
                    method: 'admin_panel.api.admin_api.update_account_status_api',
                    args: {
                        account_uuid: account.uuid,
                        status: newStatus,
                        comment: values.comment || ''
                    },
                    freeze: true,
                    freeze_message: isLock ? 'Locking account...' : 'Activating account...',
                    callback: (res) => {
                        const result = res.message || {};
                        if (result.errors) {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: Array.isArray(result.errors) ? result.errors.join(', ') : result.errors
                            });
                        } else {
                            frappe.show_alert({
                                message: `Account ${isLock ? 'locked' : 'activated'} successfully`,
                                indicator: 'green'
                            }, 5);
                            this.refresh_current_account();
                        }
                    },
                    error: (err) => {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: err?.responseJSON?.exception || err?.message || `Failed to ${isLock ? 'lock' : 'activate'} account`
                        });
                    }
                });
            }
        });

        d.show();
    }

    /* ── Actions: Update Phone ────────────────────────── */

    update_phone() {
        if (!this.current_account) return;
        const account = this.current_account;

        const d = new frappe.ui.Dialog({
            title: 'Update Phone Number',
            fields: [
                {
                    fieldname: 'phone',
                    fieldtype: 'Data',
                    label: 'New Phone Number',
                    description: 'Enter phone number with country code (e.g., +1234567890)',
                    reqd: 1,
                    default: account.owner?.phone || ''
                }
            ],
            primary_action_label: 'Update Phone',
            primary_action: (values) => {
                d.hide();
                frappe.call({
                    method: 'admin_panel.api.admin_api.update_user_phone_api',
                    args: {
                        account_uuid: account.uuid,
                        phone: values.phone
                    },
                    freeze: true,
                    freeze_message: 'Updating phone number...',
                    callback: (res) => {
                        const result = res.message || {};
                        if (result.errors) {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: Array.isArray(result.errors) ? result.errors.join(', ') : result.errors
                            });
                        } else {
                            frappe.show_alert({ message: 'Phone number updated successfully', indicator: 'green' }, 5);
                            this.refresh_current_account();
                        }
                    },
                    error: (err) => {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: err?.responseJSON?.exception || err?.message || 'Failed to update phone number'
                        });
                    }
                });
            }
        });

        d.show();
    }

    /* ── Actions: Validate / Delete Merchant ─────────── */

    validate_merchant(merchantId) {
        frappe.confirm(
            'Are you sure you want to validate this merchant?',
            () => {
                frappe.call({
                    method: 'admin_panel.api.admin_api.validate_merchant_api',
                    args: { merchant_id: merchantId },
                    freeze: true,
                    freeze_message: 'Validating merchant...',
                    callback: (res) => {
                        const result = res.message || {};
                        if (result.errors) {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: Array.isArray(result.errors) ? result.errors.join(', ') : result.errors
                            });
                        } else {
                            frappe.show_alert({ message: 'Merchant validated successfully', indicator: 'green' }, 5);
                            this.refresh_current_account();
                        }
                    },
                    error: (err) => {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: err?.responseJSON?.exception || err?.message || 'Failed to validate merchant'
                        });
                    }
                });
            }
        );
    }

    delete_merchant(merchantId) {
        frappe.confirm(
            'Are you sure you want to delete this merchant? This action cannot be undone.',
            () => {
                frappe.call({
                    method: 'admin_panel.api.admin_api.delete_merchant_api',
                    args: { merchant_id: merchantId },
                    freeze: true,
                    freeze_message: 'Deleting merchant...',
                    callback: (res) => {
                        const result = res.message || {};
                        if (result.errors) {
                            frappe.msgprint({
                                title: 'Error',
                                indicator: 'red',
                                message: Array.isArray(result.errors) ? result.errors.join(', ') : result.errors
                            });
                        } else {
                            frappe.show_alert({ message: 'Merchant deleted successfully', indicator: 'green' }, 5);
                            this.refresh_current_account();
                        }
                    },
                    error: (err) => {
                        frappe.msgprint({
                            title: 'Error',
                            indicator: 'red',
                            message: err?.responseJSON?.exception || err?.message || 'Failed to delete merchant'
                        });
                    }
                });
            }
        );
    }

    /* ── View Document ───────────────────────────────── */

    view_document(fileKey) {
        if (!fileKey) return;
        frappe.show_alert({
            message: __('Open the Account Upgrade Request form to view the document.'),
            indicator: 'blue'
        }, 5);
    }
}
