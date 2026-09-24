"""ENG-606: approval-created bank accounts carry a currency and a default, and
the one-off backfill heals the ones created before that.

Runs the real code (approve-flow helper and the whitelisted backfill, decorators
included) against the in-memory frappe stand-in.
"""

import types

import pytest
from idv_stubs import frappe

from admin_panel.api import admin_api, banking

PARTY = "CUST-0001"
OTHER_PARTY = "CUST-0002"


def account(name, party=PARTY, number="1000001", currency="JMD", bank="NCB", **extra):
	return {
		"name": name,
		"account_name": name.split(" - ")[0],
		"bank": bank,
		"bank_account_no": number,
		"branch_code": "001",
		"account_type": "Savings",
		"currency": currency,
		"is_default": 0,
		"disabled": 0,
		"is_company_account": 0,
		"party_type": "Customer",
		"party": party,
		"modified": 1,
		**extra,
	}


def row(fake, name, doctype="Bank Account"):
	return next((r for r in fake.rows(doctype) if r.get("name") == name), None)


def audit_entries(fake, action):
	return [c for c in fake.rows("Comment") if c["content"].startswith(f"[{action}]")]


@pytest.fixture()
def env(fake, monkeypatch):
	fake.autoname["Bank Account"] = lambda doc: f"{doc.account_name} - {doc.bank}"
	monkeypatch.setattr(frappe, "log_error", lambda *args, **kwargs: fake.errors.append(args), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	fake.seed("Customer", {"name": PARTY, "mobile_no": "+18765550100"})
	fake.seed("Bank", {"name": "NCB", "bank_name": "NCB"})
	return fake


def request(**overrides):
	data = {
		"name": "AUR-0001",
		"phone_number": "+18765550100",
		"full_name": "Alice Holder",
		"email": "alice@example.com",
		"address_title": None,
		"address_line1": None,
		"city": None,
		"country": None,
		"bank_name": "NCB",
		"bank_branch": "001",
		"account_type": "Savings",
		"account_number": "5550001",
		"currency": "USD",
	}
	data.update(overrides)
	return types.SimpleNamespace(**data)


def created_account(env):
	return row(env, "Alice Holder - NCB")


# ---- approval: currency ------------------------------------------------------


def test_approval_inserts_the_request_currency(env):
	errors, party = admin_api._create_erp_records(request(currency="USD"))

	assert (errors, party) == ([], PARTY)
	assert created_account(env)["currency"] == "USD"
	assert audit_entries(env, "approve_upgrade_currency_defaulted") == []


def test_approval_defaults_a_missing_currency_to_jmd_and_audit_logs_it(env):
	errors, _ = admin_api._create_erp_records(request(currency=None))

	assert errors == []
	assert created_account(env)["currency"] == "JMD"
	entries = audit_entries(env, "approve_upgrade_currency_defaulted")
	assert len(entries) == 1
	assert entries[0]["reference_doctype"] == "Account Upgrade Request"
	assert entries[0]["reference_name"] == "AUR-0001"
	assert "'currency': 'JMD'" in entries[0]["content"]
	assert "'requested': None" in entries[0]["content"]
	# account number is masked, never written in full
	assert "…0001" in entries[0]["content"]
	assert "5550001" not in entries[0]["content"]


@pytest.mark.parametrize("currency", ["", "  ", "EUR", "jamaican dollars"])
def test_approval_never_inserts_an_empty_or_unaccepted_currency(env, currency):
	errors, _ = admin_api._create_erp_records(request(currency=currency))

	assert errors == []
	assert created_account(env)["currency"] == "JMD"


def test_approval_normalises_currency_case(env):
	admin_api._create_erp_records(request(currency="usd"))

	assert created_account(env)["currency"] == "USD"
	assert audit_entries(env, "approve_upgrade_currency_defaulted") == []


def test_approval_normalises_the_account_type_like_self_serve(env):
	admin_api._create_erp_records(request(account_type="checking"))

	assert created_account(env)["account_type"] == "Chequing"


def test_approval_rejects_an_account_type_self_serve_would_reject(env):
	errors, party = admin_api._create_erp_records(request(account_type="Money Market"))

	assert party == PARTY
	assert len(errors) == 1 and errors[0].startswith("Bank Account: account_type must be one of")
	assert created_account(env) is None


# ---- approval: default -------------------------------------------------------


def test_approval_makes_the_first_enabled_account_the_default(env):
	admin_api._create_erp_records(request())

	assert created_account(env)["is_default"] == 1


def test_approval_leaves_default_alone_when_another_enabled_account_exists(env):
	env.seed("Bank Account", account("Old - NCB", number="9990001", is_default=1))

	admin_api._create_erp_records(request())

	assert created_account(env)["is_default"] == 0
	assert row(env, "Old - NCB")["is_default"] == 1


def test_approval_ignores_disabled_accounts_when_electing_the_default(env):
	env.seed("Bank Account", account("Removed - NCB", number="9990002", disabled=1, removed_by_customer=1))
	env.seed("Bank Account", account("Other - NCB", party=OTHER_PARTY, number="9990003", is_default=1))

	admin_api._create_erp_records(request())

	assert created_account(env)["is_default"] == 1


# ---- is_jamaican_bank --------------------------------------------------------


@pytest.mark.parametrize(
	"name",
	[
		"NCB",
		"National Commercial Bank",
		"Scotiabank",
		"JN Bank",
		"Sagicor Bank",
		"CIBC FirstCaribbean",
		"JMMB",
		"JMMB Bank (Jamaica) Ltd",
		"Bank of Nova Scotia Jamaica",
		"BNS",
		"Jamaica National Building Society",
		"JNBank",
		"JNBS",
		"First Global Bank",
		"Victoria Mutual Building Society",
		"VMBS",
		"VM Building Society",
		"Jamaica Co-operative Credit Union",
	],
)
def test_jamaican_banks_are_recognised(name):
	assert banking.is_jamaican_bank(name)


@pytest.mark.parametrize(
	"name",
	[
		"Chase",
		"Bank of America",
		"Wells Fargo",
		"Citibank",
		"US Bank",
		"Chase Jamaica",
		"Citi Jamaica",
		"Bank of America Jamaica",
		"Wells Fargo Jamaica",
		"Some Credit Union",
		"",
	],
)
def test_foreign_or_unknown_banks_are_not(name):
	assert not banking.is_jamaican_bank(name)


# ---- backfill ----------------------------------------------------------------


def seed_backfill(env):
	env.seed(
		"Bank", {"name": "Chase", "bank_name": "Chase"}, {"name": "Local", "bank_name": "Some Credit Union"}
	)
	env.seed(
		"Bank Account",
		account("Blank - NCB", currency="", number="1", modified=1),
		account("Null - NCB", currency=None, number="2", modified=3),
		account("Foreign - Chase", party=OTHER_PARTY, bank="Chase", currency="", number="3"),
		account("Unknown - Local", party="CUST-0003", bank="Local", currency="", number="4"),
		account("Fine - NCB", party="CUST-0004", currency="USD", number="5", is_default=1),
		account("Removed - NCB", currency="", number="6", disabled=1, removed_by_customer=1),
		account("Company - NCB", party=None, party_type="Company", currency="", number="7"),
		account("NoType - NCB", party="CUST-0005", currency="", account_type="", number="8"),
	)


def test_backfill_dry_run_reports_without_writing(env):
	seed_backfill(env)
	before = {r["name"]: dict(r) for r in env.rows("Bank Account")}

	result = banking.backfill_bank_account_currency()

	assert result == {
		"dry_run": True,
		"updated": ["Null - NCB", "Blank - NCB"],
		"defaults_set": ["Null - NCB", "Foreign - Chase", "Unknown - Local", "NoType - NCB"],
		"skipped_needs_review": [
			{
				"name": "Foreign - Chase",
				"bank": "Chase",
				"party": OTHER_PARTY,
				"reason": "bank not recognised",
			},
			{
				"name": "Unknown - Local",
				"bank": "Local",
				"party": "CUST-0003",
				"reason": "bank not recognised",
			},
			{"name": "NoType - NCB", "bank": "NCB", "party": "CUST-0005", "reason": "no account_type"},
		],
	}
	assert {r["name"]: dict(r) for r in env.rows("Bank Account")} == before
	assert env.rows("Comment") == []
	assert env.commits == 0


def test_backfill_real_run_sets_jmd_on_jamaican_banks_only(env):
	seed_backfill(env)

	result = banking.backfill_bank_account_currency(dry_run=0)

	assert result["dry_run"] is False
	assert result["updated"] == ["Null - NCB", "Blank - NCB"]
	assert row(env, "Blank - NCB")["currency"] == "JMD"
	assert row(env, "Null - NCB")["currency"] == "JMD"
	assert row(env, "Foreign - Chase")["currency"] == ""
	assert row(env, "Unknown - Local")["currency"] == ""
	assert row(env, "Fine - NCB")["currency"] == "USD"
	assert row(env, "Removed - NCB")["currency"] == ""
	assert row(env, "Company - NCB")["currency"] == ""
	assert row(env, "NoType - NCB")["currency"] == ""
	assert env.commits == 1


def test_backfill_skips_a_jamaican_account_with_no_account_type(env):
	env.seed("Bank Account", account("NoType - NCB", currency="", account_type=""))

	result = banking.backfill_bank_account_currency(dry_run=0)

	assert result["updated"] == []
	assert result["skipped_needs_review"] == [
		{"name": "NoType - NCB", "bank": "NCB", "party": PARTY, "reason": "no account_type"}
	]
	assert row(env, "NoType - NCB")["currency"] == ""
	assert row(env, "NoType - NCB")["account_type"] == ""
	assert audit_entries(env, "backfill_bank_account_currency") == []


def test_backfill_real_run_elects_a_default_per_party_without_one(env):
	seed_backfill(env)

	result = banking.backfill_bank_account_currency(dry_run="0")

	assert result["defaults_set"] == ["Null - NCB", "Foreign - Chase", "Unknown - Local", "NoType - NCB"]
	# most recently modified of the party's enabled accounts
	assert row(env, "Null - NCB")["is_default"] == 1
	assert row(env, "Blank - NCB")["is_default"] == 0
	assert row(env, "Foreign - Chase")["is_default"] == 1
	assert row(env, "Fine - NCB")["is_default"] == 1
	assert row(env, "Removed - NCB")["is_default"] == 0


def test_backfill_audit_logs_each_change_with_masked_numbers(env):
	env.seed("Bank Account", account("Blank - NCB", currency="", number="1111222233334444"))

	banking.backfill_bank_account_currency(dry_run=0)

	currency_entries = audit_entries(env, "backfill_bank_account_currency")
	assert len(currency_entries) == 1
	assert currency_entries[0]["reference_name"] == "Blank - NCB"
	assert "…4444" in currency_entries[0]["content"]
	assert "1111222233334444" not in currency_entries[0]["content"]
	assert len(audit_entries(env, "backfill_bank_account_default")) == 1


def test_backfill_is_idempotent(env):
	seed_backfill(env)
	banking.backfill_bank_account_currency(dry_run=0)

	second = banking.backfill_bank_account_currency(dry_run=0)

	assert second["updated"] == []
	assert second["defaults_set"] == []
	assert [s["name"] for s in second["skipped_needs_review"]] == [
		"Foreign - Chase",
		"Unknown - Local",
		"NoType - NCB",
	]
	assert env.commits == 1


def test_backfill_with_nothing_to_do_writes_nothing(env):
	env.seed("Bank Account", account("Fine - NCB", is_default=1))

	result = banking.backfill_bank_account_currency(dry_run=0)

	assert result == {"dry_run": False, "updated": [], "defaults_set": [], "skipped_needs_review": []}
	assert env.commits == 0
