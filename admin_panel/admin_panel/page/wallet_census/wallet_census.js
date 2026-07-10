frappe.pages["wallet-census"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Wallet Census",
		single_column: true,
	});

	if (!frappe.user_roles.includes("Accounts Manager")) {
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

class WalletCensus {
	constructor(page) {
		this.page = page;
		this.rows = [];
		this.totals = {};
		this.bucket_counts = {};
		this.active_bucket = "all";
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
            <div class="wallet-census">
                <div id="wc-status" class="text-muted small mb-3"></div>
                <div id="wc-summary" class="row mb-3"></div>
                <div id="wc-buckets" class="mb-2"></div>
                <div class="mb-2">
                    <input type="text" id="wc-search" class="form-control" style="max-width:320px;display:inline-block"
                        placeholder="Filter by username / accountId…">
                    <button class="btn btn-default btn-sm ml-2" id="wc-export">Export CSV</button>
                </div>
                <div id="wc-table" class="table-responsive"></div>
            </div>
        `);

		const search = this.page.main.find("#wc-search");
		search.on(
			"input",
			wc_debounce(() => this.render_table(), 200)
		);
		this.page.main.find("#wc-export").on("click", () => this.export_csv());
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
				`<span class="text-danger">Last run failed: ${frappe.utils.escape_html(
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
            <div class="col-sm-3">
                <div class="card p-3 mb-2">
                    <div class="text-muted small">${title}</div>
                    <div style="font-size:1.4rem;font-weight:600">${value}</div>
                    <div class="text-muted small">${sub || ""}</div>
                </div>
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
			const active = b.key === this.active_bucket ? "btn-primary" : "btn-default";
			return `<button class="btn btn-sm ${active} mr-1 mb-1 wc-bucket" data-bucket="${b.key}">${b.label} <span class="badge">${count}</span></button>`;
		}).join("");
		const el = this.page.main.find("#wc-buckets");
		el.html(html);
		el.find(".wc-bucket").on("click", (e) => {
			this.active_bucket = e.currentTarget.dataset.bucket;
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
		const body = rows
			.map(
				(r) => `
            <tr>
                <td>${frappe.utils.escape_html(r.username || "—")}</td>
                <td style="text-align:right">${
					r.balance
						? Number(r.balance).toLocaleString(undefined, {
								minimumFractionDigits: 2,
								maximumFractionDigits: 2,
						  })
						: "0.00"
				}</td>
                <td>${r.currency || "—"}</td>
                <td>${frappe.utils.escape_html(r.status || "—")}</td>
                <td>${frappe.utils.escape_html(r.migration_status || "—")}</td>
                <td><code>${frappe.utils.escape_html(r.account_id || "")}</code></td>
            </tr>`
			)
			.join("");
		this.page.main.find("#wc-table").html(`
            <div class="text-muted small mb-1">${rows.length} accounts</div>
            <table class="table table-bordered table-hover">
                <thead><tr>${head}</tr></thead>
                <tbody>${
					body ||
					'<tr><td colspan="6" class="text-center text-muted">No accounts</td></tr>'
				}</tbody>
            </table>`);
		this.page.main.find(".wc-sort").on("click", (e) => {
			const key = e.currentTarget.dataset.key;
			if (this.sort_key === key) this.sort_dir = this.sort_dir === "desc" ? "asc" : "desc";
			else {
				this.sort_key = key;
				this.sort_dir = "desc";
			}
			this.render_table();
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
			const s = v === null || v === undefined ? "" : String(v);
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
