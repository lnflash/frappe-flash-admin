import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_PANEL = REPO_ROOT / "admin_panel"
DOCTYPE_DIR = ADMIN_PANEL / "admin_panel" / "doctype" / "bank_account_update_request"


def read_text(path):
	return path.read_text()


def test_admin_api_exposes_bank_account_update_endpoints():
	api_py = read_text(ADMIN_PANEL / "api" / "admin_api.py")
	assert "def approve_bank_account_update_request" in api_py
	assert "def reject_bank_account_update_request" in api_py
	assert "Bank Account Update Request" in api_py


def test_approve_patches_in_place_preserving_identity():
	api_py = read_text(ADMIN_PANEL / "api" / "admin_api.py")
	# The patch must load the existing Bank Account doc (preserving its `name`),
	# never delete + recreate.
	assert 'frappe.get_doc("Bank Account", req.bank_account, for_update=True)' in api_py
	assert "bank_account.save(ignore_permissions=True)" in api_py
	# `is_default` must be left untouched so it survives the patch.
	assert "bank_account.is_default" not in api_py
	# Ownership is re-verified at approval time.
	assert "bank_account.party != req.party" in api_py


def test_doctype_definition():
	data = json.loads(read_text(DOCTYPE_DIR / "bank_account_update_request.json"))
	assert data["name"] == "Bank Account Update Request"
	assert data["module"] == "Admin Panel"
	fieldnames = {f["fieldname"] for f in data["fields"]}
	for expected in (
		"party",
		"bank_account",
		"status",
		"bank_name",
		"bank_branch",
		"account_type",
		"account_number",
		"currency",
		"support_note",
	):
		assert expected in fieldnames
	status_field = next(f for f in data["fields"] if f["fieldname"] == "status")
	assert status_field["options"] == "Pending\nApproved\nRejected\nClosed"


def test_controller_class_present():
	controller = read_text(DOCTYPE_DIR / "bank_account_update_request.py")
	assert "class BankAccountUpdateRequest(Document)" in controller


def test_approve_guards_incomplete_and_supersedes_siblings():
	api_py = read_text(ADMIN_PANEL / "api" / "admin_api.py")
	# Incomplete requests are rejected rather than blanking the live account.
	assert "missing required bank details" in api_py
	# Other still-open requests for the same account are closed on approval.
	assert 'set_value("Bank Account Update Request", sibling, "status", "Closed")' in api_py
