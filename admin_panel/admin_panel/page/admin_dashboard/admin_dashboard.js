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
        .ad-stat-card:hover {
            box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            transform: translateY(-1px);
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
        }
        .ad-tool-card:hover {
            box-shadow: 0 6px 20px rgba(0,0,0,0.07);
            transform: translateY(-2px);
            border-color: var(--primary-color);
        }
        .ad-tool-icon {
            width: 44px; height: 44px;
            border-radius: 10px;
            display: flex; align-items: center; justify-content: center;
            font-size: 22px;
            margin-bottom: 14px;
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

        .ad-table-wrap {
            background: var(--bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            overflow: hidden;
        }
        .ad-table {
            width: 100%;
            border-collapse: collapse;
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
        .ad-table tr:hover td { background: var(--bg-light); }

        .ad-badge {
            display: inline-block;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 8px;
            border-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.3px;
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
        }
        .ad-link-row a:hover { text-decoration: underline; }

        .ad-loading {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 300px;
        }

        @media (max-width: 900px) {
            .ad-grid-4 { grid-template-columns: repeat(2, 1fr); }
            .ad-grid-3 { grid-template-columns: 1fr; }
        }
        @media (max-width: 600px) {
            .ad-grid-4 { grid-template-columns: 1fr; }
            .ad-wrap { padding: 16px; }
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
        const recent = data.recent_requests || [];

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
                    <div class="ad-tool-title">Account Hub</div>
                    <div class="ad-tool-desc">Search accounts, view wallets, manage level &amp; status, validate merchants. Everything in one place.</div>
                </div>
                <div class="ad-tool-card" data-route="/app/account-management">
                    <div class="ad-tool-icon" style="background:#fff0e6;color:#ea580c;">👤</div>
                    <div class="ad-tool-title">Account Management</div>
                    <div class="ad-tool-desc">Review ID documents, approve or reject upgrade requests, update user details.</div>
                </div>
                <div class="ad-tool-card" data-route="/app/alert-users">
                    <div class="ad-tool-icon" style="background:#fef3c7;color:#d97706;">🔔</div>
                    <div class="ad-tool-title">Alert Users</div>
                    <div class="ad-tool-desc">Broadcast announcements via email or in-app notifications to all users or specific groups.</div>
                </div>
            </div>

            <h3 class="ad-section-title">Recent Upgrade Requests</h3>
            <div class="ad-table-wrap">
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
                    <tbody>
                        ${recent.length === 0
                            ? '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted);">No upgrade requests yet.</td></tr>'
                            : recent.map(r => `
                                <tr style="cursor:pointer;" data-name="${frappe.utils.escape_html(r.name)}" class="ad-req-row">
                                    <td><strong>${frappe.utils.escape_html(r.username || '—')}</strong></td>
                                    <td>${frappe.utils.escape_html(r.full_name || '—')}</td>
                                    <td>${levelLabel(r.requested_level)}</td>
                                    <td>${statusBadge(r.status)}</td>
                                    <td>${formatDate(r.creation)}</td>
                                </tr>
                            `).join('')}
                    </tbody>
                </table>
                ${recent.length > 0 ? `
                    <div class="ad-link-row">
                        <a href="/app/account-management">View all requests →</a>
                    </div>
                ` : ''}
            </div>
        `);

        // ── Click handlers ──

        // Tool cards
        $wrap.find('.ad-tool-card').on('click', function () {
            frappe.set_route($(this).data('route').replace('/app/', ''));
        });

        // Recent request rows → open the request form
        $wrap.find('.ad-req-row').on('click', function () {
            const name = $(this).data('name');
            if (name) {
                frappe.set_route('Form', 'Account Upgrade Request', name);
            }
        });
    }
};
