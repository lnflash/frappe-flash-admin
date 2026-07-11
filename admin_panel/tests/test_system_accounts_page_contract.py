"""Contract tests for the System Accounts treasury page + API.

The invariants that matter here are the money ones: read endpoints carry
the financial gate, the transfer endpoint is System-Manager-only with a
cap and a role-wallet-only guard, and every attempt lands in the
append-only System Transfer Log.
"""

import json
import re
from pathlib import Path

ADMIN_PANEL = Path(__file__).resolve().parents[1]
API_PY = (ADMIN_PANEL / "api" / "system_accounts.py").read_text()
IBEX_PY = (ADMIN_PANEL / "api" / "ibex_client.py").read_text()
PAGE_JS = (ADMIN_PANEL / "admin_panel" / "page" / "system_accounts" / "system_accounts.js").read_text()
SETUP_PY = (ADMIN_PANEL / "admin_panel" / "setup.py").read_text()


def test_read_endpoints_carry_the_financial_gate():
	for fn in ("get_system_accounts", "get_system_account_activity"):
		stack = f"@frappe.whitelist()\n@require_financial()\n@handle_api_errors\ndef {fn}("
		assert stack in API_PY, f"{fn} must be whitelisted + require_financial + handle_api_errors"


def test_transfer_endpoint_is_system_manager_only_with_cap_and_role_guard():
	stack = (
		'@frappe.whitelist()\n@require_roles(["System Manager"])\n'
		"@handle_api_errors\ndef transfer_between_system_wallets("
	)
	assert stack in API_PY
	assert "system_transfer_cap_usd" in API_PY
	assert "DEFAULT_TRANSFER_CAP_USD" in API_PY
	# watchlist accounts are view-only: only transferable (role) wallets qualify
	assert 'if acc["transferable"]' in API_PY
	assert '"Sender is not a role-account wallet"' in API_PY
	assert '"Receiver is not a role-account wallet"' in API_PY


def test_every_transfer_attempt_is_logged_before_money_moves():
	insert_pos = API_PY.index('"doctype": "System Transfer Log"')
	pay_pos = API_PY.index("client.add_invoice(")
	assert insert_pos < pay_pos, "the log doc must be inserted before any IBEX call"
	assert 'log.db_set("status", "Failed")' in API_PY
	assert 'log.db_set("status", "Paid")' in API_PY


def test_activity_endpoint_revalidates_wallet_membership():
	assert '"Not a system-account wallet"' in API_PY
	assert "frappe.PermissionError" in API_PY


def test_ibex_client_write_surface_is_exactly_the_two_invoice_calls():
	assert '"/v2/invoice/add"' in IBEX_PY
	assert '"/v2/invoice/pay"' in IBEX_PY
	posts = re.findall(r"self\._post\(\s*\n?\s*\"([^\"]+)\"", IBEX_PY)
	assert set(posts) <= {"/v2/invoice/add", "/v2/invoice/pay"}, f"unexpected IBEX write endpoints: {posts}"


def test_page_gates_and_wiring():
	assert 'SA_VIEW_ROLES = ["System Manager", "Accounts Manager"]' in PAGE_JS
	assert "Flash Admin" not in PAGE_JS  # view tier matches require_financial
	assert 'frappe.user_roles.includes("System Manager")' in PAGE_JS  # transfer control gate
	assert "admin_panel.api.system_accounts.get_system_accounts" in PAGE_JS
	assert "admin_panel.api.system_accounts.get_system_account_activity" in PAGE_JS
	assert "admin_panel.api.system_accounts.transfer_between_system_wallets" in PAGE_JS
	assert "frappe.confirm(" in PAGE_JS  # transfers are review-then-confirm


def test_page_css_stays_scoped():
	css = PAGE_JS[PAGE_JS.index("SA_CSS") : PAGE_JS.index("frappe.pages")]
	leaks = re.findall(r"\n\s+(\.(?:form-control|modern-[a-z-]+|sa-[a-z-]+)[^\n{]*)\{", css)
	assert not leaks, f"unscoped selectors in system_accounts CSS: {leaks}"


def test_page_is_registered_everywhere():
	assert '"name": "system-accounts"' in SETUP_PY
	workspace = json.loads((ADMIN_PANEL / "fixtures" / "workspace.json").read_text())
	links = workspace[0]["links"] if isinstance(workspace, list) else workspace["links"]
	assert any(l.get("link_type") == "Page" and l.get("link_to") == "system-accounts" for l in links)
	page_json = json.loads(
		(ADMIN_PANEL / "admin_panel" / "page" / "system_accounts" / "system_accounts.json").read_text()
	)
	assert page_json["name"] == "system-accounts"
	assert page_json["title"] == "System Accounts"


def test_transfer_log_doctype_is_append_only():
	dt = json.loads(
		(
			ADMIN_PANEL / "admin_panel" / "doctype" / "system_transfer_log" / "system_transfer_log.json"
		).read_text()
	)
	assert dt["in_create"] == 1  # no desk New button
	for perm in dt["permissions"]:
		assert not perm.get("write") and not perm.get("create") and not perm.get("delete"), (
			f"System Transfer Log must be read-only via desk: {perm}"
		)
