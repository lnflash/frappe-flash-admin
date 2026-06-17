from pathlib import Path
import re

ACCOUNT_HUB_JS = Path(__file__).resolve().parents[1] / "admin_panel" / "page" / "account_hub" / "account_hub.js"


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
