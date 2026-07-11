"""Contract tests for the ops-pulse page instrumentation.

Text-level assertions in the repo's established style: they pin the
invariants the ops-pulse rollout introduced — endpoint gating, page
wiring, the desk-SPA Escape-handler guards, server-clock age math, and
CSS scoping (the pre-rollout blocks declared GLOBAL selectors that bled
into every desk page).
"""

import re
from pathlib import Path

ADMIN_PANEL = Path(__file__).resolve().parents[1]
PAGES = ADMIN_PANEL / "admin_panel" / "page"


def read(path):
	return path.read_text()


PULSE_PY = read(ADMIN_PANEL / "api" / "pulse.py")
TRANSFER_JS = read(PAGES / "transfer_requests" / "transfer_requests.js")
MGMT_JS = read(PAGES / "account_management" / "account_management.js")
ALERT_JS = read(PAGES / "alert_users" / "alert_users.js")


def test_pulse_endpoints_are_whitelisted_and_admin_gated():
	"""Every pulse endpoint carries the full decorator stack, in order —
	whitelist alone would expose queue metrics to any logged-in user."""
	for fn in ("get_dashboard_pulse", "get_transfer_pulse", "get_upgrade_pulse"):
		stack = f"@frappe.whitelist()\n@require_admin()\n@handle_api_errors\ndef {fn}("
		assert stack in PULSE_PY, f"{fn} is missing the whitelist/require_admin/handle_api_errors stack"


def test_pages_wire_their_pulse_endpoints():
	assert 'method: "admin_panel.api.pulse.get_transfer_pulse"' in TRANSFER_JS
	assert 'method: "admin_panel.api.pulse.get_upgrade_pulse"' in MGMT_JS


def test_drawer_escape_handlers_guard_dialog_and_page_visibility():
	"""Desk keeps page wrappers alive after navigation; a document-level
	Escape handler without both guards closes drawers on OTHER pages."""
	for js in (TRANSFER_JS, MGMT_JS):
		handler = re.search(r"keydown\.[a-z_]+\", \(e\) => \{(?P<body>.*?)\n\t\t\}\);", js, re.DOTALL)
		assert handler, "expected a namespaced document keydown handler"
		body = handler.group("body")
		assert "window.cur_dialog" in body
		assert 'this.page.wrapper.is(":visible")' in body


def test_age_math_uses_server_clock_and_iso_safe_parsing():
	"""frappe datetimes are space-separated (implementation-defined in
	new Date(); Invalid Date on WebKit) and server-local — ages must be
	computed from the payload's `now`, parsed with the T-separator."""
	for js in (TRANSFER_JS, MGMT_JS):
		assert "server_now_ms()" in js
		assert 'replace(" ", "T")' in js
		assert re.search(
			r"formatAge\(dateStr\) \{\n\t\tconst then = new Date\(String\(dateStr\)\.replace", js
		)


def test_page_css_stays_scoped():
	"""The pre-rollout blocks styled global .form-control / .modern-*
	selectors, restyling every desk form while the page was in the DOM.
	All rules must lead with the page's scope class."""
	for js, scope in (
		(ALERT_JS, ".alert-users-page"),
		(MGMT_JS, ".flash-account-manager"),
		(TRANSFER_JS, ".flash-cashout-manager"),
	):
		css = js[js.index("<style>") : js.index("</style>")]
		leaks = re.findall(r"\n\s+(\.(?:form-control|modern-[a-z-]+)[^\n{]*)\{", css)
		assert not leaks, f"unscoped selectors in {scope} page CSS: {leaks}"
		assert scope in css, f"expected {scope}-scoped rules"
