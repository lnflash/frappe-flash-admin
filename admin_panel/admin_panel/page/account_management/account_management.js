frappe.pages["account-management"].on_page_load = function (wrapper) {
	if (!frappe.user_roles.includes("Accounts Manager")) {
		var page = frappe.ui.make_app_page({
			parent: wrapper,
			title: "Flash Account Manager",
			single_column: true,
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

	page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Flash Account Manager",
		single_column: true,
	});

	wrapper.account_management = new FlashAccountManager(page);
};

const AccountLevels = {
	TRIAL: "ZERO",
	PERSONAL: "ONE",
	PRO: "TWO",
	MERCHANT: "THREE",
};

const AccountStatus = {
	PENDING: "Pending",
	REJECTED: "Rejected",
	APPROVED: "Approved",
	CLOSED: "Closed",
};

const ACCOUNT_LEVEL_MAP = {
	[AccountLevels.TRIAL]: "Trial",
	[AccountLevels.PERSONAL]: "Personal",
	[AccountLevels.PRO]: "Pro",
	[AccountLevels.MERCHANT]: "Merchant",
};

const LEVEL_BADGE_MAP = {
	[AccountLevels.TRIAL]: "badge-trial",
	[AccountLevels.PERSONAL]: "badge-personal",
	[AccountLevels.PRO]: "badge-business",
	[AccountLevels.MERCHANT]: "badge-merchant",
};

const STATUS_BADGE_MAP = {
	[AccountStatus.APPROVED]: "badge-approved",
	[AccountStatus.REJECTED]: "badge-rejected",
	[AccountStatus.PENDING]: "badge-pending",
	[AccountStatus.CLOSED]: "badge-closed",
};

function getAccountLevelLabel(level) {
	return ACCOUNT_LEVEL_MAP[level] || level;
}

function getLevelBadgeClass(level) {
	return LEVEL_BADGE_MAP[level] || "badge-trial";
}

function getStatusBadgeClass(status) {
	return STATUS_BADGE_MAP[status] || "badge-pending";
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
			searchInput: main.find(".search-input"),
			requestsLoading: main.find(".requests-loading"),
			requestsTable: main.find(".requests-list table"),
			noRequests: main.find(".no-requests"),
			requestDetails: main.find(".request-details"),
			pulseTiles: main.find(".pulse-tiles"),
			paginationControls: main.find(".pagination-controls"),
			requestsTbody: main.find(".requests-tbody"),
			searchLoading: main.find(".search-loading"),
			searchError: main.find(".search-error"),
			filterStatus: main.find("#filter-status"),
			filterLevel: main.find("#filter-level"),
		};
	}

	create_layout() {
		this.page.main.html(`
            <style>
                /* ═══ Ops-pulse design system — Account Management (approval queue) ═══
                   Every selector is scoped under .flash-account-manager: the old
                   block leaked global .modern-* rules into sibling desk pages. */
                .flash-account-manager {
                    --am-surface: var(--card-bg, #ffffff); --am-ink: var(--text-color, #1a2420);
                    --am-ink2: var(--text-muted, #5c6b65); --am-ink3: var(--text-light, #8fa098);
                    --am-line: var(--border-color, #e2e8e5); --am-line-soft: var(--subtle-fg, #ecf1ee);
                    --am-accent: #007856; --am-accent-ink: #007856; --am-accent-soft: #e6f3ee;
                    --am-good: #0ca30c; --am-warn: #b87d00; --am-warn-bg: #fff3d6;
                    --am-serious: #c05a32; --am-serious-bg: #fdeae2;
                    --am-shadow: 0 1px 2px rgba(26,36,32,0.05), 0 4px 14px rgba(26,36,32,0.04);
                    /* legacy aliases */
                    --color-primary: var(--am-accent); --color-background: transparent;
                    --color-layer: var(--am-surface); --color-text01: var(--am-ink);
                    --color-text02: var(--am-ink2); --color-border01: var(--am-line);
                    --color-green: var(--am-good); --color-error: var(--am-serious);
                    --color-warning: var(--am-warn);
                    max-width: 1400px; margin: 0 auto;
                }
                [data-theme="dark"] .flash-account-manager, .dark .flash-account-manager {
                    --am-accent: #1e9e75; --am-accent-ink: #4cc29e; --am-accent-soft: #12352a;
                    --am-good: #35c135; --am-warn: #fab219; --am-warn-bg: #33290d;
                    --am-serious: #ec835a; --am-serious-bg: #38211a;
                    --am-shadow: 0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.25);
                }

                /* queue pulse tiles */
                .flash-account-manager .tr-tiles { display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
                    gap: 12px; margin-bottom: 14px; }
                .flash-account-manager .tr-tile { background: var(--am-surface);
                    border: 1px solid var(--am-line); border-radius: 14px;
                    box-shadow: var(--am-shadow); padding: 12px 16px; }
                .flash-account-manager .tr-tile-label { font-size: 11px; letter-spacing: 0.06em;
                    text-transform: uppercase; color: var(--am-ink2); font-weight: 650; }
                .flash-account-manager .tr-tile-value { font-size: 22px; font-weight: 650;
                    color: var(--am-ink); font-variant-numeric: tabular-nums; margin-top: 2px; }
                .flash-account-manager .tr-tile-value.warn { color: var(--am-warn); }
                .flash-account-manager .tr-tile-value.bad { color: var(--am-serious); }
                .flash-account-manager .tr-tile-sub { font-size: 11.5px; color: var(--am-ink3);
                    margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

                /* toolbar */
                .flash-account-manager .modern-search-card { background: var(--am-surface);
                    border: 1px solid var(--am-line); border-radius: 14px;
                    box-shadow: var(--am-shadow); padding: 14px 16px; margin-bottom: 14px; }
                .flash-account-manager .modern-search-wrapper { display: flex; gap: 10px;
                    flex-wrap: wrap; align-items: center; }
                .flash-account-manager .modern-search-wrapper[style*="margin-bottom"] {
                    margin-bottom: 10px !important; }
                .flash-account-manager .modern-search-input { flex: 1; min-width: 220px;
                    padding: 8px 13px; border: 1px solid var(--am-line); border-radius: 10px;
                    font-size: 13.5px; background: var(--am-surface); color: var(--am-ink); }
                .flash-account-manager .modern-search-input:focus { outline: 2px solid var(--am-accent);
                    outline-offset: 1px; border-color: var(--am-accent); }
                .flash-account-manager .modern-search-input::placeholder { color: var(--am-ink3); }
                .flash-account-manager .modern-search-select { flex: 0 1 240px; min-width: 180px;
                    appearance: auto; }

                /* buttons */
                .flash-account-manager .modern-btn { display: inline-flex; align-items: center;
                    gap: 6px; border: 1px solid var(--am-line); background: var(--am-surface);
                    color: var(--am-ink); border-radius: 9px; padding: 7px 14px; font-size: 13px;
                    font-weight: 600; cursor: pointer; transition: all 0.13s; }
                .flash-account-manager .modern-btn:hover { border-color: var(--am-accent); }
                .flash-account-manager .modern-btn:focus-visible { outline: 2px solid var(--am-accent);
                    outline-offset: 1px; }
                .flash-account-manager .modern-btn:disabled { opacity: 0.55; cursor: not-allowed; }
                .flash-account-manager .modern-btn-primary { background: var(--am-accent);
                    border-color: var(--am-accent); color: #fff; }
                .flash-account-manager .modern-btn-primary:hover { filter: brightness(1.07); }
                .flash-account-manager .modern-btn-danger { color: var(--am-serious);
                    border-color: var(--am-serious); background: transparent; }
                .flash-account-manager .modern-btn-danger:hover { background: var(--am-serious-bg); }

                /* quick actions — approve/reject icon buttons */
                .flash-account-manager .modern-icon-btn { width: 28px; height: 28px;
                    display: inline-grid; place-items: center; border-radius: 8px;
                    border: 1px solid var(--am-line); background: var(--am-surface);
                    color: var(--am-ink2); cursor: pointer; margin: 0 2px;
                    font-size: 12px; transition: all 0.13s; }
                .flash-account-manager .modern-icon-btn:hover { border-color: currentColor; }
                .flash-account-manager .modern-icon-btn:disabled { opacity: 0.5; cursor: not-allowed; }
                .flash-account-manager .modern-icon-btn-success { color: var(--am-good); }
                .flash-account-manager .modern-icon-btn-success:hover { background: var(--am-accent-soft); }
                .flash-account-manager .modern-icon-btn-danger { color: var(--am-serious); }
                .flash-account-manager .modern-icon-btn-danger:hover { background: var(--am-serious-bg); }

                /* cards */
                .flash-account-manager .modern-requests-card { background: var(--am-surface);
                    border: 1px solid var(--am-line); border-radius: 14px;
                    box-shadow: var(--am-shadow); overflow: hidden; margin-bottom: 14px; }
                .flash-account-manager .modern-card-header { display: flex; align-items: center;
                    justify-content: space-between; gap: 12px; padding: 13px 18px;
                    border-bottom: 1px solid var(--am-line); }
                .flash-account-manager .modern-card-title { margin: 0; font-size: 13.5px;
                    font-weight: 650; color: var(--am-ink); display: flex; align-items: center; }
                .flash-account-manager .modern-card-title .fa { color: var(--am-accent-ink); }

                /* table */
                .flash-account-manager .modern-table-wrapper { overflow-x: auto; }
                .flash-account-manager .modern-table { width: 100%; border-collapse: collapse;
                    font-size: 13px; }
                .flash-account-manager .modern-table th { text-align: left; font-size: 11px;
                    letter-spacing: 0.05em; text-transform: uppercase; color: var(--am-ink2);
                    font-weight: 650; padding: 10px 14px; border-bottom: 1px solid var(--am-line);
                    white-space: nowrap; }
                .flash-account-manager .modern-table td { padding: 10px 14px;
                    border-bottom: 1px solid var(--am-line-soft); color: var(--am-ink);
                    font-variant-numeric: tabular-nums; }
                .flash-account-manager .modern-table td strong { font-weight: 600; }
                .flash-account-manager .modern-table tbody tr { cursor: pointer;
                    border-left: 3px solid transparent; transition: background 0.12s; }
                .flash-account-manager .modern-table tbody tr:hover { background: var(--am-line-soft); }
                .flash-account-manager .modern-table tbody tr.selected { background: var(--am-accent-soft);
                    border-left-color: var(--am-accent); }
                .flash-account-manager .modern-table tbody tr:last-child td { border-bottom: none; }

                /* row age chips */
                .flash-account-manager .tr-age { display: inline-flex; border-radius: 999px;
                    padding: 2px 8px; font-size: 11px; font-weight: 650; margin-left: 8px;
                    background: var(--am-line-soft); color: var(--am-ink2); }
                .flash-account-manager .tr-age.warn { background: var(--am-warn-bg); color: var(--am-warn); }
                .flash-account-manager .tr-age.bad { background: var(--am-serious-bg); color: var(--am-serious); }

                /* chips — level ramp mirrors Account Hub; status is semantic */
                .flash-account-manager .modern-badge { display: inline-flex; align-items: center;
                    border-radius: 999px; padding: 3px 11px; font-size: 11.5px; font-weight: 650;
                    letter-spacing: 0.02em; white-space: nowrap; }
                .flash-account-manager .badge-trial { background: var(--am-line-soft); color: var(--am-ink2); }
                .flash-account-manager .badge-personal { background: var(--am-accent-soft);
                    color: var(--am-accent-ink); opacity: 0.85; }
                .flash-account-manager .badge-business { background: var(--am-accent-soft);
                    color: var(--am-accent-ink); }
                .flash-account-manager .badge-merchant { background: var(--am-accent); color: #fff; }
                .flash-account-manager .badge-pending { background: var(--am-warn-bg); color: var(--am-warn); }
                .flash-account-manager .badge-approved { background: var(--am-accent-soft);
                    color: var(--am-accent-ink); }
                .flash-account-manager .badge-rejected { background: var(--am-serious-bg);
                    color: var(--am-serious); }
                .flash-account-manager .badge-closed { background: var(--am-line-soft); color: var(--am-ink3); }

                /* empty + loading */
                .flash-account-manager .no-requests { text-align: center; padding: 40px 20px;
                    color: var(--am-ink3); }
                .flash-account-manager .no-requests-icon { font-size: 26px; margin-bottom: 8px;
                    filter: grayscale(0.4); opacity: 0.75; }
                .flash-account-manager .no-requests p:first-of-type { color: var(--am-ink); margin: 0; }
                .flash-account-manager .no-requests p { margin: 4px 0 0; }
                .flash-account-manager .loading-spinner { text-align: center; padding: 34px 0; }
                .flash-account-manager .loading-spinner p { margin: 8px 0 0; font-size: 12.5px; }
                .flash-account-manager .spinner { width: 22px; height: 22px;
                    border: 2px solid var(--am-line); border-top-color: var(--am-accent);
                    border-radius: 50%; margin: 0 auto; animation: am-spin 0.8s linear infinite; }
                @keyframes am-spin { to { transform: rotate(360deg); } }

                /* detail drawer */
                .flash-account-manager .detail-section { margin-bottom: 18px; }
                .flash-account-manager .section-header { font-size: 11px; letter-spacing: 0.06em;
                    text-transform: uppercase; color: var(--am-ink2); font-weight: 650;
                    margin: 0 0 8px; display: flex; align-items: center; }
                .flash-account-manager .detail-item { display: flex; justify-content: space-between;
                    gap: 12px; align-items: baseline; padding: 6px 0;
                    border-bottom: 1px solid var(--am-line-soft); }
                .flash-account-manager .detail-label { font-size: 11px; letter-spacing: 0.05em;
                    text-transform: uppercase; color: var(--am-ink2); font-weight: 600; flex: none; }
                .flash-account-manager .detail-value { font-size: 13px; font-weight: 600;
                    color: var(--am-ink); text-align: right; word-break: break-word; min-width: 0;
                    font-variant-numeric: tabular-nums; }
                .flash-account-manager .notes-box { background: var(--am-serious-bg);
                    color: var(--am-serious); border-radius: 10px; padding: 10px 14px;
                    font-size: 12.5px; font-weight: 600; margin: 6px 0 0; white-space: pre-wrap; }
                .flash-account-manager .request-details { position: fixed; top: 0; right: 0;
                    bottom: 0; width: min(620px, 94vw); z-index: 1040; margin: 0;
                    border-radius: 16px 0 0 16px; border-right: none;
                    box-shadow: -20px 0 50px rgba(26, 36, 32, 0.18); overflow-y: auto; }
                [data-theme="dark"] .flash-account-manager .request-details,
                .dark .flash-account-manager .request-details {
                    box-shadow: -20px 0 50px rgba(0, 0, 0, 0.5); }
                .flash-account-manager .request-details .modern-card-header { position: sticky;
                    top: 0; background: var(--am-surface); z-index: 1; }

                @media (prefers-reduced-motion: no-preference) {
                    .flash-account-manager .modern-requests-card { animation: am-rise 0.3s ease; }
                    @keyframes am-rise { from { opacity: 0; transform: translateY(5px); } }
                    .flash-account-manager .request-details { animation: am-slide 0.22s ease; }
                    @keyframes am-slide { from { opacity: 0.4; transform: translateX(40px); } }
                }
            </style>

            <div class="flash-account-manager m-3">
                <!-- Queue pulse -->
                <div class="tr-tiles pulse-tiles" style="display:none;"></div>

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
                            <option value="${AccountStatus.PENDING}">Pending</option>
                            <option value="${AccountStatus.APPROVED}">Approved</option>
                            <option value="${AccountStatus.REJECTED}">Rejected</option>
                            <option value="${AccountStatus.CLOSED}">Closed</option>
                        </select>
                        <select id="filter-level" class="modern-search-input modern-search-select">
                            <option value="">Requested Level (All)</option>
                            <option value="${AccountLevels.TRIAL}">Trial</option>
                            <option value="${AccountLevels.PERSONAL}">Personal</option>
                            <option value="${AccountLevels.PRO}">Pro</option>
                            <option value="${AccountLevels.MERCHANT}">Merchant</option>
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
                                        <span class="detail-label">Full Name</span>
                                        <span class="detail-value detail-fullname"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Phone</span>
                                        <span class="detail-value detail-phone"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">Email</span>
                                        <span class="detail-value detail-email"></span>
                                    </div>
                                    <div class="detail-item id-document-item" style="display: none;">
                                        <span class="detail-label">ID Document</span>
                                        <span class="detail-value detail-id-document"></span>
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
                                        <span class="detail-label">Address Line 1</span>
                                        <span class="detail-value detail-address-line1"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Address Line 2</span>
                                        <span class="detail-value detail-address-line2"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">City</span>
                                        <span class="detail-value detail-city"></span>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="detail-item">
                                        <span class="detail-label">State</span>
                                        <span class="detail-value detail-state"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Postal Code</span>
                                        <span class="detail-value detail-pincode"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Country</span>
                                        <span class="detail-value detail-country"></span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Terminals Requested</span>
                                        <span class="detail-value detail-terminal-requested"></span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Bank Information (optional for PRO, required for MERCHANT) -->
                        <div class="detail-section bank-info-section mb-4" style="display: none;">
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
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Status</span>
                                        <span class="detail-value detail-status"></span>
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
                            <button class="modern-btn modern-btn-danger btn-reject">
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
			title: "ID Document",
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "preview",
				},
			],
			primary_action_label: "Close",
			primary_action() {
				d.hide();
			},
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
			method: "admin_panel.api.admin_api.get_id_document_url",
			args: { file_key: fileKey },
			callback: (response) => {
				if (response.message && response.message.success) {
					const preSignedUrl = response.message.url;
					containerEl.html(`
                        <button class="btn btn-sm btn-secondary btn-view-id-doc">
                            <i class="fa fa-eye"></i> View document
                        </button>
                    `);
					containerEl.find(".btn-view-id-doc").on("click", () => {
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
			},
		});
	}

	bind_events() {
		const main = this.page.main;
		const debouncedSearch = debounce(() => {
			if (this.$cache.searchInput.val().trim()) {
				this.search();
			} else {
				this.$cache.searchError.hide();
				this.load_upgrade_requests();
			}
		}, 300);

		main.find(".btn-search").on("click", () => this.search());
		this.$cache.searchInput.on("keypress", (e) => {
			if (e.which === 13) this.search();
		});
		this.$cache.searchInput.on("input", debouncedSearch);

		main.find(".btn-refresh").on("click", () => this.load_upgrade_requests());

		$(document).on("keydown.account_management", (e) => {
			// wrapper visibility guard: desk keeps this page alive after
			// navigation, and this handler must not fire on other pages
			if (e.key === "Escape" && !window.cur_dialog && this.page.wrapper.is(":visible")) {
				this.close_details();
			}
		});
		main.find(".btn-close-details").on("click", () => this.$cache.requestDetails.hide());
		main.find(".btn-approve").on("click", () => this.approve_request(this.selected_request));
		main.find(".btn-reject").on("click", () => this.reject_request(this.selected_request));

		this.$cache.filterStatus.on("change", () => {
			this.current_page = 1;
			this.load_upgrade_requests();
		});
		this.$cache.filterLevel.on("change", () => {
			this.current_page = 1;
			this.load_upgrade_requests();
		});

		// Pagination events
		main.find(".btn-first-page").on("click", () => this.go_to_page(1));
		main.find(".btn-prev-page").on("click", () => this.go_to_page(this.current_page - 1));
		main.find(".btn-next-page").on("click", () => this.go_to_page(this.current_page + 1));
		main.find(".btn-last-page").on("click", () => this.go_to_page(this.total_pages));
	}

	create_request_row(req, showActions = true) {
		const levelBadge = getLevelBadgeClass(req.requested_level);
		const displayStatus = req.status || AccountStatus.PENDING;
		const statusBadge = getStatusBadgeClass(displayStatus);
		const isPending = req.status === AccountStatus.PENDING;

		const actionsHtml =
			showActions && isPending
				? `<td style="text-align:center;">
                <button class="modern-icon-btn modern-icon-btn-success btn-quick-approve" data-request-id="${req.name}" title="Approve"><i class="fa fa-check"></i></button>
                <button class="modern-icon-btn modern-icon-btn-danger btn-quick-reject" data-request-id="${req.name}" title="Reject"><i class="fa fa-times"></i></button>
               </td>`
				: `<td style="text-align:center;"><span>-</span></td>`;

		const row = $(`
            <tr class="request-row" data-request-id="${req.name}">
                <td><strong>${req.username || "-"}</strong></td>
                <td>${this.formatPhone(req.phone_number)}</td>
                <td><span class="modern-badge ${levelBadge}">${getAccountLevelLabel(
			req.requested_level
		)}</span></td>
                <td>${this.formatDateTime(req.creation)}${this.render_age_chip(req)}</td>
                <td><span class="modern-badge ${statusBadge}">${displayStatus}</span></td>
                ${actionsHtml}
            </tr>
        `);

		row.on("click", (e) => {
			if (!$(e.target).closest("button").length) {
				this.page.main.find(".request-row").removeClass("selected");
				row.addClass("selected");
				this.show_request_details(req);
			}
		});

		row.find(".btn-quick-approve").on("click", (e) => {
			e.stopPropagation();
			$(e.currentTarget).prop("disabled", true);
			this.approve_request(req);
		});
		row.find(".btn-quick-reject").on("click", (e) => {
			e.stopPropagation();
			$(e.currentTarget).prop("disabled", true);
			this.reject_request(req);
		});
		return row;
	}

	go_to_page(page) {
		if (page < 1 || page > this.total_pages) return;
		this.current_page = page;
		this.load_upgrade_requests();
	}

	server_now_ms() {
		// Ages are measured against the server clock the payload ships, not
		// the browser clock — operator tz must not skew warn/bad tones.
		const raw = this.pulse && this.pulse.now;
		const parsed = raw ? new Date(String(raw).replace(" ", "T")).getTime() : NaN;
		return isNaN(parsed) ? Date.now() : parsed;
	}

	formatAge(dateStr) {
		const then = new Date(String(dateStr).replace(" ", "T"));
		if (isNaN(then)) return "";
		const mins = Math.max(0, Math.floor((this.server_now_ms() - then.getTime()) / 60000));
		if (mins < 60) return `${mins}m`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h`;
		return `${Math.floor(hours / 24)}d ${hours % 24}h`;
	}

	age_tone(dateStr) {
		const then = new Date(String(dateStr).replace(" ", "T"));
		if (isNaN(then)) return "";
		const hours = (this.server_now_ms() - then.getTime()) / 3600e3;
		if (hours >= 24) return "bad";
		if (hours >= 6) return "warn";
		return "";
	}

	render_age_chip(req) {
		if (req.status !== AccountStatus.PENDING || !req.creation) return "";
		const age = this.formatAge(req.creation);
		if (!age) return "";
		return `<span class="tr-age ${this.age_tone(req.creation)}">${age}</span>`;
	}

	load_pulse() {
		frappe.call({
			method: "admin_panel.api.pulse.get_upgrade_pulse",
			callback: (res) => {
				this.pulse = res.message;
				this.render_pulse();
			},
			error: () => this.$cache.pulseTiles.hide(),
		});
	}

	render_pulse() {
		if (!this.pulse) return;
		const c = this.pulse;
		const tiles = [
			{ label: "Pending", value: c.pending ?? 0 },
			{
				label: "Oldest Waiting",
				value: c.oldest_at ? this.formatAge(c.oldest_at) : "\u2014",
				tone: c.oldest_at ? this.age_tone(c.oldest_at) : "",
				sub: c.oldest_who || "queue clear",
			},
			{ label: "Processed (7d)", value: c.processed_week ?? 0 },
		];
		this.$cache.pulseTiles.html(
			tiles
				.map(
					(t) => `
                <div class="tr-tile">
                    <div class="tr-tile-label">${t.label}</div>
                    <div class="tr-tile-value ${t.tone || ""}">${frappe.utils.escape_html(
						String(t.value)
					)}</div>
                    ${
						t.sub
							? `<div class="tr-tile-sub">${frappe.utils.escape_html(t.sub)}</div>`
							: ""
					}
                </div>`
				)
				.join("")
		);
		this.$cache.pulseTiles.show();
	}

	load_upgrade_requests() {
		this.load_pulse();
		this.$cache.requestsLoading.show();
		this.$cache.requestsTable.hide();
		this.$cache.noRequests.hide();
		this.$cache.requestDetails.hide();
		this.$cache.paginationControls.hide();

		frappe.call({
			method: "admin_panel.api.admin_api.get_upgrade_requests",
			args: {
				status: this.$cache.filterStatus.val(),
				requested_level: this.$cache.filterLevel.val(),
				page: this.current_page,
				page_size: this.page_size,
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
				frappe.show_alert(
					{ message: "Failed to load upgrade requests", indicator: "red" },
					5
				);
			},
		});
	}

	update_pagination() {
		if (this.total_count === 0) {
			this.$cache.paginationControls.hide();
			return;
		}

		this.$cache.paginationControls.css("display", "flex");

		const start = (this.current_page - 1) * this.page_size + 1;
		const end = Math.min(this.current_page * this.page_size, this.total_count);
		const main = this.page.main;

		main.find(".page-start").text(start);
		main.find(".page-end").text(end);
		main.find(".total-count").text(this.total_count);
		main.find(".current-page").text(this.current_page);
		main.find(".total-pages").text(this.total_pages);

		main.find(".btn-first-page, .btn-prev-page").prop("disabled", this.current_page <= 1);
		main.find(".btn-next-page, .btn-last-page").prop(
			"disabled",
			this.current_page >= this.total_pages
		);
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
		const panel = this.page.main.find(".request-details");

		const approveBtn = panel.find(".btn-approve");
		const rejectBtn = panel.find(".btn-reject");

		// Show buttons only for pending requests (not approved, rejected, or closed)
		if (req.status === AccountStatus.PENDING) {
			approveBtn.show();
			rejectBtn.show();
		} else {
			approveBtn.hide();
			rejectBtn.hide();
		}

		const rejectionResonContainer = panel.find(".rejection-reason");
		if (req.support_note) {
			rejectionResonContainer.show();
		} else {
			rejectionResonContainer.hide();
		}

		// Fill personal info
		panel.find(".detail-username").text(req.username || "-");
		panel.find(".detail-phone").text(this.formatPhone(req.phone_number) || "-");
		panel.find(".detail-fullname").text(req.full_name || "-");
		panel.find(".detail-email").text(req.email || "-");

		// Business info
		if (
			req.requested_level === AccountLevels.PRO ||
			req.requested_level === AccountLevels.MERCHANT
		) {
			panel.find(".business-info").show();
			panel.find(".detail-business-name").text(req.address_title || "-");
			panel.find(".detail-address-line1").text(req.address_line1 || "-");
			panel.find(".detail-address-line2").text(req.address_line2 || "-");
			panel.find(".detail-city").text(req.city || "-");
			panel.find(".detail-state").text(req.state || "-");
			panel.find(".detail-pincode").text(req.pincode || "-");
			panel.find(".detail-country").text(req.country || "-");
			panel.find(".detail-terminal-requested").text(req.terminal_requested ?? "-");
		} else {
			panel.find(".business-info").hide();
		}

		// ID Document (PRO and MERCHANT)
		const idDocItem = panel.find(".id-document-item");
		if (
			req.requested_level === AccountLevels.PRO ||
			req.requested_level === AccountLevels.MERCHANT
		) {
			const idDocEl = panel.find(".detail-id-document");
			idDocEl.empty();

			if (req.id_document) {
				idDocEl.html(`
                    <button class="btn btn-sm btn-secondary btn-view-id-doc" disabled>
                        <i class="fa fa-spinner fa-spin"></i> Loading...
                    </button>
                `);
				this.prefetch_id_document_url(req.id_document, idDocEl);
			} else {
				idDocEl.text("-");
			}
			idDocItem.show();
		} else {
			idDocItem.hide();
		}

		// Bank info (required for MERCHANT, optional for PRO)
		const hasBankInfo = req.bank_name || req.account_number || req.bank_branch;
		const showBankInfo =
			req.requested_level === AccountLevels.MERCHANT ||
			(req.requested_level === AccountLevels.PRO && hasBankInfo);

		if (showBankInfo) {
			panel.find(".detail-bank-name").text(req.bank_name || "-");
			panel.find(".detail-account-number").text(req.account_number || "-");
			panel.find(".detail-account-type").text(req.account_type || "-");
			panel.find(".detail-bank-branch").text(req.bank_branch || "-");
			panel.find(".detail-currency").text(req.currency || "-");
			panel.find(".bank-info-section").show();
		} else {
			panel.find(".bank-info-section").hide();
		}

		// Request info
		panel.find(".detail-current-level").text(getAccountLevelLabel(req.current_level) || "-");
		panel
			.find(".detail-requested-level")
			.text(getAccountLevelLabel(req.requested_level) || "-");
		panel.find(".detail-status").text(req.status || "-");
		panel.find(".detail-submitted").text(this.formatDateTime(req.creation));
		panel.find(".detail-request-id").text(req.name);
		panel.find(".detail-rejection-reason").text(req.support_note);

		panel.show();
	}

	approve_request(req) {
		if (!req) return;
		const levelLabel = getAccountLevelLabel(req.requested_level);
		frappe.confirm(
			`Are you sure you want to approve the upgrade request for ${req.username}? This will update the account level to ${levelLabel}.`,
			() =>
				frappe.call({
					method: "admin_panel.api.admin_api.approve_upgrade_request",
					args: { request_id: req.name },
					freeze: true,
					freeze_message: "Approving request and updating account level...",
					callback: (r) => {
						const result = r.message || {};
						if (result.success) {
							frappe.msgprint({
								title: "Success",
								indicator: "green",
								message:
									result.message ||
									"Request approved and account level updated.",
							});
							this.close_details();
							this.load_upgrade_requests();
						} else if (result.error || result.errors) {
							const errorMsg =
								result.error || result.errors?.join(", ") || "Unknown error";
							frappe.msgprint({
								title: "Error",
								indicator: "red",
								message: errorMsg,
							});
						}
					},
					error: (err) => {
						const msg =
							err?.responseJSON?.exception ||
							err?.responseJSON?.message ||
							"Failed to approve request";
						frappe.msgprint({ title: "Error", indicator: "red", message: msg });
					},
				})
		);
	}

	reject_request(req) {
		if (!req) return;

		const d = new frappe.ui.Dialog({
			title: "Reject Upgrade Request",
			fields: [
				{
					fieldname: "reason",
					fieldtype: "Small Text",
					label: "Reason for Rejection",
					reqd: 1,
				},
			],
			primary_action_label: "Reject",
			primary_action: (values) => {
				frappe.call({
					method: "admin_panel.api.admin_api.reject_upgrade_request",
					args: { request_id: req.name, reason: values.reason },
					freeze: true,
					freeze_message: "Rejecting request...",
					callback: (r) => {
						const result = r.message || {};
						if (result.success) {
							d.hide();
							frappe.msgprint({
								title: "Request Rejected",
								indicator: "orange",
								message: result.message || "Request rejected.",
							});
							this.close_details();
							this.load_upgrade_requests();
						} else if (result.error || result.errors) {
							const errorMsg =
								result.error || result.errors?.join(", ") || "Unknown error";
							frappe.msgprint({
								title: "Error",
								indicator: "red",
								message: errorMsg,
							});
						}
					},
					error: (err) => {
						frappe.msgprint({
							title: "Error",
							indicator: "red",
							message: err.message || "Failed to reject request",
						});
					},
				});
			},
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
			frappe.show_alert(
				{ message: "Please enter a username or phone number", indicator: "orange" },
				3
			);
			return;
		}

		this.$cache.searchLoading.show();
		this.$cache.searchError.hide();
		this.$cache.requestDetails.hide();

		frappe.call({
			method: "admin_panel.api.admin_api.search_account",
			args: { id: input },
			callback: (res) => {
				this.$cache.searchLoading.hide();
				const results = res.message;
				if (!results || results.error) {
					this.show_search_error(results?.error || "Account not found");
					return;
				}
				this.show_search_results(Array.isArray(results) ? results : []);
			},
			error: (e) => {
				this.$cache.searchLoading.hide();
				this.show_search_error(e.message || "Account not found");
			},
		});
	}

	show_search_results(results) {
		this.$cache.requestsTbody.empty();
		this.$cache.searchError.hide();
		this.$cache.paginationControls.hide();

		if (!results || !results.length) {
			this.$cache.noRequests.show();
			this.$cache.requestsTable.hide();
			this.show_search_error("No accounts found");
			return;
		}

		this.$cache.noRequests.hide();
		this.$cache.requestsTable.show();

		results.forEach((account) => {
			this.$cache.requestsTbody.append(this.create_request_row(account, true));
		});
	}

	show_search_error(msg) {
		this.$cache.searchLoading.hide();
		this.$cache.searchError.show();
		this.page.main.find(".error-message").text(msg);
	}

	formatPhone(phone) {
		if (!phone) return "-";
		return phone.replace(/^(\d{3})(\d{3})(\d{2})(\d{2})$/, "+$1 $2 $3 $4");
	}

	formatDateTime(dt) {
		return dt ? frappe.datetime.str_to_user(dt) : "-";
	}
}
