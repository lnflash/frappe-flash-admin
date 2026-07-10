import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_PANEL = REPO_ROOT / "admin_panel"
PAGE_DIR = ADMIN_PANEL / "admin_panel" / "page" / "wallet_census"
DOCTYPE_DIR = ADMIN_PANEL / "admin_panel" / "doctype" / "wallet_census_snapshot"


def read_text(path):
	return path.read_text()


def lines_above_def(source, def_name, count=5):
	return source.split(f"def {def_name}")[0].splitlines()[-count:]


def test_setup_registers_wallet_census_page():
	setup_py = read_text(ADMIN_PANEL / "admin_panel" / "setup.py")

	assert '"name": "wallet-census"' in setup_py
	assert '"title": "Wallet Census"' in setup_py


def test_wallet_census_page_fixture_name_matches_page_name():
	page_json = json.loads((PAGE_DIR / "wallet_census.json").read_text())

	assert page_json["name"] == "wallet-census"
	assert page_json["page_name"] == "wallet-census"


def test_snapshot_doctype_does_not_track_changes():
	doctype_json = json.loads((DOCTYPE_DIR / "wallet_census_snapshot.json").read_text())

	assert doctype_json["track_changes"] == 0


def test_run_census_now_is_bench_execute_only_while_start_census_is_whitelisted():
	census_py = read_text(ADMIN_PANEL / "api" / "census.py")

	# run_census_now blocks the caller for the full scan — it must never grow
	# a whitelist decorator. start_census is the whitelisted (queued) path.
	assert "def run_census_now" in census_py
	assert "@frappe.whitelist()" not in "\n".join(lines_above_def(census_py, "run_census_now"))
	assert "def start_census" in census_py
	assert "@frappe.whitelist()" in "\n".join(lines_above_def(census_py, "start_census"))


def test_census_defines_stale_run_and_retention_constants():
	census_py = read_text(ADMIN_PANEL / "api" / "census.py")

	assert "STALE_RUN_SECONDS" in census_py
	assert "KEEP_SNAPSHOTS" in census_py


def test_wallet_census_js_gates_roles_pages_rows_and_guards_csv_formulas():
	js = read_text(PAGE_DIR / "wallet_census.js")

	assert "WC_ALLOWED_ROLES" in js
	assert "Flash Admin" in js
	assert r"^[=+\-@]" in js
	assert "Show all" in js


def test_customer_detail_caps_tx_limit():
	customer_py = read_text(ADMIN_PANEL / "api" / "customer.py")

	assert "cint(tx_limit)" in customer_py
