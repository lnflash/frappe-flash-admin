"""Behavioral tests for the customer self-serve bank account endpoints.

flash calls add / update / set_default / delete on behalf of the customer, so
these run the real endpoint code (decorators included) against the in-memory
frappe stand-in. The fixture adds the few surfaces the shared fake lacks:
delete_doc with link checking, savepoints, and frappe-shaped exceptions so
handle_api_errors re-raises throws the way it does in production.
"""

import copy

import pytest
from idv_stubs import frappe, frappe_utils

if not hasattr(frappe_utils, "cstr"):
	frappe_utils.cstr = lambda value: "" if value is None else str(value)
if not hasattr(frappe_utils, "cint"):

	def _cint(value):
		try:
			return int(value)
		except (TypeError, ValueError):
			return 0

	frappe_utils.cint = _cint

from admin_panel.api import banking

PARTY = "CUST-0001"
OTHER_PARTY = "CUST-0002"


def account(name, party=PARTY, number="1000001", currency="JMD", **extra):
	return {
		"name": name,
		"account_name": name.split(" - ")[0],
		"bank": "NCB",
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


@pytest.fixture()
def bank(fake, monkeypatch):
	class Thrown(frappe.ValidationError):
		pass

	class DoesNotExistError(frappe.ValidationError):
		http_status_code = 404

	class LinkExistsError(frappe.ValidationError):
		pass

	def throw(msg, exc=None, *args, **kwargs):
		raise (exc or Thrown)(msg)

	savepoints = {}

	def savepoint(name):
		savepoints[name] = copy.deepcopy(fake.tables)

	def rollback(*, save_point=None):
		if save_point is None:
			return fake.rollback()
		fake.tables = copy.deepcopy(savepoints[save_point])

	def delete_doc(doctype, name, ignore_permissions=False):
		rows = fake.rows(doctype)
		row = next(r for r in rows if r.get("name") == name)
		# on_trash side effect BEFORE the link check, like the real delete_doc:
		# the endpoint must not let this survive a refused delete.
		row["on_trash_ran"] = 1
		linked = any(r.get("bank_account") == name for r in fake.rows("Cashout")) or any(
			r.get("bank_account") == name for r in fake.rows("Bank Account Update Request")
		)
		if linked:
			raise LinkExistsError(f"Cannot delete {name}: linked")
		rows.remove(row)

	fake.autoname["Bank Account"] = lambda doc: f"{doc.account_name} - {doc.bank}"
	monkeypatch.setattr(frappe, "throw", throw, raising=False)
	monkeypatch.setattr(frappe, "DoesNotExistError", DoesNotExistError, raising=False)
	monkeypatch.setattr(frappe, "LinkExistsError", LinkExistsError, raising=False)
	monkeypatch.setattr(frappe, "delete_doc", delete_doc, raising=False)
	frappe.db.savepoint = savepoint
	frappe.db.rollback = rollback

	fake.seed("Customer", {"name": PARTY}, {"name": OTHER_PARTY})
	fake.seed("Bank", {"name": "NCB", "bank_name": "NCB"})
	fake.Thrown = Thrown
	fake.DoesNotExistError = DoesNotExistError
	return fake


def removed(name, **extra):
	"""An account the customer removed (soft delete): disabled AND marked."""
	return account(name, disabled=1, removed_by_customer=1, **extra)


def row(bank, name, doctype="Bank Account"):
	return next((r for r in bank.rows(doctype) if r.get("name") == name), None)


def audit_entries(bank, action):
	return [c for c in bank.rows("Comment") if c["content"].startswith(f"[{action}]")]


# ---- delete_bank_account -----------------------------------------------------


def test_delete_hard_deletes_an_unreferenced_account(bank):
	bank.seed("Bank Account", account("A - NCB", number="1111222233334444"))

	result = banking.delete_bank_account("A - NCB", PARTY)

	assert result == {
		"success": True,
		"bank_account_id": "A - NCB",
		"deleted": True,
		"disabled": False,
		"new_default": None,
	}
	assert row(bank, "A - NCB") is None
	assert bank.commits == 1


def test_delete_audit_masks_the_account_number(bank):
	bank.seed("Bank Account", account("A - NCB", number="1111222233334444"))

	banking.delete_bank_account("A - NCB", PARTY)

	(entry,) = audit_entries(bank, "delete_bank_account")
	assert "…4444" in entry["content"]
	assert "1111222233334444" not in entry["content"]
	# The Bank Account is gone, so the entry is anchored on the Customer.
	assert (entry["reference_doctype"], entry["reference_name"]) == ("Customer", PARTY)


def test_delete_falls_back_to_disable_when_links_exist(bank):
	bank.seed("Bank Account", account("A - NCB", is_default=1))
	bank.seed("Cashout", {"name": "CO-1", "bank_account": "A - NCB"})

	result = banking.delete_bank_account("A - NCB", PARTY)

	assert result["deleted"] is False
	assert result["disabled"] is True
	kept = row(bank, "A - NCB")
	assert kept["disabled"] == 1
	# Marked as the customer's own removal, which is what makes it revivable.
	assert kept["removed_by_customer"] == 1
	assert kept["is_default"] == 0
	# The refused delete was rolled back to the savepoint, side effects and all.
	assert "on_trash_ran" not in kept
	(entry,) = audit_entries(bank, "delete_bank_account")
	assert (entry["reference_doctype"], entry["reference_name"]) == ("Bank Account", "A - NCB")


def test_delete_rejects_a_non_owner(bank):
	bank.seed("Bank Account", account("A - NCB", party=OTHER_PARTY))

	with pytest.raises(bank.Thrown, match="does not belong to this customer"):
		banking.delete_bank_account("A - NCB", PARTY)

	assert row(bank, "A - NCB")["disabled"] == 0
	assert bank.commits == 0


def test_delete_rejects_company_and_non_customer_accounts(bank):
	bank.seed(
		"Bank Account",
		account("Company - NCB", is_company_account=1),
		account("Supplier - NCB", number="2", party_type="Supplier"),
	)

	for name in ("Company - NCB", "Supplier - NCB"):
		with pytest.raises(bank.Thrown, match="does not belong to this customer"):
			banking.delete_bank_account(name, PARTY)
		assert row(bank, name) is not None


def test_delete_of_an_already_removed_account_is_not_found(bank):
	bank.seed("Bank Account", account("A - NCB", disabled=1))

	with pytest.raises(bank.DoesNotExistError, match="not found"):
		banking.delete_bank_account("A - NCB", PARTY)


def test_delete_default_reelects_preferring_same_currency(bank):
	bank.seed(
		"Bank Account",
		account("Default - NCB", number="1", currency="JMD", is_default=1, modified=5),
		account("Old JMD - NCB", number="2", currency="JMD", modified=10),
		account("New JMD - NCB", number="3", currency="JMD", modified=20),
		account("Newest USD - NCB", number="4", currency="USD", modified=30),
		account("Removed JMD - NCB", number="5", currency="JMD", modified=40, disabled=1),
		account("Other party - NCB", number="6", currency="JMD", modified=50, party=OTHER_PARTY),
	)

	result = banking.delete_bank_account("Default - NCB", PARTY)

	assert result["new_default"] == "New JMD - NCB"
	defaults = [r["name"] for r in bank.rows("Bank Account") if r["is_default"]]
	assert defaults == ["New JMD - NCB"]


def test_delete_default_falls_back_to_another_currency(bank):
	bank.seed(
		"Bank Account",
		account("Default - NCB", number="1", currency="JMD", is_default=1),
		account("USD old - NCB", number="2", currency="USD", modified=10),
		account("USD new - NCB", number="3", currency="USD", modified=20),
	)

	assert banking.delete_bank_account("Default - NCB", PARTY)["new_default"] == "USD new - NCB"


def test_delete_non_default_leaves_the_default_alone(bank):
	bank.seed(
		"Bank Account",
		account("Default - NCB", number="1", is_default=1),
		account("Second - NCB", number="2", modified=99),
	)

	result = banking.delete_bank_account("Second - NCB", PARTY)

	assert result["new_default"] is None
	assert row(bank, "Default - NCB")["is_default"] == 1


def test_delete_last_account_elects_nobody(bank):
	bank.seed("Bank Account", account("Only - NCB", is_default=1))

	assert banking.delete_bank_account("Only - NCB", PARTY)["new_default"] is None


def test_delete_closes_pending_update_requests_only(bank):
	bank.seed("Bank Account", account("A - NCB"), account("B - NCB", number="2"))
	bank.seed(
		"Bank Account Update Request",
		{"name": "REQ-1", "bank_account": "A - NCB", "status": "Pending"},
		{"name": "REQ-2", "bank_account": "A - NCB", "status": "Pending"},
		{"name": "REQ-3", "bank_account": "A - NCB", "status": "Rejected"},
		{"name": "REQ-4", "bank_account": "B - NCB", "status": "Pending"},
	)

	result = banking.delete_bank_account("A - NCB", PARTY)

	statuses = {r["name"]: r["status"] for r in bank.rows("Bank Account Update Request")}
	assert statuses == {"REQ-1": "Closed", "REQ-2": "Closed", "REQ-3": "Rejected", "REQ-4": "Pending"}
	# The requests still link to the account, so it is disabled, and the
	# savepoint rollback must not have reopened them.
	assert result["disabled"] is True


# ---- disabled accounts are invisible ------------------------------------------


def test_disabled_accounts_hidden_from_the_list(bank):
	bank.seed(
		"Bank Account", account("Live - NCB", number="1"), account("Gone - NCB", number="2", disabled=1)
	)

	result = banking.get_customer_banking(erp_party=PARTY)

	assert [a["name"] for a in result["bank_accounts"]] == ["Live - NCB"]


def test_support_view_includes_disabled_accounts_with_the_removal_marker(bank):
	bank.seed(
		"Bank Account",
		account("Live - NCB", number="1", is_default=1),
		removed("Gone - NCB", number="2"),
		account("Held - NCB", number="3", disabled=1),
	)

	result = banking.get_customer_banking(erp_party=PARTY, include_disabled=1)

	assert {a["name"]: (a["disabled"], a["removed_by_customer"]) for a in result["bank_accounts"]} == {
		"Live - NCB": (0, None),
		"Gone - NCB": (1, 1),
		"Held - NCB": (1, None),
	}


@pytest.mark.parametrize("flag", [0, "0", None, ""])
def test_falsy_include_disabled_keeps_them_hidden(bank, flag):
	"""The flag arrives as a string over HTTP — "0" must not read as truthy."""
	bank.seed("Bank Account", account("Live - NCB", number="1"), removed("Gone - NCB", number="2"))

	result = banking.get_customer_banking(erp_party=PARTY, include_disabled=flag)

	assert [a["name"] for a in result["bank_accounts"]] == ["Live - NCB"]


def test_disabled_account_cannot_become_default(bank):
	bank.seed(
		"Bank Account",
		account("Live - NCB", number="1", is_default=1),
		account("Gone - NCB", number="2", disabled=1),
	)

	with pytest.raises(bank.DoesNotExistError):
		banking.set_default_bank_account("Gone - NCB", PARTY)

	assert row(bank, "Live - NCB")["is_default"] == 1
	assert row(bank, "Gone - NCB")["is_default"] == 0


def test_disabled_account_cannot_be_edited(bank):
	bank.seed("Bank Account", account("Gone - NCB", number="2", disabled=1))

	with pytest.raises(bank.DoesNotExistError):
		banking.update_bank_account("Gone - NCB", PARTY, "NCB", "999", "Savings", "JMD")

	assert row(bank, "Gone - NCB")["bank_account_no"] == "2"


def test_set_default_still_works_for_live_accounts(bank):
	bank.seed(
		"Bank Account",
		account("First - NCB", number="1", is_default=1),
		account("Second - NCB", number="2"),
	)

	assert banking.set_default_bank_account("Second - NCB", PARTY) == {"success": True}
	assert row(bank, "First - NCB")["is_default"] == 0
	assert row(bank, "Second - NCB")["is_default"] == 1


# ---- add_bank_account: re-add + naming ----------------------------------------


def test_readding_a_removed_account_reenables_it(bank):
	bank.seed(
		"Bank Account",
		account("Live - NCB", number="1", is_default=1),
		removed("Gone - NCB", number="2", currency="JMD", account_type="Savings"),
	)

	result = banking.add_bank_account(PARTY, "NCB", "2", "Chequing", "USD", bank_branch="042")

	assert result == {"success": True, "bank_account": "Gone - NCB", "reenabled": True}
	revived = row(bank, "Gone - NCB")
	assert revived["disabled"] == 0
	assert revived["removed_by_customer"] == 0
	assert (revived["account_type"], revived["currency"], revived["branch_code"]) == (
		"Chequing",
		"USD",
		"042",
	)
	assert revived["is_default"] == 0
	assert len(bank.rows("Bank Account")) == 2


def test_readded_account_becomes_default_when_it_is_the_only_live_one(bank):
	bank.seed("Bank Account", removed("Gone - NCB", number="2"))

	banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD")

	assert row(bank, "Gone - NCB")["is_default"] == 1


def test_readd_with_set_default_clears_the_previous_default(bank):
	bank.seed(
		"Bank Account",
		account("Live - NCB", number="1", is_default=1),
		removed("Gone - NCB", number="2"),
	)

	banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD", set_default=1)

	assert row(bank, "Gone - NCB")["is_default"] == 1
	assert row(bank, "Live - NCB")["is_default"] == 0


def test_admin_disabled_account_is_not_revived_by_a_readd(bank):
	"""Support disabled it from the desk (fraud hold, ownership dispute): no
	removal marker, so self-serve must not switch it back on."""
	bank.seed("Bank Account", account("Held - NCB", number="2", disabled=1))

	with pytest.raises(bank.Thrown, match="already exists"):
		banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD")

	held = row(bank, "Held - NCB")
	assert held["disabled"] == 1
	assert len(bank.rows("Bank Account")) == 1
	assert audit_entries(bank, "add_bank_account") == []


def test_remove_then_readd_round_trip(bank):
	"""The marker is written by the real delete path and consumed by the real add path."""
	bank.seed("Bank Account", account("A - NCB", number="2"))
	bank.seed("Cashout", {"name": "CO-1", "bank_account": "A - NCB"})

	banking.delete_bank_account("A - NCB", PARTY)
	result = banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD")

	assert result["reenabled"] is True
	assert (row(bank, "A - NCB")["disabled"], row(bank, "A - NCB")["removed_by_customer"]) == (0, 0)


def test_marker_is_cleared_when_an_account_is_enabled_from_the_desk(bank):
	"""Otherwise a LATER admin hold on the same doc would look customer-removed."""
	doc = frappe.get_doc(removed("Gone - NCB", number="2"))
	doc.disabled = 0

	banking.clear_removal_marker_when_enabled(doc)

	assert doc.removed_by_customer == 0


def test_marker_survives_a_save_while_still_disabled(bank):
	doc = frappe.get_doc(removed("Gone - NCB", number="2"))

	banking.clear_removal_marker_when_enabled(doc)

	assert doc.removed_by_customer == 1


def test_marker_hook_and_fixture_are_wired():
	import json
	from pathlib import Path

	root = Path(banking.__file__).resolve().parents[1]
	hooks = (root / "hooks.py").read_text()
	assert '"validate": "admin_panel.api.banking.clear_removal_marker_when_enabled"' in hooks
	# The export filter must keep covering the field or a fixture re-export drops it.
	assert '["fieldname", "in", ["currency", "removed_by_customer"]]' in hooks
	fields = json.loads((root / "fixtures" / "custom_field.json").read_text())
	(marker,) = [f for f in fields if f["fieldname"] == banking.REMOVED_BY_CUSTOMER]
	assert (marker["dt"], marker["fieldtype"], marker["read_only"]) == ("Bank Account", "Check", 1)


def test_add_audit_masks_the_account_number(bank):
	banking.add_bank_account(PARTY, "NCB", "1111222233334444", "Savings", "JMD", account_name="Jo")

	(entry,) = audit_entries(bank, "add_bank_account")
	assert "…4444" in entry["content"]
	assert "1111222233334444" not in entry["content"]


def test_readd_audit_masks_the_account_number(bank):
	bank.seed("Bank Account", removed("Gone - NCB", number="1111222233334444"))

	banking.add_bank_account(PARTY, "NCB", "1111222233334444", "Savings", "JMD")

	(entry,) = audit_entries(bank, "add_bank_account")
	assert "…4444" in entry["content"]
	assert "1111222233334444" not in entry["content"]


# ---- number collisions on edit -------------------------------------------------


def test_edit_onto_own_removed_number_says_to_add_it_again(bank):
	bank.seed("Bank Account", account("Live - NCB", number="1"), removed("Gone - NCB", number="111"))

	with pytest.raises(bank.Thrown, match="was removed. Add it again"):
		banking.update_bank_account("Live - NCB", PARTY, "NCB", "111", "Savings", "JMD")

	assert row(bank, "Live - NCB")["bank_account_no"] == "1"


@pytest.mark.parametrize(
	"holder",
	[
		account("Mine - NCB", number="111"),
		account("Held - NCB", number="111", disabled=1),
		account("Theirs - NCB", number="111", party=OTHER_PARTY),
		removed("TheirsGone - NCB", number="111", party=OTHER_PARTY),
	],
	ids=["own-live", "own-admin-disabled", "other-party", "other-party-removed"],
)
def test_edit_onto_any_other_holder_stays_a_generic_collision(bank, holder):
	"""The specific hint is only for the party's OWN customer-removed account;
	anything else must not leak who holds the number or why."""
	bank.seed("Bank Account", account("Live - NCB", number="1"), holder)

	with pytest.raises(bank.Thrown, match="Another bank account already uses"):
		banking.update_bank_account("Live - NCB", PARTY, "NCB", "111", "Savings", "JMD")

	assert row(bank, "Live - NCB")["bank_account_no"] == "1"


def test_edit_keeping_the_same_number_is_not_a_collision(bank):
	bank.seed("Bank Account", account("Live - NCB", number="1"))

	assert banking.update_bank_account("Live - NCB", PARTY, "NCB", "1", "Chequing", "JMD") == {
		"success": True
	}


def _approve(bank, request):
	import sys
	import types

	if "admin_panel.api.admin_api" not in sys.modules:
		for name in ("pymongo", "bson"):
			sys.modules.setdefault(name, types.ModuleType(name))
	from admin_panel.api import admin_api

	return admin_api.approve_bank_account_update_request(request)


def _update_request(name, bank_account, number):
	return {
		"name": name,
		"status": "Pending",
		"party": PARTY,
		"bank_account": bank_account,
		"bank_name": "NCB",
		"bank_branch": "001",
		"account_type": "Savings",
		"account_number": number,
	}


def test_approve_onto_own_removed_number_says_to_add_it_again(bank):
	bank.seed("Bank Account", account("Live - NCB", number="1"), removed("Gone - NCB", number="111"))
	bank.seed("Bank Account Update Request", _update_request("REQ-1", "Live - NCB", "111"))

	result = _approve(bank, "REQ-1")

	assert result == {"success": False, "error": banking.OWN_REMOVED_NUMBER_MESSAGE}
	assert row(bank, "Live - NCB")["bank_account_no"] == "1"
	assert row(bank, "REQ-1", "Bank Account Update Request")["status"] == "Pending"


def test_approve_onto_another_holders_number_stays_generic(bank):
	bank.seed(
		"Bank Account",
		account("Live - NCB", number="1"),
		account("Theirs - NCB", number="111", party=OTHER_PARTY),
	)
	bank.seed("Bank Account Update Request", _update_request("REQ-1", "Live - NCB", "111"))

	assert _approve(bank, "REQ-1") == {"success": False, "error": banking.NUMBER_IN_USE_MESSAGE}


def test_approve_still_patches_a_free_number(bank):
	bank.seed("Bank Account", account("Live - NCB", number="1"))
	bank.seed("Bank Account Update Request", _update_request("REQ-1", "Live - NCB", "222"))

	assert _approve(bank, "REQ-1")["success"] is True
	assert row(bank, "Live - NCB")["bank_account_no"] == "222"


def test_number_held_by_another_party_is_still_a_duplicate(bank):
	"""Even a disabled account under ANOTHER party keeps the number taken."""
	bank.seed("Bank Account", account("Theirs - NCB", number="2", party=OTHER_PARTY, disabled=1))

	with pytest.raises(bank.Thrown, match="already exists"):
		banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD")


def test_live_duplicate_under_the_same_party_is_rejected(bank):
	bank.seed("Bank Account", account("Mine - NCB", number="2"))

	with pytest.raises(bank.Thrown, match="already exists"):
		banking.add_bank_account(PARTY, "NCB", "2", "Savings", "JMD")


def test_first_live_account_becomes_default_despite_removed_ones(bank):
	bank.seed("Bank Account", account("Gone - NCB", number="2", disabled=1))

	result = banking.add_bank_account(PARTY, "NCB", "7", "Savings", "JMD", account_name="Fresh")

	assert row(bank, result["bank_account"])["is_default"] == 1


def test_autoname_survives_repeated_collisions(bank):
	"""Same holder, same bank, numbers sharing their last 4."""
	names = [
		banking.add_bank_account(PARTY, "NCB", number, "Savings", "JMD", account_name="Jo")["bank_account"]
		for number in ("11114444", "22224444", "33334444", "44444444")
	]

	assert names == [
		"Jo - NCB",
		"Jo (…4444) - NCB",
		"Jo (…4444) 2 - NCB",
		"Jo (…4444) 3 - NCB",
	]
	assert len({r["name"] for r in bank.rows("Bank Account")}) == 4


# ---- wiring -------------------------------------------------------------------


def test_delete_endpoint_is_whitelisted_and_admin_gated():
	source = (banking.__file__ and open(banking.__file__).read()) or ""
	stack = "@frappe.whitelist()\n@require_admin()\n@handle_api_errors\ndef delete_bank_account("
	assert stack in source


def test_delete_requires_an_admin_role(bank, monkeypatch):
	bank.seed("Bank Account", account("A - NCB"))
	monkeypatch.setattr(frappe, "get_roles", lambda user=None: ["Customer"], raising=False)

	with pytest.raises(frappe.PermissionError):
		banking.delete_bank_account("A - NCB", PARTY)

	assert row(bank, "A - NCB") is not None
