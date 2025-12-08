frappe.pages['cashout-requests'].on_page_load = function(wrapper) {
    if (!frappe.user_roles.includes('Accounts Manager')) {
        var page = frappe.ui.make_app_page({
            parent: wrapper,
            title: 'Flash Cashout Manager',
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
        title: 'Flash Cashout Manager',
        single_column: true
    });

    new FlashCashoutManager(page);
};

class FlashCashoutManager {
    constructor(page) {
        this.page = page;
        this.selected_request = null;
        this.cashout_requests = [];
        this.setup_page();
    }

    setup_page() {
        this.create_layout();
        this.bind_events();
        this.load_cashout_requests();
    }

    create_layout() {
        this.page.main.html(`
            <style>
                .flash-cashout-manager {
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
                    --color-blue: #2563EB;
                }
                
                .flash-cashout-manager {
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
                
                .badge-pending {
                    background: rgba(245, 158, 11, 0.15);
                    color: var(--color-warning);
                }

                .badge-completed {
                    background: #d4f7d9;
                    color: #15803d;
                }

                .badge-expired {
                    background: #fde2e2;
                    color: #b91c1c;
                }

                .badge-usd {
                    background: rgba(37, 99, 235, 0.1);
                    color: var(--color-blue);
                }

                .badge-jmd {
                    background: rgba(232, 211, 21, 0.15);
                    color: #b8a00e;
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

                .amount-highlight {
                    font-size: 24px;
                    font-weight: 700;
                    color: var(--color-primary);
                }

                .confirmation-section {
                    background: var(--color-background);
                    padding: 24px;
                    border-radius: 12px;
                    margin-top: 24px;
                    border: 2px solid var(--color-border01);
                }

                .confirmation-input {
                    width: 100%;
                    padding: 14px 18px;
                    border: 2px solid var(--color-border01);
                    border-radius: 12px;
                    font-size: 16px;
                    font-family: monospace;
                    letter-spacing: 2px;
                    text-align: center;
                    transition: all 0.2s ease;
                }

                .confirmation-input:focus {
                    outline: none;
                    border-color: var(--color-primary);
                    box-shadow: 0 0 0 3px rgba(0, 120, 86, 0.1);
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

                    .modern-table-wrapper {
                        overflow-x: auto;
                    }

                    .modern-search-card,
                    .modern-requests-card {
                        padding: 16px !important;
                    }

                    .request-details .card-body {
                        padding: 16px !important;
                    }

                    .request-details .d-flex {
                        flex-direction: column;
                    }

                    .request-details .d-flex button {
                        width: 100%;
                    }

                    .amount-highlight {
                        font-size: 20px;
                    }
                }
            </style>

            <div class="flash-cashout-manager m-3">
                <!-- Search Bar -->
                <div class="modern-search-card">
                    <div class="modern-search-wrapper" style="margin-bottom:20px;">
                        <input 
                            type="text" 
                            id="search-input" 
                            class="modern-search-input search-input" 
                            placeholder="Enter order ID or username"
                        >
                        <button class="modern-btn modern-btn-primary btn-search">
                            <i class="fa fa-search"></i>
                            Search
                        </button>
                    </div>
                    <div class="modern-search-wrapper">
                        <select id="filter-status" class="modern-search-input modern-search-select">
                            <option value="">Status (All)</option>
                            <option value="Pending">Pending</option>
                            <option value="Completed">Completed</option>
                            <option value="Expired">Expired</option>
                        </select>
                        <select id="filter-currency" class="modern-search-input modern-search-select">
                            <option value="">Currency (All)</option>
                            <option value="USD">USD</option>
                            <option value="JMD">JMD</option>
                        </select>
                    </div>
                </div>

                <!-- Cashout Requests Section -->
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
                                        <th>Order ID</th>
                                        <th>Username</th>
                                        <th>Send Amount</th>
                                        <th>Receive Amount</th>
                                        <th>Expiration</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody class="requests-tbody">
                                    <!-- Populated dynamically -->
                                </tbody>
                            </table>
                            <div class="no-requests" style="display: none;">
                                <div class="no-requests-icon">💵</div>
                                <p style="font-size: 16px; font-weight: 500;">No cashout requests</p>
                                <p style="font-size: 14px;">New requests will appear here when submitted</p>
                            </div>
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
                        <!-- Cashout Information -->
                        <div class="detail-section mb-4">
                            <h6 class="section-header">
                                <i class="fa fa-info-circle" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Cashout Information
                            </h6>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Order ID</span>
                                        <span class="detail-value detail-order-id"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Offer ID</span>
                                        <span class="detail-value detail-offer-id"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Exchange Rate</span>
                                        <span class="detail-value detail-exchange-rate"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Flash Fee</span>
                                        <span class="detail-value detail-flash-fee"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Send Amount</span>
                                        <span class="detail-value amount-highlight detail-send-amount"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Receive Amount</span>
                                        <span class="detail-value amount-highlight detail-receive-amount"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Expiration Time</span>
                                        <span class="detail-value detail-expiration"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Status</span>
                                        <span class="detail-value detail-status"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

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
                        <div class="detail-section business-info mb-4">
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
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Business Address</span>
                                        <span class="detail-value detail-business-address"></span>
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
                                </div>
                            </div>
                        </div>

                        <!-- Confirmation Section -->
                        <div class="confirmation-section pending-only">
                            <h6 class="section-header">
                                <i class="fa fa-check-circle" style="margin-right: 8px; color: var(--color-primary);"></i>
                                Payment Confirmation
                            </h6>
                            <div class="mb-3">
                                <label class="detail-label mb-2">Enter Confirmation Code</label>
                                <input 
                                    type="text" 
                                    class="confirmation-input" 
                                    id="confirmation-code" 
                                    placeholder="XXXXXX"
                                    maxlength="10"
                                >
                            </div>
                            <button class="modern-btn modern-btn-primary w-100 btn-confirm-payment" style="background: var(--color-green);">
                                <i class="fa fa-check"></i>
                                Confirm Payment Completed
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

    bind_events() {
        const main = this.page.main;

        main.find('.btn-search').on('click', () => this.search());
        main.find('.search-input').on('keypress', (e) => { if(e.which===13) this.search(); });

        main.find('.btn-refresh').on('click', () => this.load_cashout_requests());
        main.find('.btn-close-details').on('click', () => main.find('.request-details').hide());
        main.find('.btn-confirm-payment').on('click', () => this.confirm_payment());
        
        main.find('#filter-status').on('change', () => this.load_cashout_requests());
        main.find('#filter-currency').on('change', () => this.load_cashout_requests());
    }

    load_cashout_requests() {
        const main = this.page.main;
        main.find('.requests-loading').show();
        main.find('.requests-list table').hide();
        main.find('.no-requests').hide();
        main.find('.request-details').hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.get_cashout_requests',
            args: {
                status: this.page.main.find('#filter-status').val(),
                currency: this.page.main.find('#filter-currency').val(),
            },
            callback: (response) => {
                main.find('.requests-loading').hide();
                this.cashout_requests = response.message || [];
                this.render_requests();
            },
            error: () => {
                main.find('.requests-loading').hide();
                frappe.show_alert({ message: 'Failed to load cashout requests', indicator: 'red' }, 5);
            }
        });
    }

    render_requests() {
        const tbody = this.page.main.find('.requests-tbody');
        tbody.empty();

        if (this.cashout_requests.length === 0) {
            this.page.main.find('.requests-list table').hide();
            this.page.main.find('.no-requests').show();
            return;
        }

        this.page.main.find('.requests-list table').show();
        this.page.main.find('.no-requests').hide();

        this.cashout_requests.forEach((req) => {
            const statusBadge = req.status === "Completed" ? "badge-completed" : 
                              req.status === "Expired" ? "badge-expired" : "badge-pending";
            const currencyBadge = req.currency === "USD" ? "badge-usd" : "badge-jmd";
            
            const row = $(`
                <tr class="request-row" data-request-id="${req.name}">
                    <td><strong>${req.order_id || '-'}</strong></td>
                    <td>${req.username || '-'}</td>
                    <td>${this.formatAmount(req.send_amount, req.send_currency)}</td>
                    <td>
                        <span class="modern-badge ${currencyBadge}">
                            ${this.formatAmount(req.receive_amount, req.currency)}
                        </span>
                    </td>
                    <td>${this.formatDateTime(req.expiration_time)}</td>
                    <td><span class="modern-badge ${statusBadge}">${req.status || 'Pending'}</span></td>
                </tr>
            `);

            row.on('click', () => { 
                this.page.main.find('.request-row').removeClass('selected');
                row.addClass('selected');
                this.show_request_details(req); 
            });

            tbody.append(row);
        });
    }

    show_request_details(req) {
        this.selected_request = req;
        const panel = this.page.main.find('.request-details');

        // Show/hide confirmation section based on status
        const confirmSection = panel.find('.confirmation-section');
        if (req.status === "Pending") {
            confirmSection.show();
        } else {
            confirmSection.hide();
        }
        
        // Fill cashout info
        panel.find('.detail-order-id').text(req.order_id || '-');
        panel.find('.detail-offer-id').text(req.offer_id || '-');
        panel.find('.detail-exchange-rate').text(req.exchange_rate || '-');
        panel.find('.detail-flash-fee').text(this.formatAmount(req.flash_fee, req.send_currency) || '-');
        panel.find('.detail-send-amount').text(this.formatAmount(req.send_amount, req.send_currency) || '-');
        panel.find('.detail-receive-amount').text(this.formatAmount(req.receive_amount, req.currency) || '-');
        panel.find('.detail-expiration').text(this.formatDateTime(req.expiration_time));
        
        const statusBadge = req.status === "Completed" ? "badge-completed" : 
                          req.status === "Expired" ? "badge-expired" : "badge-pending";
        panel.find('.detail-status').html(`<span class="modern-badge ${statusBadge}">${req.status || 'Pending'}</span>`);

        // Fill user info
        panel.find('.detail-username').text(req.username || '-');
        panel.find('.detail-phone').text(this.formatPhone(req.phone_number) || '-');
        panel.find('.detail-fullname').text(req.full_name || '-');
        panel.find('.detail-email').text(req.email || '-');

        // Business info
        if (req.business_name) {
            panel.find('.business-info').show();
            panel.find('.detail-business-name').text(req.business_name || '-');
            panel.find('.detail-business-address').text(req.business_address || '-');
        } else {
            panel.find('.business-info').hide();
        }

        // Bank info
        panel.find('.detail-bank-name').text(req.bank_name || '-');
        panel.find('.detail-account-number').text(req.account_number || '-');
        panel.find('.detail-currency').text(req.currency || '-');
        panel.find('.detail-bank-branch').text(req.bank_branch || '-');
        panel.find('.detail-account-type').text(req.account_type || '-');

        // Clear confirmation code input
        panel.find('#confirmation-code').val('');

        panel.show();

        // Scroll to the selected row
        const row = this.page.main.find(`tr[data-request-id="${req.name}"]`);
        if (row.length) {
            row[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }

    confirm_payment() {
        if (!this.selected_request) return;

        const code = this.page.main.find('#confirmation-code').val().trim();
        if (!code) {
            frappe.show_alert({ message: 'Please enter confirmation code', indicator: 'orange' }, 3);
            return;
        }

        frappe.confirm(
            `Are you sure you want to confirm payment for order ${this.selected_request.order_id}?`,
            () => {
                frappe.call({
                    method: 'admin_panel.api.admin_api.confirm_cashout_payment',
                    args: { 
                        request_id: this.selected_request.name,
                        confirmation_code: code
                    },
                    freeze: true,
                    freeze_message: "Confirming payment...",
                    callback: (r) => {
                        if (!r.exc) {
                            frappe.msgprint("Payment confirmed successfully");
                            this.page.main.find('.request-details').hide();
                            this.load_cashout_requests();
                        }
                    }
                });
            }
        );
    }

    search() {
        const query = this.page.main.find('.search-input').val().trim();
        if (!query) {
            frappe.show_alert({ message: 'Please enter an order ID or username', indicator: 'orange' }, 3);
            return;
        }

        const main = this.page.main;
        main.find('.search-loading').show();
        main.find('.search-error').hide();
        main.find('.request-details').hide();

        frappe.call({
            method: 'admin_panel.api.admin_api.search_cashout',
            args: { query },
            callback: (res) => {
                const results = res.message || [];
                main.find('.search-loading').hide();
                this.show_search_results(results);
            },
            error: (e) => {
                main.find('.search-loading').hide();
                this.show_search_error(e.message || 'Request not found');
            }
        });
    }

    show_search_results(results) {
        const main = this.page.main;
        const tbody = main.find('.requests-tbody');

        tbody.empty();

        if (!results.length) {
            main.find('.no-requests').show();
            main.find('.requests-list table').hide();
            this.show_search_error('No cashout requests found');
            return;
        }

        main.find('.no-requests').hide();
        main.find('.requests-list table').show();

        results.forEach(req => {
            const statusBadge = req.status === "Completed" ? "badge-completed" : 
                              req.status === "Expired" ? "badge-expired" : "badge-pending";
            const currencyBadge = req.currency === "USD" ? "badge-usd" : "badge-jmd";
            
            const row = $(`
                <tr class="request-row" data-request-id="${req.name}">
                    <td><strong>${req.order_id || '-'}</strong></td>
                    <td>${req.username || '-'}</td>
                    <td>${this.formatAmount(req.send_amount, req.send_currency)}</td>
                    <td>
                        <span class="modern-badge ${currencyBadge}">
                            ${this.formatAmount(req.receive_amount, req.currency)}
                        </span>
                    </td>
                    <td>${this.formatDateTime(req.expiration_time)}</td>
                    <td><span class="modern-badge ${statusBadge}">${req.status || 'Pending'}</span></td>
                </tr>
            `);

            row.on('click', () => { 
                this.page.main.find('.request-row').removeClass('selected');
                row.addClass('selected');
                this.show_request_details(req); 
            });

            tbody.append(row);
        });
    }

    show_search_error(msg) { 
        this.page.main.find('.search-loading').hide(); 
        this.page.main.find('.search-error').show(); 
        this.page.main.find('.error-message').text(msg); 
    }

    formatPhone(phone) { 
        return phone ? phone.replace(/^(\d{3})(\d{3})(\d{2})(\d{2})$/, '+$1 $2 $3 $4') : '-'; 
    }
    
    formatDateTime(dt) { 
        return dt ? frappe.datetime.str_to_user(dt) : '-'; 
    }

    formatAmount(amount, currency) {
        if (!amount) return '-';
        const formatted = parseFloat(amount).toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        });
        return `${currency || ''} ${formatted}`;
    }
}