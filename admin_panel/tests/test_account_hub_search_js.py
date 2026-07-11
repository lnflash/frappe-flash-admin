import re
from pathlib import Path

ACCOUNT_HUB_JS = (
	Path(__file__).resolve().parents[1] / "admin_panel" / "page" / "account_hub" / "account_hub.js"
)


def source():
	return ACCOUNT_HUB_JS.read_text()


def test_account_hub_defines_contains_style_default_list_search_helper():
	js = source()

	assert "function accountMatchesSearch" in js
	assert re.search(r"username[^\n]+email", js, re.DOTALL)
	assert ".includes(normalizedQuery)" in js
	assert "normalizePhoneSearchValue" in js


def test_search_input_filters_default_list_inline_without_remote_api_debounce():
	js = source()

	input_handler_match = re.search(
		r"searchInput\.on\('input', \(\) => \{(?P<body>.*?)\n\s*\}\);",
		js,
		re.DOTALL,
	)
	assert input_handler_match, "Expected Account Hub search input handler"

	body = input_handler_match.group("body")
	assert "filter_local_list" in body
	assert "debouncedSearch" not in body
	assert "perform_search" not in body


def test_result_clicks_stay_on_account_hub_and_select_account():
	js = source()

	assert "event.preventDefault();" in js
	assert "event.stopPropagation();" in js
	assert "this.on_result_click(account, item)" in js
	assert "frappe.set_route('Form', 'Account Upgrade Request'" not in js


def test_search_error_path_surfaces_server_message_before_generic():
	"""Not-found searches return a friendly 404 body; the error callback must
	show that message rather than always claiming a connection problem."""
	js = source()

	assert "const serverMsg =" in js
	assert "err.responseJSON" in js
	assert 'serverMsg || "Could not reach the server.' in js


def test_graphql_client_treats_invalid_account_id_as_not_found():
	client_py = (ACCOUNT_HUB_JS.parents[3] / "api" / "graphql_client.py").read_text()

	assert "_is_not_found_error" in client_py
	assert "InvalidAccountIdError" in client_py
	assert "UNEXPECTED_CLIENT_ERROR" in client_py


def test_graphql_client_lookups_tolerate_partial_responses():
	"""A resolved account node with field-level errors (e.g. Kratos 404 on
	owner.email) must be returned with nulls, not raised — the admin panel
	exists to inspect broken accounts."""
	client_py = (ACCOUNT_HUB_JS.parents[3] / "api" / "graphql_client.py").read_text()

	assert "GraphQL partial response" in client_py
	assert "if allow_not_found:" in client_py
