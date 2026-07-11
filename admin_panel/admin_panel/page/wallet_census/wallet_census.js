const WC_ALLOWED_ROLES = ["Accounts Manager", "Flash Admin", "System Manager"];

frappe.pages["wallet-census"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Wallet Census",
		single_column: true,
	});

	const allowed =
		frappe.session.user === "Administrator" ||
		WC_ALLOWED_ROLES.some((r) => frappe.user_roles.includes(r));
	if (!allowed) {
		page.main.html(`
            <div class="text-center mt-5">
                <div class="alert alert-warning">
                    <h4>Access Denied</h4>
                    <p>You do not have permission to access this page. Please contact your administrator to get one of the "Accounts Manager", "Flash Admin", or "System Manager" roles.</p>
                </div>
            </div>
        `);
		return;
	}

	wrapper.wallet_census = new WalletCensus(page);
};

frappe.pages["wallet-census"].on_page_show = function (wrapper) {
	if (wrapper.wallet_census) {
		wrapper.wallet_census.refresh_status();
	}
};

function wc_debounce(func, wait) {
	let timeout;
	return function (...args) {
		clearTimeout(timeout);
		timeout = setTimeout(() => func.apply(this, args), wait);
	};
}

const WC_CSS = `
    .wallet-census { --wc-surface: var(--card-bg, #ffffff); --wc-ink: var(--text-color, #1a2420);
          --wc-ink2: var(--text-muted, #5c6b65); --wc-ink3: var(--text-light, #8fa098);
          --wc-line: var(--border-color, #e2e8e5); --wc-line-soft: var(--subtle-fg, #ecf1ee);
          --wc-accent: #007856; --wc-accent-ink: #007856; --wc-accent-soft: #e6f3ee;
          --wc-good: #0ca30c; --wc-warn: #b87d00; --wc-warn-bg: #fff3d6;
          --wc-serious: #c05a32; --wc-serious-bg: #fdeae2;
          --wc-shadow: 0 1px 2px rgba(26,36,32,0.05), 0 4px 14px rgba(26,36,32,0.04);
          max-width: 1240px; margin: 0 auto; }
    [data-theme="dark"] .wallet-census, .dark .wallet-census {
          --wc-accent: #1e9e75; --wc-accent-ink: #4cc29e; --wc-accent-soft: #12352a;
          --wc-good: #35c135; --wc-warn: #fab219; --wc-warn-bg: #33290d;
          --wc-serious: #ec835a; --wc-serious-bg: #38211a;
          --wc-shadow: 0 1px 2px rgba(0,0,0,0.35), 0 6px 18px rgba(0,0,0,0.25); }
    .wallet-census .wc-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
    .wallet-census .wc-input { border: 1px solid var(--wc-line); border-radius: 9px; padding: 7px 12px;
          font-size: 13px; background: var(--wc-surface); color: var(--wc-ink); }
    .wallet-census .wc-input:focus { outline: 2px solid var(--wc-accent); outline-offset: 1px; border-color: var(--wc-accent); }
    .wallet-census .wc-btn { border: 1px solid var(--wc-line); background: var(--wc-surface); color: var(--wc-ink);
          border-radius: 9px; padding: 7px 14px; font-size: 13px; font-weight: 600; cursor: pointer;
          transition: border-color 0.15s; }
    .wallet-census .wc-btn:hover { border-color: var(--wc-accent); }
    .wallet-census .wc-btn:focus-visible { outline: 2px solid var(--wc-accent); outline-offset: 1px; }
    .wallet-census .wc-btn.primary { background: var(--wc-accent); border-color: var(--wc-accent); color: #fff; }
    .wallet-census .wc-btn.primary:hover { filter: brightness(1.07); }
    .wallet-census .wc-meta { color: var(--wc-ink2); font-size: 12.5px; margin: 0 0 14px; }
    .wallet-census .wc-meta .err { color: var(--wc-serious); font-weight: 600; }
    .wallet-census .wc-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 14px; margin-bottom: 16px; }
    .wallet-census .wc-tile { background: var(--wc-surface); border: 1px solid var(--wc-line);
          border-radius: 14px; padding: 15px 17px 12px; box-shadow: var(--wc-shadow);
          display: flex; flex-direction: column; gap: 5px; min-height: 104px; }
    .wallet-census .wc-tile-label { font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
          color: var(--wc-ink2); font-weight: 600; }
    .wallet-census .wc-tile-value { font-size: 27px; font-weight: 650; letter-spacing: -0.015em;
          line-height: 1.1; color: var(--wc-ink); }
    .wallet-census .wc-tile-sub { color: var(--wc-ink3); font-size: 12px; margin-top: auto; }
    .wallet-census .wc-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
    .wallet-census .wc-bucket { border: 1px solid var(--wc-line); background: var(--wc-surface);
          color: var(--wc-ink2); border-radius: 999px; padding: 5px 13px; font-size: 12.5px;
          font-weight: 600; cursor: pointer; transition: all 0.12s; }
    .wallet-census .wc-bucket:hover { border-color: var(--wc-accent); color: var(--wc-ink); }
    .wallet-census .wc-bucket.active { background: var(--wc-accent); border-color: var(--wc-accent); color: #fff; }
    .wallet-census .wc-bucket .badge { font-weight: 650; margin-left: 5px; opacity: 0.75; }
    .wallet-census .wc-card { background: var(--wc-surface); border: 1px solid var(--wc-line);
          border-radius: 14px; box-shadow: var(--wc-shadow); overflow: hidden; }
    .wallet-census .wc-count { color: var(--wc-ink3); font-size: 12px; padding: 12px 18px 0; }
    .wallet-census table.wc-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0 0; }
    .wallet-census table.wc-table th { text-align: left; font-size: 11px; letter-spacing: 0.05em;
          text-transform: uppercase; color: var(--wc-ink2); font-weight: 650; padding: 10px 18px;
          border-bottom: 1px solid var(--wc-line); white-space: nowrap; cursor: pointer; }
    .wallet-census table.wc-table td { padding: 9px 18px; border-bottom: 1px solid var(--wc-line-soft);
          color: var(--wc-ink); font-variant-numeric: tabular-nums; }
    .wallet-census table.wc-table tr:last-child td { border-bottom: none; }
    .wallet-census .wc-row:hover { background: var(--wc-line-soft); }
    .wallet-census table.wc-table code { background: transparent; color: var(--wc-ink3); font-size: 12px; }
    .wallet-census .wc-morebar { padding: 12px 18px 14px; display: flex; gap: 10px; }
    .wallet-census #wc-detail h4 { font-size: 18px; font-weight: 650; margin: 6px 0 14px; color: var(--wc-ink); }
    .wallet-census #wc-detail h5 { font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase;
          color: var(--wc-ink2); font-weight: 650; margin: 20px 0 8px; }
    .wallet-census #wc-detail table { width: 100%; border-collapse: collapse; font-size: 13px;
          background: var(--wc-surface); border: 1px solid var(--wc-line); border-radius: 12px; overflow: hidden; }
    .wallet-census #wc-detail table th { text-align: left; font-size: 11px; letter-spacing: 0.05em;
          text-transform: uppercase; color: var(--wc-ink2); font-weight: 650; padding: 9px 14px;
          border-bottom: 1px solid var(--wc-line); background: var(--wc-line-soft); }
    .wallet-census #wc-detail table td { padding: 8px 14px; border-bottom: 1px solid var(--wc-line-soft);
          font-variant-numeric: tabular-nums; }
    .wallet-census #wc-detail table tr:last-child td { border-bottom: none; }
    .wallet-census .alert { border-radius: 12px; border: 1px solid var(--wc-line); padding: 12px 16px; font-size: 13px; }
    .wallet-census .alert-warning { background: var(--wc-warn-bg); color: var(--wc-warn); border-color: transparent; }
    .wallet-census .alert-danger { background: var(--wc-serious-bg); color: var(--wc-serious); border-color: transparent; }
    .wallet-census .wc-detail-head { display: flex; justify-content: space-between; align-items: center;
          gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
    .wallet-census .wc-kv-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
          gap: 10px; margin: 0 0 18px; }
    .wallet-census .wc-kv { background: var(--wc-surface); border: 1px solid var(--wc-line);
          border-radius: 12px; padding: 10px 14px; }
    .wallet-census .wc-kv .k { font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase;
          color: var(--wc-ink2); font-weight: 600; margin-bottom: 2px; }
    .wallet-census .wc-kv .v { font-size: 13.5px; font-weight: 600; color: var(--wc-ink); word-break: break-all; }
    .wallet-census .wc-kv .v.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
          font-size: 12px; font-weight: 500; color: var(--wc-ink2); }
    .wallet-census .wc-chip-st { display: inline-flex; align-items: center; border-radius: 999px;
          padding: 3px 11px; font-size: 12px; font-weight: 600;
          background: var(--wc-line-soft); color: var(--wc-ink2); }
    .wallet-census .wc-chip-st.ok { background: var(--wc-accent-soft); color: var(--wc-accent-ink); }
    .wallet-census .wc-chip-st.warn { background: var(--wc-warn-bg); color: var(--wc-warn); }
    .wallet-census .wc-chip-st.bad { background: var(--wc-serious-bg); color: var(--wc-serious); }
    .wallet-census .wc-amt.in { color: var(--wc-good); font-weight: 650; }
    .wallet-census .wc-amt.out { color: var(--wc-ink); font-weight: 600; }
    .wallet-census .wc-fee { color: var(--wc-ink3); font-size: 11.5px; margin-left: 6px; }
    .wallet-census .wc-defchip { background: var(--wc-accent-soft); color: var(--wc-accent-ink);
          border-radius: 999px; padding: 2px 9px; font-size: 11px; font-weight: 650; }
    @media (prefers-reduced-motion: no-preference) {
        .wallet-census .wc-rise { opacity: 0; transform: translateY(6px); animation: wc-rise 0.35s ease forwards; }
        @keyframes wc-rise { to { opacity: 1; transform: none; } }
    }
`;

const WC_PAGE_SIZE = 200;
const WC_PAGE_STEP = 500;

const BUCKETS = [
	{ key: "all", label: "All" },
	{ key: "active_funded", label: "Active + Funded" },
	{ key: "active_zero", label: "Active + Zero" },
	{ key: "closed_with_dust", label: "Closed w/ Dust" },
	{ key: "unmatched", label: "Unmatched" },
	{ key: "migrated", label: "Migrated" },
	{ key: "system", label: "System" },
	{ key: "non_default_wallet", label: "Non-default Wallet" },
];

// IBEX transactionTypeId semantics, mapped empirically (2026-07-11) by
// reconciling full account ledgers against reported balances:
// 1 & 3 credit the account, 2 & 4 debit it (4 = withdrawal, carries a fee).
const WC_TX_TYPES = {
	1: { label: "Credit", dir: "in" },
	2: { label: "Send", dir: "out" },
	3: { label: "Credit", dir: "in" },
	4: { label: "Withdrawal", dir: "out" },
};

class WalletCensus {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.totals = {};
		this.bucket_counts = {};
		this.active_bucket = "all";
		this.render_limit = WC_PAGE_SIZE;
		this.sort_key = "balance";
		this.sort_dir = "desc";
		this.poll_timer = null;

		this.run_btn = this.page.set_primary_action(
			"Run Census",
			() => this.run_census(),
			"refresh"
		);
		this.render_shell();
		this.load_latest();
		this.refresh_status();
	}

	render_shell() {
		this.page.main.html(`
            <style>${WC_CSS}</style>
            <div class="wallet-census">
                <div class="wc-toolbar">
                    <input type="text" id="wc-lookup" class="wc-input" style="min-width:320px;flex:1;max-width:420px"
                        placeholder="Look up a customer: username / phone / accountId…">
                    <button class="wc-btn primary" id="wc-lookup-btn">Look up</button>
                </div>
                <div id="wc-detail" style="display:none"></div>
                <div id="wc-census">
                    <div id="wc-status" class="wc-meta"></div>
                    <div id="wc-summary" class="wc-tiles"></div>
                    <div id="wc-buckets" class="wc-chips"></div>
                    <div class="wc-toolbar">
                        <input type="text" id="wc-search" class="wc-input" style="min-width:280px"
                            placeholder="Filter loaded rows by username / accountId…">
                        <button class="wc-btn" id="wc-export">Export CSV</button>
                    </div>
                    <div id="wc-table"></div>
                </div>
            </div>
        `);

		const search = this.page.main.find("#wc-search");
		search.on(
			"input",
			wc_debounce(() => {
				this.render_limit = WC_PAGE_SIZE;
				this.render_table();
			}, 200)
		);
		this.page.main.find("#wc-export").on("click", () => this.export_csv());

		const lookup = this.page.main.find("#wc-lookup");
		const doLookup = () => {
			const q = (lookup.val() || "").trim();
			if (q) this.open_detail(q);
		};
		this.page.main.find("#wc-lookup-btn").on("click", doLookup);
		lookup.on("keydown", (e) => {
			if (e.key === "Enter") doLookup();
		});
	}

	set_status(text) {
		this.page.main.find("#wc-status").html(text);
	}

	// ── Run + poll ────────────────────────────────────────────────
	run_census() {
		this.set_status("Starting census…");
		frappe.call({
			method: "admin_panel.api.census.start_census",
			callback: () => {
				this.set_status("Census running…");
				this.poll();
			},
		});
	}

	refresh_status() {
		frappe.call({
			method: "admin_panel.api.census.get_census_status",
			callback: (res) => {
				const s = res.message || {};
				if (s.status === "Running") this.poll();
				else this.render_status(s);
			},
		});
	}

	poll() {
		if (this.poll_timer) clearTimeout(this.poll_timer);
		frappe.call({
			method: "admin_panel.api.census.get_census_status",
			callback: (res) => {
				const s = res.message || {};
				this.render_status(s);
				if (s.status === "Running") {
					this.poll_timer = setTimeout(() => this.poll(), 4000);
				} else if (s.status === "Complete") {
					this.load_latest();
				}
			},
		});
	}

	render_status(s) {
		if (!s || s.status === "None") {
			this.set_status("No census has been run yet.");
			return;
		}
		if (s.status === "Running") {
			this.set_status(
				`⏳ Running — ${s.scanned_accounts || 0} accounts scanned (${
					s.scanned_pages || 0
				} pages)…`
			);
		} else if (s.status === "Failed") {
			this.set_status(
				`<span class="err">Last run failed: ${frappe.utils.escape_html(
					s.error || ""
				)}</span>`
			);
		} else if (s.status === "Complete") {
			this.set_status(`Last run completed ${s.completed_at || ""} (${s.snapshot}).`);
		}
	}

	// ── Load + render ─────────────────────────────────────────────
	load_latest() {
		frappe.call({
			method: "admin_panel.api.census.get_latest_census",
			callback: (res) => {
				const d = res.message || {};
				if (!d.snapshot) return;
				this.rows = d.rows || [];
				this.totals = d.totals || {};
				this.bucket_counts = d.bucket_counts || {};
				this.render_summary();
				this.render_buckets();
				this.render_table();
			},
		});
	}

	fmt_money(v, ccy) {
		if (v === null || v === undefined) return "—";
		return `${Number(v).toLocaleString(undefined, {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		})} ${ccy}`;
	}

	render_summary() {
		const t = this.totals;
		const usd = t.usd || {},
			usdt = t.usdt || {},
			btc = t.btc || {};
		const card = (title, value, sub) => `
            <div class="wc-tile wc-rise">
                <div class="wc-tile-label">${title}</div>
                <div class="wc-tile-value">${value}</div>
                <div class="wc-tile-sub">${sub || ""}</div>
            </div>`;
		this.page.main
			.find("#wc-summary")
			.html(
				card(
					"USD Float",
					this.fmt_money(usd.balance, "USD"),
					`${usd.funded_count || 0} funded / ${usd.zero_count || 0} zero`
				) +
					card(
						"USDT Float",
						this.fmt_money(usdt.balance, "USDT"),
						`${usdt.funded_count || 0} funded / ${usdt.zero_count || 0} zero`
					) +
					card(
						"Accounts",
						`${t.accounts || 0}`,
						`${t.funded || 0} funded / ${t.zero || 0} zero`
					) +
					card("BTC Wallets", `${btc.wallet_count || 0}`, "balance not held in IBEX")
			);
	}

	render_buckets() {
		const html = BUCKETS.map((b) => {
			const count =
				b.key === "all" ? this.totals.accounts || 0 : this.bucket_counts[b.key] || 0;
			const active = b.key === this.active_bucket ? " active" : "";
			return `<button class="wc-bucket${active}" data-bucket="${b.key}">${b.label} <span class="badge">${count}</span></button>`;
		}).join("");
		const el = this.page.main.find("#wc-buckets");
		el.html(html);
		el.find(".wc-bucket").on("click", (e) => {
			this.active_bucket = e.currentTarget.dataset.bucket;
			this.render_limit = WC_PAGE_SIZE;
			this.render_buckets();
			this.render_table();
		});
	}

	filtered_rows() {
		const q = (this.page.main.find("#wc-search").val() || "").toLowerCase().trim();
		let rows = this.rows;
		if (this.active_bucket !== "all") {
			rows = rows.filter((r) => (r.buckets || []).includes(this.active_bucket));
		}
		if (q) {
			rows = rows.filter(
				(r) =>
					(r.username || "").toLowerCase().includes(q) ||
					(r.account_id || "").toLowerCase().includes(q)
			);
		}
		const dir = this.sort_dir === "desc" ? -1 : 1;
		const key = this.sort_key;
		rows = rows.slice().sort((a, b) => {
			const av = a[key],
				bv = b[key];
			if (av === bv) return 0;
			if (av === null || av === undefined) return 1;
			if (bv === null || bv === undefined) return -1;
			return av > bv ? dir : -dir;
		});
		return rows;
	}

	render_table() {
		const rows = this.filtered_rows();
		const visible = rows.slice(0, this.render_limit);
		const cols = [
			{ key: "username", label: "Username" },
			{ key: "balance", label: "Balance" },
			{ key: "currency", label: "Currency" },
			{ key: "status", label: "Status" },
			{ key: "migration_status", label: "Migration" },
			{ key: "account_id", label: "Account ID" },
		];
		const head = cols
			.map((c) => {
				const arrow =
					this.sort_key === c.key ? (this.sort_dir === "desc" ? " ▼" : " ▲") : "";
				return `<th class="wc-sort" data-key="${c.key}" style="cursor:pointer">${c.label}${arrow}</th>`;
			})
			.join("");
		const body = visible
			.map(
				(r) => `
            <tr class="wc-row" data-q="${frappe.utils.escape_html(
				r.account_id || r.username || ""
			)}" style="cursor:pointer">
                <td>${frappe.utils.escape_html(r.username || "—")}</td>
                <td style="text-align:right">${
					r.balance
						? Number(r.balance).toLocaleString(undefined, {
								minimumFractionDigits: 2,
								maximumFractionDigits: 2,
						  })
						: "0.00"
				}</td>
                <td>${frappe.utils.escape_html(r.currency || "—")}</td>
                <td>${frappe.utils.escape_html(r.status || "—")}</td>
                <td>${frappe.utils.escape_html(r.migration_status || "—")}</td>
                <td><code>${frappe.utils.escape_html(r.account_id || "")}</code></td>
            </tr>`
			)
			.join("");
		const moreBtns =
			rows.length > visible.length
				? `<div class="wc-morebar">
                    <button class="wc-btn" id="wc-more">Show ${WC_PAGE_STEP} more</button>
                    <button class="wc-btn" id="wc-all">Show all</button>
                </div>`
				: "";
		this.page.main.find("#wc-table").html(`
            <div class="wc-card wc-rise">
                <div class="wc-count">Showing ${visible.length} of ${rows.length} accounts</div>
                <div style="overflow-x:auto">
                    <table class="wc-table">
                        <thead><tr>${head}</tr></thead>
                        <tbody>${
							body ||
							'<tr><td colspan="6" style="text-align:center;color:var(--wc-ink3)">No accounts</td></tr>'
						}</tbody>
                    </table>
                </div>${moreBtns}
            </div>`);
		this.page.main.find(".wc-sort").on("click", (e) => {
			const key = e.currentTarget.dataset.key;
			if (this.sort_key === key) this.sort_dir = this.sort_dir === "desc" ? "asc" : "desc";
			else {
				this.sort_key = key;
				this.sort_dir = "desc";
			}
			this.render_table();
		});
		this.page.main.find(".wc-row").on("click", (e) => {
			const q = e.currentTarget.dataset.q;
			if (q) this.open_detail(q);
		});
		this.page.main.find("#wc-more").on("click", () => {
			this.render_limit += WC_PAGE_STEP;
			this.render_table();
		});
		this.page.main.find("#wc-all").on("click", () => {
			this.render_limit = rows.length;
			this.render_table();
		});
	}

	// ── Per-customer detail ───────────────────────────────────────
	open_detail(query) {
		const detail = this.page.main.find("#wc-detail");
		this.page.main.find("#wc-census").hide();
		detail.show().html('<div class="text-muted">Loading customer…</div>');
		frappe.call({
			method: "admin_panel.api.customer.get_customer_detail",
			args: { query: query },
			callback: (res) => this.render_detail(res.message || {}, query),
			error: () => {
				const backBtn = `<button class="wc-btn" id="wc-back">← Back to census</button>`;
				detail.html(
					`<div class="mb-2">${backBtn}</div>
                     <div class="alert alert-danger">Failed to load customer — the server returned an error. Check logs or try again.</div>`
				);
				this.page.main.find("#wc-back").on("click", () => this.close_detail());
			},
		});
	}

	close_detail() {
		this.page.main.find("#wc-detail").hide().empty();
		this.page.main.find("#wc-census").show();
	}

	render_detail(d, query) {
		const detail = this.page.main.find("#wc-detail");
		const backBtn = `<button class="wc-btn" id="wc-back">← Back to census</button>`;
		if (!d.found) {
			// The census row may still carry IBEX-side facts even when the DB has no match.
			const row = (this.rows || []).find(
				(r) => r.account_id === query || r.username === query
			);
			const censusFacts = row
				? `<h5>IBEX-side facts from the last census</h5>
                 <table class="table table-bordered table-sm" style="max-width:560px">
                    <tbody>
                        <tr><td class="text-muted">Wallet ID</td><td><code>${frappe.utils.escape_html(
							row.wallet_id || ""
						)}</code></td></tr>
                        <tr><td class="text-muted">Currency</td><td>${frappe.utils.escape_html(
							row.currency || "—"
						)}</td></tr>
                        <tr><td class="text-muted">Balance</td><td style="text-align:right">${
							row.balance
								? Number(row.balance).toLocaleString(undefined, {
										minimumFractionDigits: 2,
										maximumFractionDigits: 2,
								  })
								: "0.00"
						}</td></tr>
                        <tr><td class="text-muted">Status</td><td>${frappe.utils.escape_html(
							row.status || "—"
						)}</td></tr>
                        <tr><td class="text-muted">Buckets</td><td>${frappe.utils.escape_html(
							(row.buckets || []).join(", ")
						)}</td></tr>
                    </tbody>
                 </table>`
				: "";
			detail.html(
				`<div class="mb-2">${backBtn}</div>
                 <div class="alert alert-warning">No customer found for “${frappe.utils.escape_html(
						query
					)}”. ${frappe.utils.escape_html(d.error || "")}</div>${censusFacts}`
			);
			this.page.main.find("#wc-back").on("click", () => this.close_detail());
			return;
		}

		const i = d.identity;
		const esc = (v) => frappe.utils.escape_html(String(v == null || v === "" ? "—" : v));
		const kv = (label, val, mono) =>
			`<div class="wc-kv"><div class="k">${label}</div><div class="v${
				mono ? " mono" : ""
			}">${esc(val)}</div></div>`;
		const statusChip = (st) => {
			const cls =
				{ active: "ok", closed: "bad", locked: "warn" }[(st || "").toLowerCase()] || "";
			return `<span class="wc-chip-st ${cls}">${esc(st || "unknown")}</span>`;
		};

		const walletRows = (d.wallets || [])
			.map(
				(w) => `<tr>
                <td>${esc(w.currency)}</td>
                <td>${esc(w.type)}</td>
                <td style="text-align:right"><span class="wc-amt out">${Number(
					w.live_balance || 0
				).toLocaleString(undefined, {
					minimumFractionDigits: 2,
					maximumFractionDigits: 8,
				})}</span>${
					w.balance_not_found ? '<span class="wc-fee">(drained)</span>' : ""
				}</td>
                <td>${w.is_default ? '<span class="wc-defchip">default</span>' : ""}</td>
                <td><code>${frappe.utils.escape_html(w.wallet_id || "")}</code></td>
            </tr>`
			)
			.join("");

		const migRows = (d.migrations || []).length
			? d.migrations
					.map(
						(m) => `<tr>
                <td>${
					m.status && m.status.toLowerCase().startsWith("complet")
						? `<span class="wc-chip-st ok">${esc(m.status)}</span>`
						: statusChip(m.status)
				}</td>
                <td>${esc(m.run_id)}</td>
                <td>${esc(m.completed_at || m.started_at)}</td>
                <td>${frappe.utils.escape_html(m.last_error || "")}</td>
            </tr>`
					)
					.join("")
			: '<tr><td colspan="4" style="color:var(--wc-ink3)">No migration records</td></tr>';

		const txRows = (d.transactions || []).length
			? d.transactions
					.map((t) => {
						const ty = WC_TX_TYPES[t.type_id] || null;
						const amt =
							t.amount != null && Number.isFinite(Number(t.amount))
								? Number(t.amount).toLocaleString(undefined, {
										maximumFractionDigits: 8,
								  })
								: "—";
						const sign = ty ? (ty.dir === "in" ? "+" : "−") : "";
						const fee =
							t.network_fee && Number(t.network_fee) > 0
								? `<span class="wc-fee">fee ${Number(t.network_fee).toLocaleString(
										undefined,
										{ maximumFractionDigits: 8 }
								  )}</span>`
								: "";
						return `<tr>
                <td>${esc((t.created_at || "").replace("T", " ").slice(0, 19))}</td>
                <td style="text-align:right"><span class="wc-amt ${
					ty ? ty.dir : "out"
				}">${sign}${amt}</span>${fee}</td>
                <td>${esc(t.currency)}</td>
                <td>${ty ? esc(ty.label) : esc(t.type_id)}</td>
            </tr>`;
					})
					.join("")
			: '<tr><td colspan="4" style="color:var(--wc-ink3)">No recent transactions</td></tr>';

		detail.html(`
            <div class="wc-detail-head">
                <div>${backBtn}</div>
                <div style="display:flex;align-items:center;gap:8px">
                    ${statusChip(i.status)}
                    <button class="wc-btn" id="wc-hub">View in Account Hub</button>
                </div>
            </div>
            <h4>${frappe.utils.escape_html(i.username || i.account_id || "Customer")}
                <span style="font-weight:500;font-size:13px;color:var(--wc-ink3);margin-left:8px">level ${esc(
					i.level
				)} · ${esc(i.role)} · created ${esc((i.created_at || "").slice(0, 10))}</span>
            </h4>
            <div class="wc-kv-grid">
                ${kv("Phone", i.phone)}
                ${kv("Display currency", i.display_currency)}
                ${kv("Push tokens", d.devices && d.devices.push_tokens)}
                ${kv("Contacts", (d.contacts || []).length)}
                ${kv("Account ID", i.account_id, true)}
                ${kv("UUID", i.uuid, true)}
                ${kv("npub", i.npub, true)}
            </div>
            <h5>Wallets <span style="text-transform:none;letter-spacing:0;font-weight:500">— live IBEX balance</span></h5>
            <table>
                <thead><tr><th>Currency</th><th>Type</th><th style="text-align:right">Live balance</th><th></th><th>Wallet ID</th></tr></thead>
                <tbody>${walletRows}</tbody>
            </table>
            <h5>Migration</h5>
            <table>
                <thead><tr><th>Status</th><th>Run ID</th><th>When</th><th>Error</th></tr></thead>
                <tbody>${migRows}</tbody>
            </table>
            <h5>Recent transactions${
				d.tx_wallet_id
					? ` <span style="text-transform:none;letter-spacing:0;font-weight:500">— ${frappe.utils.escape_html(
							d.tx_wallet_id
					  )}</span>`
					: ""
			}</h5>
            <table>
                <thead><tr><th>When</th><th style="text-align:right">Amount</th><th>Currency</th><th>Type</th></tr></thead>
                <tbody>${txRows}</tbody>
            </table>
        `);

		this.page.main.find("#wc-back").on("click", () => this.close_detail());
		this.page.main.find("#wc-hub").on("click", () => {
			frappe.route_options = { account_hub_query: i.username || i.account_id };
			frappe.set_route("account-hub");
		});
	}

	export_csv() {
		const rows = this.filtered_rows();
		const cols = [
			"username",
			"account_id",
			"wallet_id",
			"currency",
			"balance",
			"status",
			"level",
			"role",
			"migration_status",
			"run_id",
			"created_at",
		];
		const esc = (v) => {
			let s = v === null || v === undefined ? "" : String(v);
			// Excel formula-injection guard
			if (typeof v === "string" && /^[=+\-@]/.test(s)) s = "'" + s;
			return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
		};
		const lines = [cols.join(",")];
		rows.forEach((r) => lines.push(cols.map((c) => esc(r[c])).join(",")));
		const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		a.href = url;
		a.download = `wallet-census-${this.active_bucket}.csv`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}
}
