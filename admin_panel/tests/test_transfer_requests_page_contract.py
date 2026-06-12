import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_PANEL = REPO_ROOT / "admin_panel"
PAGE_DIR = ADMIN_PANEL / "admin_panel" / "page" / "transfer_requests"


def read_text(path):
    return path.read_text()


def workspace_links():
    workspace = json.loads((ADMIN_PANEL / "fixtures" / "workspace.json").read_text())
    return workspace["links"]


def test_admin_dashboard_routes_transfer_requests_card_to_custom_page():
    js = read_text(ADMIN_PANEL / "admin_panel" / "page" / "admin_dashboard" / "admin_dashboard.js")

    assert "ad-tool-title\">Transfer Requests" in js
    assert 'data-route="/app/transfer-requests"' in js
    assert 'data-route="/app/bridge-transfer-request"' not in js


def test_setup_registers_transfer_requests_page_not_cashout_requests():
    setup_py = read_text(ADMIN_PANEL / "admin_panel" / "setup.py")

    assert '"name": "transfer-requests"' in setup_py
    assert '"title": "Transfer Requests"' in setup_py
    assert '"name": "cashout-requests"' not in setup_py
    assert 'delete_doc("Page", "cashout-requests"' in setup_py


def test_transfer_requests_page_fixture_replaces_cashout_requests_page():
    page_json = json.loads((PAGE_DIR / "transfer_requests.json").read_text())

    assert page_json["name"] == "transfer-requests"
    assert page_json["page_name"] == "transfer-requests"
    assert page_json["title"] == "Transfer Requests"
    assert not (ADMIN_PANEL / "admin_panel" / "page" / "cashout_requests").exists()


def test_transfer_requests_js_registers_page_and_bridge_tab():
    js = read_text(PAGE_DIR / "transfer_requests.js")

    assert "frappe.pages['transfer-requests']" in js
    assert "TransferRequestsManager" in js
    assert "Cashouts" in js
    assert "Bridge" in js
    assert "get_bridge_transfer_requests" in js


def test_workspace_keeps_doctype_links_and_removes_cashout_requests_page_link():
    links = workspace_links()

    assert any(
        link["link_type"] == "DocType" and link["link_to"] == "Cashout"
        for link in links
    )
    assert any(
        link["link_type"] == "DocType" and link["link_to"] == "Bridge Transfer Request"
        for link in links
    )
    assert any(
        link["link_type"] == "Page"
        and link["label"] == "Transfer Requests"
        and link["link_to"] == "transfer-requests"
        for link in links
    )
    assert not any(
        link["link_type"] == "Page"
        and (link["label"] == "Cashout Requests" or link["link_to"] == "cashout-requests")
        for link in links
    )


def test_admin_api_exposes_bridge_transfer_requests_read_only_endpoint():
    api_py = read_text(ADMIN_PANEL / "api" / "admin_api.py")

    assert "def get_bridge_transfer_requests" in api_py
    assert '"Bridge Transfer Request"' in api_py
    assert "transaction_type" in api_py
    assert "failure_reason" in api_py


def test_transfer_requests_cashout_tab_has_account_management_style_action_buttons():
    js = read_text(PAGE_DIR / "transfer_requests.js")

    assert "create_request_row(req, showActions = true)" in js
    assert "'Actions'" in js
    assert "modern-icon-btn" in js
    assert "btn-quick-create" in js
    assert "btn-quick-confirm" in js
    assert "btn-quick-complete" in js
    assert "e.stopPropagation()" in js
    assert "closest('button')" in js
    assert "create_cashout_request(req)" in js
    assert "confirm_cashout_payment(req)" in js
    assert "complete_cashout(req)" in js


def test_transfer_requests_bridge_tab_stays_read_only_without_actions_column():
    js = read_text(PAGE_DIR / "transfer_requests.js")

    assert "const cashoutHeaders" in js
    assert "const bridgeHeaders" in js
    assert "const headers = this.active_type === 'bridge' ? bridgeHeaders : cashoutHeaders" in js
    assert "const bridgeHeaders = ['Request ID', 'Type', 'Amount', 'Status', 'Failure', 'Last Seen']" in js


def test_admin_api_exposes_cashout_action_endpoints():
    api_py = read_text(ADMIN_PANEL / "api" / "admin_api.py")

    assert "def create_cashout_request" in api_py
    assert "def confirm_cashout_payment" in api_py
    assert "def complete_cashout" in api_py
    assert "confirmation_code" in api_py
