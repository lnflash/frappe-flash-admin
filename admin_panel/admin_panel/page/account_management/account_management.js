frappe.pages['account-management'].on_page_load = function(wrapper) {
    if (!frappe.user_roles.includes('Accounts Manager')) {
        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Flash Account Manager',
            single_column: true
        });
        
        page.main.html(`
            <div class="text-center mt-5">
                <div class="alert alert-warning">
                    <h4>Access Denied</h4>
                    <p>You do not have permission to access this page. Please contact your administrator to get the "Account Manager" role.</p>
                </div>
            </div>
        `);
        return;
    }

    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Flash Account Manager',
        single_column: true
    });

    new FlashAccountManager(page);
};

const AccountLevels = {
    TRIAL: "ZERO",
    PERSONAL: "ONE",
    PRO: "TWO",
    MERCHANT: "THREE"
};

const AccountStatus = {
    PENDING: "Pending",
    REJECTED: "Rejected",
    APPROVED: "Approved"
};

const ACCOUNT_LEVEL_MAP = {
    [AccountLevels.TRIAL]: 'Trial',
    [AccountLevels.PERSONAL]: 'Personal',
    [AccountLevels.PRO]: 'Pro',
    [AccountLevels.MERCHANT]: 'Merchant'
};

const LEVEL_BADGE_MAP = {
    [AccountLevels.PERSONAL]: 'badge-personal',
    [AccountLevels.PRO]: 'badge-business',
    [AccountLevels.MERCHANT]: 'badge-merchant'
};

const STATUS_BADGE_MAP = {
    [AccountStatus.APPROVED]: 'badge-approved',
    [AccountStatus.REJECTED]: 'badge-rejected',
    [AccountStatus.PENDING]: 'badge-pending'
};

const accountLevels = Object.entries(ACCOUNT_LEVEL_MAP).map(([value, label]) => ({ label, value }));

function getAccountLevelLabel(level) {
    return ACCOUNT_LEVEL_MAP[level] || level;
}

function getLevelBadgeClass(level) {
    return LEVEL_BADGE_MAP[level] || 'badge-merchant';
}

function getStatusBadgeClass(status) {
    return STATUS_BADGE_MAP[status] || 'badge-pending';
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

class FlashAccountManager {
    constructor(page) {
        this.page = page;
        this.current_account_data = null;
        this.selected_request = null;
        this.upgrade_requests = [];
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
        this.load_upgrade_requests();
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
            filterStatus: main.find('#filter-status'),
            filterLevel: main.find('#filter-level')
        };
    }

    create_layout() {
        this.page.main.html(`
            <style>
                .flash-account-manager {
                    --color-primary: #007856;
                    --color-accent: #E8D315;
                    --color-background: #F1F1F1;
                    --color-layer: #FFFFFF;
                    --color-text01: #212121;
                    --color-text02: #939998;
                    --color-border01: #DDE3E1;
                    --color-button01: #002118;
                    --color-green: #00A700;
                    --color-error: #DC2626;
                    --color-warning: #F59E0B;
                }
                
                .flash-account-manager {
                    max-width: 1400px;
                    margin: 0 auto;
                }
                
                .modern-search-card {
                    background: var(--color-layer);
                    border-radius: 16px;
                    padding: 24px;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
                    border: 1px solid var(--color-border01);
                    margin-bottom: 24px;
                }
                
                .search-title {
                    font-size: 18px;
                    font-weight: 600;
                    color: var(--color-text01);
                    margin-bottom: 16px;
                }
                
                .modern-search-wrapper {
                    display: flex;
                    gap: 12px;
                    align-items: center;
                }
                
                .modern-search-input {
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
                
                .modern-search-input:focus {
                    outline: none;
                    border-color: var(--color-primary);
                    box-shadow: 0 0 0 3px rgba(0, 120, 86, 0.1);
                }
                
                .modern-search-input::placeholder {
                    color: var(--color-text02);
                }

                .modern-search-select {
                    max-width: 250px;
                }

                .modern-btn {
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
                
                .modern-btn-primary {
                    background: var(--color-primary);
                    color: white;
                }
                
                .modern-btn-primary:hover {
                    background: #005a42;
                    transform: translateY(-1px);
                    box-shadow: 0 4px 12px rgba(0, 120, 86, 0.2);
                }
                
                .modern-btn-secondary {
                    background: var(--color-layer);
                    color: var(--color-text01);
                    border: 2px solid var(--color-border01);
                }
                
                .modern-btn-secondary:hover {
                    background: var(--color-background);
                    border-color: var(--color-text02);
                }
                
                .modern-requests-card {
                    background: var(--color-layer);
                    border-radius: 16px;
                    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
                    border: 1px solid var(--color-border01);
                    overflow: hidden;
                    margin-bottom: 24px;
                }
                
                .modern-card-header {
                    padding: 20px 24px;
                    background: linear-gradient(135deg, var(--color-primary) 0%, #005a42 100%);
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .modern-card-title {
                    font-size: 20px;
                    font-weight: 600;
                    color: white;
                    margin: 0;
                }
                
                .modern-table-wrapper {
                    overflow-x: auto;
                }
                
                .modern-table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                }
                
                .modern-table thead {
                    background: var(--color-background);
                }
                
                .modern-table th {
                    padding: 16px 20px;
                    text-align: left;
                    font-size: 13px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    border-bottom: 2px solid var(--color-border01);
                }
                
                .modern-table tbody tr {
                    cursor: pointer;
                    transition: all 0.2s ease;
                    border-bottom: 1px solid var(--color-border01);
                }
                
                .modern-table tbody tr:hover {
                    background: rgba(0, 120, 86, 0.03);
                }
                
                .modern-table tbody tr.selected {
                    background: rgba(0, 120, 86, 0.15) !important;
                    border-left: 4px solid var(--color-primary);
                }
                
                .modern-table td {
                    padding: 16px 20px;
                    color: var(--color-text01);
                    font-size: 14px;
                }
                
                .modern-badge {
                    display: inline-flex;
                    align-items: center;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                
                .badge-personal {
                    background: rgba(0, 120, 86, 0.1);
                    color: var(--color-primary);
                }
                
                .badge-business {
                    background: rgba(232, 211, 21, 0.15);
                    color: #b8a00e;
                }
                
                .badge-merchant {
                    background: rgba(245, 158, 11, 0.15);
                    color: var(--color-warning);
                }
                
                .badge-pending {
                    background: rgba(245, 158, 11, 0.15);
                    color: var(--color-warning);
                }

                .badge-approved {
                    background: #d4f7d9;
                    color: #15803d;
                }

                .badge-rejected {
                    background: #fde2e2;
                    color: #b91c1c;
                }
                
                .modern-icon-btn {
                    padding: 8px 12px;
                    border-radius: 8px;
                    border: none;
                    cursor: pointer;
                    transition: all 0.2s ease;
                    font-size: 14px;
                    margin: 0 4px;
                }
                
                .modern-icon-btn-success {
                    background: rgba(0, 167, 0, 0.1);
                    color: var(--color-green);
                }
                
                .modern-icon-btn-success:hover {
                    background: var(--color-green);
                    color: white;
                    transform: scale(1.05);
                }
                
                .modern-icon-btn-danger {
                    background: rgba(220, 38, 38, 0.1);
                    color: var(--color-error);
                }
                
                .modern-icon-btn-danger:hover {
                    background: var(--color-error);
                    color: white;
                    transform: scale(1.05);
                }
                
                .no-requests {
                    padding: 60px 20px;
                    text-align: center;
                    color: var(--color-text02);
                }
                
                .no-requests-icon {
                    font-size: 48px;
                    margin-bottom: 16px;
                    opacity: 0.3;
                }
                
                .loading-spinner {
                    padding: 60px 20px;
                    text-align: center;
                }
                
                .spinner {
                    width: 40px;
                    height: 40px;
                    border: 3px solid var(--color-border01);
                    border-top-color: var(--color-primary);
                    border-radius: 50%;
                    animation: spin 0.8s linear infinite;
                    margin: 0 auto 16px;
                }
                
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
                
                .modern-btn-icon {
                    width: 16px;
                    height: 16px;
                }
                
                .section-header {
                    font-size: 16px;
                    font-weight: 600;
                    color: var(--color-text01);
                    margin-bottom: 16px;
                    padding-bottom: 12px;
                    border-bottom: 2px solid var(--color-border01);
                }
                
                .detail-item {
                    margin-bottom: 16px;
                    display: flex;
                    flex-direction: column;
                    gap: 4px;
                }
                
                .detail-label {
                    font-size: 12px;
                    font-weight: 600;
                    color: var(--color-text02);
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }
                
                .detail-value {
                    font-size: 15px;
                    color: var(--color-text01);
                    font-weight: 500;
                }

                .notes-box {
                    background: var(--color-background);
                    padding: 16px;
                    border-radius: 8px;
                    font-size: 14px;
                    color: var(--color-text01);
                    margin-top: 8px;
                    line-height: 1.6;
                    border: 1px solid var(--color-border01);
                }

                /* MOBILE UI IMPROVEMENTS */
                @media (max-width: 768px) {
                    .modern-search-wrapper {
                        flex-direction: column;
                        align-items: stretch;
                    }

                    .modern-search-input {
                        max-width: 100%;
                        width: 100%;
                    }

                    .modern-btn {
                        width: 100%;
                        justify-content: center;
                    }

                    .modern-table th, 
                    .modern-table td {
                        padding: 12px 10px;
                        font-size: 13px;
                    }

                    /* Make table horizontally scrollable */
                    .modern-table-wrapper {
                        overflow-x: auto;
                    }

                    /* Remove fixed paddings on cards */
                    .modern-search-card,
                    .modern-requests-card {
                        padding: 16px !important;
                    }

                    .modern-icon-btn-success {
                        margin-bottom: 5px;
                    }

                    /* Details panel spacing */
                    .request-details .card-body {
                        padding: 16px !important;
                    }

                    /* Stack action buttons */
                    .request-details .d-flex {
                        flex-direction: column;
                    }

                    .request-details .d-flex button {
                        width: 100%;
                    }
                }
            </style>

            <div class="flash-account-manager m-3">
                <!-- Search Bar -->
                <div class="modern-search-card">
                    <div class="modern-search-wrapper" style="margin-bottom:20px;">
                        <input 
                            type="text" 
                            id="search-input" 
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
                            <option value=${AccountStatus.PENDING}>Pending</option>
                            <option value=${AccountStatus.APPROVED}>Approved</option>
                            <option value=${AccountStatus.REJECTED}>Rejected</option>
                        </select>
                        <select id="filter-level" class="modern-search-input modern-search-select">
                            <option value="">Requested Level (All)</option>
                            <option value=${AccountLevels.TRIAL}>Trial</option>
                            <option value=${AccountLevels.PERSONAL}>Personal</option>
                            <option value=${AccountLevels.PRO}>Pro</option>
                            <option value=${AccountLevels.MERCHANT}>Merchant</option>
                        </select>
                    </div>
                </div>

                <!-- Upgrade Requests Section -->
                <div class="modern-requests-card">
                    <div class="modern-card-header">
                        <h5 class="modern-card-title">
                            <i class="fa fa-level-up" style="margin-right: 10px;"></i>
                            Account Upgrade Requests
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
                                        <th>Upgrade Type</th>
                                        <th>Submitted</th>
                                        <th>Status</th>
                                        <th style="text-align: center;">Actions</th>
                                    </tr>
                                </thead>
                                <tbody class="requests-tbody">
                                    <!-- Populated dynamically -->
                                </tbody>
                            </table>
                            <div class="no-requests" style="display: none;">
                                <div class="no-requests-icon">📋</div>
                                <p style="font-size: 16px; font-weight: 500;">No pending upgrade requests</p>
                                <p style="font-size: 14px;">New requests will appear here when submitted</p>
                            </div>
                        </div>
                    </div>
                    <!-- Pagination Controls -->
                    <div class="pagination-controls" style="display: none; padding: 16px 24px; border-top: 1px solid var(--color-border01); display: flex; justify-content: space-between; align-items: center;">
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
                            Request Details
                        </h5>
                        <button class="modern-btn modern-btn-secondary btn-close-details">
                            <i class="fa fa-times"></i>
                            Close
                        </button>
                    </div>
                    <div class="card-body" style="padding: 24px;">
                        <!-- Personal Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-user" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Personal Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Username</span>
                                        <span class="detail-value detail-username"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Phone</span>
                                        <span class="detail-value detail-phone"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Full Name</span>
                                        <span class="detail-value detail-fullname"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Email</span>
                                        <span class="detail-value detail-email"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Business Information -->
                        <div class="detail-section business-info mb-4" style="display: none;">
                            <h6 class="section-header">
                                <i class="fa fa-building" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Business Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Business Name</span>
                                        <span class="detail-value detail-business-name"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Business Address</span>
                                        <span class="detail-value detail-business-address"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Terminal Requested</span>
                                        <span class="detail-value detail-terminal-requested"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Bank Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-bank" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Bank Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Bank Name</span>
                                        <span class="detail-value detail-bank-name"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Account Number</span>
                                        <span class="detail-value detail-account-number"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Currency</span>
                                        <span class="detail-value detail-currency"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Bank Branch</span>
                                        <span class="detail-value detail-bank-branch"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Account Type</span>
                                        <span class="detail-value detail-account-type"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">ID Document</span>
                                        <span class="detail-value detail-id-document"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Request Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-info-circle" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Request Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Current Level</span>
                                        <span class="detail-value detail-current-level"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Requested Level</span>
                                        <span class="detail-value detail-requested-level"></span>
                                    </div><div class="detail-item">
                                        <span class="detail-label">Status</span>
                                        <span class="detail-value detail-status"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Approved/Rejected By</span>
                                        <span class="detail-value detail-approved-by"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Request ID</span>    
                                        <span class="detail-value detail-request-id"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Submitted</span>
                                        <span class="detail-value detail-submitted"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Approval/Rejection Date</span>
                                        <span class="detail-value detail-approval-date"></span>
                                    </div>
                                </div>
                            </div>
                            <div class="row mt-3 rejection-reason">
                                <div class="col-12">
                                    <span class="detail-label">Rejection Reason</span>
                                    <p class="detail-rejection-reason notes-box"></p>
                                </div>
                            </div>
                        </div>

                        <div class="d-flex gap-2 justify-content-end" style="gap: 12px;">
                            <button class="modern-btn modern-btn-primary btn-approve" style="background: var(--color-green);">
                                <i class="fa fa-check"></i>
                                Approve
                            </button>
                            <button class="modern-btn modern-btn-primary btn-reject" style="background: var(--color-error);">
                                <i class="fa fa-times"></i>
                                Reject
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Search Results -->
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

    show_id_document(fileUrl) {
        const d = new frappe.ui.Dialog({
            title: 'ID Document',
            size: 'large',
            fields: [
                {
                    fieldtype: 'HTML',
                    fieldname: 'preview',
                }
            ],
            primary_action_label: 'Close',
            primary_action() {
                d.hide();
            }
        });

        d.fields_dict.preview.$wrapper.html(`
                <div style="text-align:center;">
                    <img
                        src="${fileUrl}"
                        style="
                            max-width: 100%;
                            max-height: 70vh;
                            border-radius: 10px;
                            border: 1px solid #DDE3E1;
                        "
                    />
                </div>
            `);
        d.show();
    }

    prefetch_id_document_url(fileKey, containerEl) {
        frappe.call({
            method: 'admin_panel.api.admin_api.get_id_document_url',
            args: { file_key: fileKey },
            callback: (response) => {
                if (response.message && response.message.success) {
                    const preSignedUrl = response.message.url;
                    containerEl.html(`
                        <button class="btn btn-sm btn-secondary btn-view-id-doc">
                            <i class="fa fa-eye"></i> View document
                        </button>
                    `);
                    containerEl.find('.btn-view-id-doc').on('click', () => {
                        this.show_id_document(preSignedUrl);
                    });
                } else {
                    containerEl.html(`
                        <button class="btn btn-sm btn-danger btn-view-id-doc" disabled>
                            <i class="fa fa-exclamation-triangle"></i> Failed to load
                        </button>
                    `);
                }
            },
            error: () => {
                containerEl.html(`
                    <button class="btn btn-sm btn-danger btn-view-id-doc" disabled>
                        <i class="fa fa-exclamation-triangle"></i> Failed to load
                    </button>
                `);
            }
        });
    }

    bind_events() {
        const main = this.page.main;
        const debouncedSearch = debounce(() => this.search(), 300);

        main.find('.btn-search').on('click', () => this.search());
        this.$cache.searchInput.on('keypress', (e) => { if (e.which === 13) this.search(); });
        this.$cache.searchInput.on('input', debouncedSearch);

        main.find('.btn-refresh').on('click', () => this.load_upgrade_requests());
        main.find('.btn-close-details').on('click', () => this.$cache.requestDetails.hide());
        main.find('.btn-approve').on('click', () => this.approve_request(this.selected_request));
        main.find('.btn-reject').on('click', () => this.reject_request(this.selected_request));

        this.$cache.filterStatus.on('change', () => { this.current_page = 1; this.load_upgrade_requests(); });
        this.$cache.filterLevel.on('change', () => { this.current_page = 1; this.load_upgrade_requests(); });

        // Pagination events
        main.find('.btn-first-page').on('click', () => this.go_to_page(1));
        main.find('.btn-prev-page').on('click', () => this.go_to_page(this.current_page - 1));
        main.find('.btn-next-page').on('click', () => this.go_to_page(this.current_page + 1));
        main.find('.btn-last-page').on('click', () => this.go_to_page(this.total_pages));
    }

    create_request_row(req, showActions = true) {
        const levelBadge = getLevelBadgeClass(req.requested_level);
        const statusBadge = getStatusBadgeClass(req.status);
        const isPending = req.status === AccountStatus.PENDING;

        const actionsHtml = showActions && isPending
            ? `<td style="text-align:center;">
                <button class="modern-icon-btn modern-icon-btn-success btn-quick-approve" data-request-id="${req.name}" title="Approve"><i class="fa fa-check"></i></button>
                <button class="modern-icon-btn modern-icon-btn-danger btn-quick-reject" data-request-id="${req.name}" title="Reject"><i class="fa fa-times"></i></button>
               </td>`
            : `<td style="text-align:center;"><span>-</span></td>`;

        const row = $(`
            <tr class="request-row" data-request-id="${req.name}">
                <td><strong>${req.username || '-'}</strong></td>
                <td>${this.formatPhone(req.phone_number)}</td>
                <td><span class="modern-badge ${levelBadge}">${getAccountLevelLabel(req.requested_level)}</span></td>
                <td>${this.formatDateTime(req.creation)}</td>
                <td><span class="modern-badge ${statusBadge}">${req.status || AccountStatus.PENDING}</span></td>
                ${actionsHtml}
            </tr>
        `);

        row.on('click', (e) => {
            if (!$(e.target).closest('button').length) {
                this.page.main.find('.request-row').removeClass('selected');
                row.addClass('selected');
                this.show_request_details(req);
            }
        });

        row.find('.btn-quick-approve').on('click', (e) => { e.stopPropagation(); this.approve_request(req); });
        row.find('.btn-quick-reject').on('click', (e) => { e.stopPropagation(); this.reject_request(req); });

        return row;
    }

    go_to_page(page) {
        if (page < 1 || page > this.total_pages) return;
        this.current_page = page;
        this.load_upgrade_requests();
    }

    load_upgrade_requests() {
        this.$cache.requestsLoading.show();
        this.$cache.requestsTable.hide();
        this.$cache.noRequests.hide();
        this.$cache.requestDetails.hide();
        this.$cache.paginationControls.hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.get_upgrade_requests',
            args: {
                status: this.$cache.filterStatus.val(),
                requested_level: this.$cache.filterLevel.val(),
                page: this.current_page,
                page_size: this.page_size
            },
            callback: (response) => {
                this.$cache.requestsLoading.hide();
                const result = response.message || {};
                this.upgrade_requests = result.data || [];
                this.total_count = result.total || 0;
                this.total_pages = result.total_pages || 1;
                this.current_page = result.page || 1;
                this.render_requests();
                this.update_pagination();
            },
            error: () => {
                this.$cache.requestsLoading.hide();
                frappe.show_alert({ message: 'Failed to load upgrade requests', indicator: 'red' }, 5);
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

        if (this.upgrade_requests.length === 0) {
            this.$cache.requestsTable.hide();
            this.$cache.noRequests.show();
            return;
        }

        this.$cache.requestsTable.show();
        this.$cache.noRequests.hide();

        this.upgrade_requests.forEach((req) => {
            this.$cache.requestsTbody.append(this.create_request_row(req));
        });
    }

    show_request_details(req) {
        this.selected_request = req;
        const panel = this.page.main.find('.request-details');

        const approveBtn = panel.find('.btn-approve');
        const rejectBtn = panel.find('.btn-reject');
        if (req.status === AccountStatus.PENDING) {
            approveBtn.show();
            rejectBtn.show();
        } else {
            approveBtn.hide();
            rejectBtn.hide();
        }

        const rejectionResonContainer = panel.find(".rejection-reason") 
        if(req.rejection_reason){
            rejectionResonContainer.show()
        }else{
            rejectionResonContainer.hide()
        }
        
        // Fill personal info
        panel.find('.detail-username').text(req.username || '-');
        panel.find('.detail-phone').text(this.formatPhone(req.phone_number) || '-');
        panel.find('.detail-fullname').text(req.full_name || '-');
        panel.find('.detail-email').text(req.email || '-');

        // Business info
        if (req.requested_level === AccountLevels.PRO || req.requested_level === AccountLevels.MERCHANT) {
            panel.find('.business-info').show();
            panel.find('.detail-business-name').text(req.business_name || '-');
            panel.find('.detail-business-address').text(req.business_address || '-');
            panel.find('.detail-terminal-requested').text(req.terminal_requested ? 'Yes' : 'No');
        } else {
            panel.find('.business-info').hide();
        }

        // Bank info
        if (req.requested_level === AccountLevels.MERCHANT) {
            panel.find('.detail-bank-name').text(req.bank_name || '-');
            panel.find('.detail-account-number').text(req.account_number || '-');
            panel.find('.detail-account-type').text(req.account_type || '-');
            panel.find('.detail-bank-branch').text(req.bank_branch || '-');
            panel.find('.detail-currency').text(req.currency || '-');
            const idDocEl = panel.find('.detail-id-document');
            idDocEl.empty();
                    
            if (req.id_document) {
                idDocEl.html(`
                    <button class="btn btn-sm btn-secondary btn-view-id-doc" disabled>
                        <i class="fa fa-spinner fa-spin"></i> Loading...
                    </button>
                `);

                // Pre-fetch the document URL when details panel is rendered
                this.prefetch_id_document_url(req.id_document, idDocEl);
            } else {
                idDocEl.text('-');
            }
            panel.find('.detail-section:has(.fa-bank)').show();
        } else {
            panel.find('.detail-section:has(.fa-bank)').hide();
        }

        // Request info
        panel.find('.detail-current-level').text(getAccountLevelLabel(req.current_level) || '-');
        panel.find('.detail-requested-level').text(getAccountLevelLabel(req.requested_level) || '-');
        panel.find('.detail-status').text(getAccountLevelLabel(req.status) || '-');
        panel.find('.detail-approved-by').text(getAccountLevelLabel(req.approved_by) || '-');
        panel.find('.detail-submitted').text(this.formatDateTime(req.creation));
        panel.find('.detail-approval-date').text(this.formatDateTime(req.approval_date));
        panel.find('.detail-request-id').text(req.name);
        panel.find('.detail-rejection-reason').text(req.rejection_reason);

        panel.show();

        const row = this.page.main.find(`tr[data-request-id="${req.name}"]`);
        if (row.length) {
            row[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    approve_request(req){ 
        if(!req) return; 
        frappe.confirm(
            `Are you sure you want to approve the upgrade request for ${req.username}?`,
            () => frappe.call({
                method: 'admin_panel.api.admin_api.approve_upgrade_request',
                args: { request_id: req.name },
                freeze: true,
                freeze_message: "Approving request...",
                callback: (r) => {
                    if (!r.exc) {
                        frappe.msgprint("Request approved successfully");
                        this.close_details();
                        this.load_upgrade_requests();
                    }
                }
            })
        )
    }
    
    reject_request(req){
        if(!req) return;

        let d = new frappe.ui.Dialog({
            title: "Reject Upgrade Request",
            fields: [
                {
                    fieldname: "reason",
                    fieldtype: "Small Text",
                    label: "Reason for Rejection",
                    reqd: 1
                }
            ],
            primary_action_label: "Reject",
            primary_action: (values) => {
                frappe.call({
                    method: 'admin_panel.api.admin_api.reject_upgrade_request',
                    args: { request_id: req.name, reason: values.reason },
                    freeze: true,
                    freeze_message: "Rejecting request...",
                    callback: (r) => {
                        if (!r.exc) {
                            frappe.msgprint("Request rejected");
                            this.close_details();
                            this.load_upgrade_requests();
                        }
                    }
                })
                d.hide();
            }
        });

        d.show();
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
            method: 'admin_panel.api.admin_api.search_account',
            args: { id: input },
            callback: (res) => {
                this.$cache.searchLoading.hide();
                const results = res.message || [];
                this.show_search_results(results);
            },
            error: (e) => {
                this.$cache.searchLoading.hide();
                this.show_search_error(e.message || 'Account not found');
            }
        });
    }

    show_search_results(results) {
        this.$cache.requestsTbody.empty();

        if (!results.length) {
            this.$cache.noRequests.show();
            this.$cache.requestsTable.hide();
            this.show_search_error('No accounts found');
            return;
        }

        this.$cache.noRequests.hide();
        this.$cache.requestsTable.show();

        results.forEach(account => {
            this.$cache.requestsTbody.append(this.create_request_row(account, true));
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