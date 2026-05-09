frappe.pages['admin-dashboard'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Dashboard',
        single_column: true,
    });

    // ── Inject custom styles ──
    $('<style>').html(`
        .ad-wrap {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px 32px;
        }
        .ad-header {
            margin-bottom: 28px;
        }
        .ad-header h1 {
            font-size: 24px;
            font-weight: 600;
            color: var(--text-color);
            margin: 0 0 4px 0;
        }
        .ad-header p {
            margin: 0;
            font-size: 14px;
            color: var(--text-muted);
        }
        .ad-grid-row {
            display: grid;
            gap: 16px;
            margin-bottom: 24px;
        }
        .ad-grid-4 { grid-template-columns: repeat(4, 1fr); }
        .ad-grid-3 { grid-template-columns: repeat(3, 1fr); }

        .ad-stat-card {
            background: var(--bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 20px 24px;
            transition: box-shadow 0.2s, transform 0.2s;
        }
        .ad-stat-card:active {
            transform: scale(0.98);
        }
        .ad-stat-icon {
            width: 36px; height: 36px;
            border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            font-size: 18px;
            margin-bottom: 14px;
        }
        .ad-stat-label {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
        .ad-stat-value {
            font-size: 28px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: var(--text-color);
            line-height: 1.1;
        }

        .ad-tool-card {
            background: var(--bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            cursor: pointer;
            transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s;
            display: flex;
            flex-direction: column;
            -webkit-tap-highlight-color: transparent;
        }
        .ad-tool-card:active {
            transform: scale(0.97);
        }
        .ad-tool-icon {
            width: 44px; height: 44px;
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px;
            margin-bottom: 14px;
            flex-shrink: 0;
        }
        .ad-tool-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-color);
            margin-bottom: 6px;
        }
        .ad-tool-desc {
            font-size: 13px;
            color: var(--text-muted);
            line-height: 1.4;
        }

        .ad-section-title {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-color);
            margin: 0 0 14px 0;
        }
        .ad-section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin: 0 0 14px 0;
        }
        .ad-section-header .ad-section-title {
            margin: 0;
        }
        .ad-search-box {
            display: flex;
            align-items: center;
            gap: 10px;
            flex: 1;
            max-width: 440px;
            margin-left: auto;
        }
        .ad-smart-search {
            width: 100%;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 9px 12px;
            font-size: 13px;
            color: var(--text-color);
            background: var(--bg);
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .ad-smart-search:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 3px rgba(0, 120, 86, 0.1);
        }
        .ad-request-count {
            white-space: nowrap;
            font-size: 12px;
            color: var(--text-muted);
        }

        .ad-table-scroll {
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .ad-table-wrap {
            background: var(--bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow: hidden;
        }
        .ad-table {
            width: 100%;
            border-collapse: collapse;
            min-width: 560px;
        }
        .ad-table th {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
            background: var(--bg-light);
        }
        .ad-table td {
            font-size: 13px;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-color);
        }
        .ad-table tr:last-child td { border-bottom: none; }
        .ad-table tbody tr:active td { background: var(--bg-light); }

        .ad-badge {
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            white-space: nowrap;
        }
        .ad-badge-pending {
            background: #fff7e6;
            color: #b8860b;
        }
        .ad-badge-approved {
            background: #e6f9ed;
            color: #1a7d36;
        }
        .ad-badge-rejected {
            background: #fde8e8;
            color: #b91c1c;
        }
        .ad-badge-default {
            background: #f0f0f0;
            color: #666;
        }

        .ad-link-row {
            text-align: right;
            padding: 12px 16px;
            background: var(--bg);
            border-top: 1px solid var(--border-color);
        }
        .ad-link-row a {
            font-size: 13px;
            color: var(--primary-color);
            text-decoration: none;
            font-weight: 500;
            padding: 6px 0;
            display: inline-block;
        }
        .ad-link-row a:hover { text-decoration: underline; }

        .ad-loading {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 300px;
        }

        /* ── RESPONSIVE ── */
        @media (max-width: 1024px) {
            .ad-grid-4 { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 768px) {
            .ad-wrap { padding: 16px 20px; }
            .ad-header h1 { font-size: 20px; }
            .ad-grid-row { gap: 12px; margin-bottom: 20px; }
            .ad-stat-card { padding: 16px 18px; }
            .ad-stat-value { font-size: 24px; }
            .ad-stat-icon { width: 32px; height: 32px; font-size: 16px; margin-bottom: 10px; }
            .ad-grid-3 { grid-template-columns: 1fr; }
            .ad-tool-card { padding: 20px; flex-direction: row; align-items: center; gap: 16px; }
            .ad-tool-icon { width: 40px; height: 40px; font-size: 20px; margin-bottom: 0; }
            .ad-tool-content { min-width: 0; }
            .ad-section-title { font-size: 15px; }
            .ad-section-header { align-items: stretch; flex-direction: column; gap: 10px; }
            .ad-search-box { max-width: none; margin-left: 0; }
        }
        @media (max-width: 480px) {
            .ad-wrap { padding: 12px 14px; }
            .ad-header { margin-bottom: 20px; }
            .ad-header h1 { font-size: 18px; }
            .ad-header p { font-size: 13px; }
            .ad-grid-4 { grid-template-columns: repeat(2, 1fr); }
            .ad-grid-row { gap: 8px; margin-bottom: 16px; }
            .ad-stat-card { padding: 12px 14px; }
            .ad-stat-icon { width: 28px; height: 28px; font-size: 14px; margin-bottom: 8px; }
            .ad-stat-label { font-size: 11px; }
            .ad-stat-value { font-size: 20px; }
            .ad-tool-card { padding: 14px 16px; gap: 12px; }
            .ad-tool-icon { width: 36px; height: 36px; font-size: 18px; }
            .ad-tool-title { font-size: 14px; }
            .ad-tool-desc { font-size: 12px; }
            .ad-table td, .ad-table th { padding: 10px 12px; font-size: 12px; }
            .ad-link-row { padding: 10px 12px; }
            .ad-link-row a { font-size: 12px; }
        }
    `).appendTo(page.main);
    // ── ── ── ──

    const $wrap = $('<div class="ad-wrap">').appendTo(page.main);

    // ── Loading state ──
    $wrap.html(`
        <div class="ad-loading">
            <div class="frappe-list-loading" style="text-align:center;">
                <div class="frappe-list-loading-spin"></div>
                <p style="margin-top:12px;color:var(--text-muted);font-size:13px;">Loading dashboard...</p>
            </div>
        </div>
    `);

    // ── Fetch stats & render ──
    frappe.call({
        method: 'admin_panel.api.admin_api.get_dashboard_stats',
        callback: (res) => {
            const data = res.message;
            if (!data) {
                $wrap.html('<p style="text-align:center;padding:40px;color:var(--text-muted);">Could not load dashboard data.</p>');
                return;
            }
            render(data);
        },
        error: () => {
            $wrap.html('<p style="text-align:center;padding:40px;color:var(--text-muted);">Network error loading dashboard.</p>');
        }
    });

    function render(data) {
        const rq = data.upgrade_requests || {};
        const requests = data.all_requests || data.recent_requests || [];

        const levelLabel = (lvl) => {
            const labels = { ZERO: 'Zero', ONE: 'One', TWO: 'Two', THREE: 'Three' };
            return labels[lvl] || lvl || '—';
        };

        const statusBadge = (s) => {
            const cls = {
                'Pending': 'ad-badge-pending',
                'Approved': 'ad-badge-approved',
                'Rejected': 'ad-badge-rejected'
            };
            return `<span class="ad-badge ${cls[s] || 'ad-badge-default'}">${s || '—'}</span>`;
        };

        const formatDate = (ts) => {
            if (!ts) return '—';
            const d = new Date(ts);
            if (isNaN(d.getTime())) return ts;
            const now = new Date();
            const diff = (now - d) / 1000;
            if (diff < 60) return 'just now';
            if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
            if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        };


        const normalizeSearch = (value) => String(value || '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '');

        const fuzzyIncludes = (value, rawNeedle) => {
            const haystack = String(value || '').toLowerCase();
            const needle = String(rawNeedle || '').toLowerCase();
            if (!needle) return true;
            if (haystack.includes(needle)) return true;

            const normalizedHaystack = normalizeSearch(haystack);
            const normalizedNeedle = normalizeSearch(needle);
            if (!normalizedNeedle) return true;
            if (normalizedHaystack.includes(normalizedNeedle)) return true;

            // Lightweight fuzzy fallback: ordered-character subsequence match.
            let j = 0;
            for (const ch of normalizedHaystack) {
                if (ch === normalizedNeedle[j]) j += 1;
                if (j === normalizedNeedle.length) return true;
            }
            return false;
        };

        const requestMatchesQuery = (request, query) => {
            const tokens = String(query || '').trim().split(/\s+/).filter(Boolean);
            if (!tokens.length) return true;

            const fields = [
                request.username,
                request.full_name,
                request.phone_number,
                request.email,
                request.name,
                request.status,
                request.requested_level,
                request.current_level,
                levelLabel(request.requested_level),
                levelLabel(request.current_level),
            ];

            return tokens.every(token => fields.some(field => fuzzyIncludes(field, token)));
        };

        const renderRequestRows = (items) => {
            if (!items.length) {
                return '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted);">No upgrade requests match that search.</td></tr>';
            }

            return items.map(r => `
                <tr style="cursor:pointer;" data-username="${frappe.utils.escape_html(r.username || '')}" data-query="${frappe.utils.escape_html(r.username || r.phone_number || r.email || r.name || '')}" class="ad-req-row">
                    <td><strong>${frappe.utils.escape_html(r.username || '—')}</strong></td>
                    <td>${frappe.utils.escape_html(r.full_name || '—')}</td>
                    <td>${levelLabel(r.requested_level)}</td>
                    <td>${statusBadge(r.status)}</td>
                    <td>${formatDate(r.creation)}</td>
                </tr>
            `).join('');
        };

        $wrap.html(`
            <div class="ad-header">
                <h1>🔥 Admin Dashboard</h1>
                <p>Welcome, support team. Here's what's happening.</p>
            </div>

            <div class="ad-grid-row ad-grid-4">
                <div class="ad-stat-card">
                    <div class="ad-stat-icon" style="background:#fff7e6;color:#b8860b;">⏳</div>
                    <div class="ad-stat-label">Pending Requests</div>
                    <div class="ad-stat-value">${rq.pending || 0}</div>
                </div>
                <div class="ad-stat-card">
                    <div class="ad-stat-icon" style="background:#e6f9ed;color:#1a7d36;">✅</div>
                    <div class="ad-stat-label">Approved Today</div>
                    <div class="ad-stat-value">${rq.approved_today || 0}</div>
                </div>
                <div class="ad-stat-card">
                    <div class="ad-stat-icon" style="background:#e8eaff;color:#4f46e5;">📊</div>
                    <div class="ad-stat-label">Total Approved</div>
                    <div class="ad-stat-value">${rq.approved || 0}</div>
                </div>
                <div class="ad-stat-card">
                    <div class="ad-stat-icon" style="background:#f3e8ff;color:#7c3aed;">📋</div>
                    <div class="ad-stat-label">Total Requests</div>
                    <div class="ad-stat-value">${data.total_requests || 0}</div>
                </div>
            </div>

            <h3 class="ad-section-title">Quick Actions</h3>
            <div class="ad-grid-row ad-grid-3">
                <div class="ad-tool-card" data-route="/app/account-hub">
                    <div class="ad-tool-icon" style="background:#e6f0ff;color:#2563eb;">🔍</div>
                    <div class="ad-tool-content">
                        <div class="ad-tool-title">Account Hub</div>
                        <div class="ad-tool-desc">Search accounts, view wallets, manage level &amp; status, validate merchants. Everything in one place.</div>
                    </div>
                </div>
                <div class="ad-tool-card" data-route="/app/account-management">
                    <div class="ad-tool-icon" style="background:#fff0e6;color:#ea580c;">👤</div>
                    <div class="ad-tool-content">
                        <div class="ad-tool-title">Account Management</div>
                        <div class="ad-tool-desc">Review ID documents, approve or reject upgrade requests, update user details.</div>
                    </div>
                </div>
                <div class="ad-tool-card" data-route="/app/alert-users">
                    <div class="ad-tool-icon" style="background:#fef3c7;color:#d97706;">🔔</div>
                    <div class="ad-tool-content">
                        <div class="ad-tool-title">Alert Users</div>
                        <div class="ad-tool-desc">Broadcast announcements via email or in-app notifications to all users or specific groups.</div>
                    </div>
                </div>
            </div>

            <div class="ad-section-header">
                <h3 class="ad-section-title">Upgrade Requests</h3>
                <div class="ad-search-box">
                    <input type="search" class="ad-smart-search" placeholder="Search username, name, phone, email, level, status..." autocomplete="off">
                    <span class="ad-request-count"></span>
                </div>
            </div>
            <div class="ad-table-wrap">
                <div class="ad-table-scroll">
                <table class="ad-table">
                    <thead>
                        <tr>
                            <th>Username</th>
                            <th>Name</th>
                            <th>Level</th>
                            <th>Status</th>
                            <th>Submitted</th>
                        </tr>
                    </thead>
                    <tbody class="ad-requests-body">
                        ${requests.length === 0
                            ? '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted);">No upgrade requests yet.</td></tr>'
                            : renderRequestRows(requests)}
                    </tbody>
                </table>
                </div>
            </div>
        `);

        // ── Click handlers ──

        // Tool cards
        $wrap.find('.ad-tool-card').on('click', function () {
            frappe.set_route($(this).data('route').replace('/app/', ''));
        });

        const updateRequestList = () => {
            const query = $wrap.find('.ad-smart-search').val() || '';
            const filtered = requests.filter(r => requestMatchesQuery(r, query));
            $wrap.find('.ad-requests-body').html(renderRequestRows(filtered));
            $wrap.find('.ad-request-count').text(`${filtered.length} of ${requests.length}`);
        };

        $wrap.on('input', '.ad-smart-search', updateRequestList);

        // Upgrade request rows → open Account Hub with the username selected
        $wrap.on('click', '.ad-req-row', function () {
            const query = $(this).data('username') || $(this).data('query');
            if (query) {
                frappe.route_options = { account_hub_query: query };
                frappe.set_route('account-hub');
            }
        });

        updateRequestList();
    }
};
