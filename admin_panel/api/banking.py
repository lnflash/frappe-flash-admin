"""Customer banking overview for the Account Hub "Banking" tab.

One endpoint, two sources:
  * ERPNext Bank Account records — the cashout rails, looked up exactly the
    way Cashout.validate does (party_type="Customer", party=erpParty).
  * Bridge — the US virtual account (full deposit instructions) and any
    linked external accounts, via the account's bridgeCustomerId in mongo.

Partial-tolerant on purpose (the Account Hub lesson): a Bridge or mongo
failure is reported inside the payload instead of failing the whole call, so
ERP bank accounts still render when the other side is down or unconfigured.
"""

import frappe
from frappe.utils import cstr

from .auth import audit_log, require_admin
from .banking_core import slim_external_account, slim_virtual_account
from .bridge_client import CUSTOMER_ID_RE, BridgeApiError, BridgeClient
from .common import handle_api_errors
from .mongo_reader import find_account

# Check custom field on Bank Account (fixtures/custom_field.json). `disabled` is
# ERPNext's generic flag and support also sets it from the desk (fraud hold,
# ownership dispute); this marker is what says "the CUSTOMER removed this one".
# Only marked accounts may be revived by self-serve.
REMOVED_BY_CUSTOMER = "removed_by_customer"
OWN_REMOVED_NUMBER_MESSAGE = (
	"This account number belongs to a bank account that was removed. "
	"Add it again instead of editing another account."
)
NUMBER_IN_USE_MESSAGE = "Another bank account already uses this account number."


def _erp_bank_accounts(erp_party, include_disabled=False):
	# A disabled account (removed by the customer, or held by an admin) no longer
	# exists as far as the customer is concerned, so the default read hides it.
	# Support still has to see it — Cashout history points at it — so the Account
	# Hub asks for include_disabled and gets the removal marker alongside.
	filters = {"party_type": "Customer", "party": erp_party}
	fields = [
		"name",
		"account_name",
		"bank",
		"bank_account_no",
		"branch_code",
		"account_type",
		"currency",
		"is_default",
		"disabled",
	]
	if include_disabled:
		fields.append(REMOVED_BY_CUSTOMER)
	else:
		filters["disabled"] = 0
	return frappe.get_all(
		"Bank Account",
		filters=filters,
		fields=fields,
		order_by="is_default desc, creation asc",
	)


def _bridge_banking(account_ref):
	"""Bridge side of the payload. Never raises — errors are reported in-band."""
	try:
		account = find_account(account_ref)
	except Exception as e:  # mongo unconfigured/unreachable — degrade, don't fail the tab
		return {"linked": False, "error": f"mongo lookup failed: {e}"}
	if not account or not account.get("bridgeCustomerId"):
		return {"linked": False}

	customer_id = str(account["bridgeCustomerId"])
	if not CUSTOMER_ID_RE.fullmatch(customer_id):
		return {"linked": True, "customer_id": customer_id, "error": "stored bridgeCustomerId is not a UUID"}

	try:
		client = BridgeClient()
		return {
			"linked": True,
			"customer_id": customer_id,
			"kyc_status": account.get("bridgeKycStatus"),
			"virtual_accounts": [slim_virtual_account(v) for v in client.list_virtual_accounts(customer_id)],
			"external_accounts": [
				slim_external_account(e) for e in client.list_external_accounts(customer_id)
			],
		}
	except (BridgeApiError, ValueError) as e:
		return {"linked": True, "customer_id": customer_id, "error": str(e)}


@frappe.whitelist()
@require_admin()
@handle_api_errors
def get_customer_banking(erp_party=None, account_ref=None, include_disabled=0):
	"""Full banking picture for one customer: ERP cashout accounts + Bridge.

	include_disabled=1 is for support surfaces (the Account Hub); customer-facing
	callers leave it off and never see removed or held accounts.
	"""
	from frappe.utils import cint

	erp_party = cstr(erp_party).strip()
	account_ref = cstr(account_ref).strip()
	if not erp_party and not account_ref:
		frappe.throw("erp_party or account_ref is required")

	return {
		"success": True,
		"erp_party": erp_party or None,
		"bank_accounts": _erp_bank_accounts(erp_party, bool(cint(include_disabled))) if erp_party else [],
		"bridge": _bridge_banking(account_ref) if account_ref else {"linked": False},
	}


# ---- Admin write endpoints (Banking tab) -----------------------------------
#
# flash's cashout GraphQL exposes bank accounts with NonNull bank / branch /
# account-number / type / currency fields — a single null-ish value can blank
# the customer's ENTIRE bankAccounts list in the app, and cashout validation
# only accepts JMD or USD. Everything is enforced here so an admin edit can
# never break a customer's cashout. Multiple accounts per customer are fully
# supported by the app (cashout takes an explicit bankAccountId).

ALLOWED_CURRENCIES = ("JMD", "USD")
ALLOWED_ACCOUNT_TYPES = ("Chequing", "Savings")


def _validate_bank_fields(bank_name, account_number, account_type, currency):
	bank_name = cstr(bank_name).strip()
	account_number = cstr(account_number).strip()
	account_type = cstr(account_type).strip()
	currency = cstr(currency).strip().upper()
	if not bank_name:
		frappe.throw("bank_name is required")
	if not account_number:
		frappe.throw("account_number is required")
	if account_type not in ALLOWED_ACCOUNT_TYPES:
		frappe.throw("account_type must be one of: " + ", ".join(ALLOWED_ACCOUNT_TYPES))
	if currency not in ALLOWED_CURRENCIES:
		frappe.throw("currency must be JMD or USD — cashout accepts nothing else")
	return bank_name, account_number, account_type, currency


def _ensure_bank_master(bank_name):
	"""Mirror of _create_erp_records: the Bank master must exist before linking."""
	if not frappe.db.exists("Bank", bank_name):
		frappe.get_doc({"doctype": "Bank", "bank_name": bank_name}).insert(ignore_permissions=True)


def _owned_bank_account(bank_account_id, erp_party, for_update=False):
	"""Load a Bank Account and verify ownership (mirror of Cashout.validate and
	the ENG-509 approve flow) — party_type Customer + party must match."""
	bank_account = frappe.get_doc("Bank Account", cstr(bank_account_id).strip(), for_update=for_update)
	if bank_account.party_type != "Customer" or bank_account.party != erp_party:
		frappe.throw("Bank Account does not belong to this customer.")
	if bank_account.is_company_account:
		frappe.throw("Bank Account does not belong to this customer.")
	if bank_account.disabled:
		# Soft-deleted (see delete_bank_account): same answer as a missing doc.
		frappe.throw("Bank Account not found.", frappe.DoesNotExistError)
	return bank_account


def _enabled_bank_account_names(erp_party, exclude=None):
	filters = {"party_type": "Customer", "party": erp_party, "disabled": 0}
	if exclude:
		filters["name"] = ("!=", exclude)
	return frappe.get_all("Bank Account", filters=filters, pluck="name")


def _mask_account_number(account_number):
	"""Audit entries for customer-initiated writes (add, re-add, removal) carry
	the last 4 only."""
	account_number = cstr(account_number)
	return f"…{account_number[-4:]}" if account_number else ""


def _removed_account_to_revive(erp_party, account_number):
	"""A customer re-adding an account they removed earlier: the soft-deleted
	doc still holds the number, so it is re-enabled instead of rejected as a
	duplicate. Only when this party's customer-removed doc is the sole holder of
	the number — any other match is a genuine duplicate. An account support
	disabled from the desk carries no removal marker and is never revived here:
	self-serve must not undo an admin hold."""
	name = frappe.db.get_value(
		"Bank Account",
		{
			"party_type": "Customer",
			"party": erp_party,
			"bank_account_no": account_number,
			"disabled": 1,
			REMOVED_BY_CUSTOMER: 1,
		},
		"name",
	)
	if not name:
		return None
	if frappe.db.exists("Bank Account", {"bank_account_no": account_number, "name": ("!=", name)}):
		return None
	return name


def number_collision_message(erp_party, account_number, bank_account_name):
	"""Why `account_number` cannot be moved onto `bank_account_name`, or None.

	Shared by update_bank_account and the ENG-509 approve flow. A collision with
	the party's own customer-removed account gets its own message: that doc is
	hidden from the customer, so the generic one is a dead end for everybody.
	"""
	others = frappe.get_all(
		"Bank Account",
		filters={"bank_account_no": account_number, "name": ("!=", bank_account_name)},
		fields=["name", "party_type", "party", "disabled", REMOVED_BY_CUSTOMER],
	)
	if not others:
		return None
	if all(
		row.party_type == "Customer"
		and row.party == erp_party
		and row.disabled
		and row.get(REMOVED_BY_CUSTOMER)
		for row in others
	):
		return OWN_REMOVED_NUMBER_MESSAGE
	return NUMBER_IN_USE_MESSAGE


def clear_removal_marker_when_enabled(doc, method=None):
	"""Bank Account validate hook (hooks.py doc_events). The marker only means
	something while the account is disabled; once anyone re-enables it (desk or
	re-add) it is cleared, so a LATER admin hold cannot be mistaken for a
	customer removal and revived through self-serve."""
	if not doc.get("disabled") and doc.get(REMOVED_BY_CUSTOMER):
		doc.set(REMOVED_BY_CUSTOMER, 0)


@frappe.whitelist()
@require_admin()
@handle_api_errors
def add_bank_account(
	erp_party,
	bank_name,
	account_number,
	account_type,
	currency,
	bank_branch=None,
	account_name=None,
	set_default=0,
):
	"""Create an additional cashout bank account for a customer.

	The first account for a customer becomes the default automatically.
	"""
	from frappe.utils import cint

	erp_party = cstr(erp_party).strip()
	if not erp_party or not frappe.db.exists("Customer", erp_party):
		frappe.throw("Unknown ERP customer — the account needs an ERP party first.")
	bank_name, account_number, account_type, currency = _validate_bank_fields(
		bank_name, account_number, account_type, currency
	)
	revive = _removed_account_to_revive(erp_party, account_number)
	if not revive and frappe.db.exists("Bank Account", {"bank_account_no": account_number}):
		frappe.throw("A bank account with this account number already exists.")

	_ensure_bank_master(bank_name)
	existing = _enabled_bank_account_names(erp_party)
	make_default = 1 if (cint(set_default) or not existing) else 0

	if revive:
		# The doc name (the app's bankAccountId) is kept; details are refreshed
		# from this request since the customer may have retyped them.
		doc = frappe.get_doc("Bank Account", revive, for_update=True)
		doc.bank = bank_name
		doc.branch_code = cstr(bank_branch).strip()
		doc.account_type = account_type
		doc.currency = currency
		if cstr(account_name).strip():
			doc.account_name = cstr(account_name).strip()
		doc.disabled = 0
		doc.set(REMOVED_BY_CUSTOMER, 0)
		doc.is_default = make_default
		doc.save(ignore_permissions=True)
		if make_default:
			for name in existing:
				frappe.db.set_value("Bank Account", name, "is_default", 0)
		frappe.db.commit()

		audit_log(
			"add_bank_account",
			"Bank Account",
			doc.name,
			{
				"party": erp_party,
				"bank": bank_name,
				"bank_account_no": _mask_account_number(account_number),
				"currency": currency,
				"is_default": make_default,
				"reenabled": 1,
			},
		)
		return {"success": True, "bank_account": doc.name, "reenabled": True}

	# ERPNext autonames Bank Accounts "{account_name} - {bank}", and the doc
	# name is load-bearing (it is the app's bankAccountId). Disambiguate the
	# holder with the account number's last 4 so a second account at the same
	# bank can exist; existing docs keep their names. Two numbers can share
	# their last 4, so keep counting until the name is free.
	holder = cstr(account_name).strip() or erp_party
	if frappe.db.exists("Bank Account", f"{holder} - {bank_name}"):
		holder = f"{holder} (…{account_number[-4:]})"
		base, suffix = holder, 2
		while frappe.db.exists("Bank Account", f"{holder} - {bank_name}"):
			holder = f"{base} {suffix}"
			suffix += 1

	doc = frappe.get_doc(
		{
			"doctype": "Bank Account",
			"account_name": holder,
			"bank": bank_name,
			"bank_account_no": account_number,
			"branch_code": cstr(bank_branch).strip(),
			"account_type": account_type,
			"currency": currency,
			"is_company_account": 0,
			"is_default": make_default,
			"party_type": "Customer",
			"party": erp_party,
		}
	)
	doc.insert(ignore_permissions=True)
	if make_default:
		for name in existing:
			frappe.db.set_value("Bank Account", name, "is_default", 0)
	frappe.db.commit()

	audit_log(
		"add_bank_account",
		"Bank Account",
		doc.name,
		{
			"party": erp_party,
			"bank": bank_name,
			"bank_account_no": _mask_account_number(account_number),
			"currency": currency,
			"is_default": make_default,
		},
	)
	return {"success": True, "bank_account": doc.name, "reenabled": False}


@frappe.whitelist()
@require_admin()
@handle_api_errors
def update_bank_account(
	bank_account_id,
	erp_party,
	bank_name,
	account_number,
	account_type,
	currency,
	bank_branch=None,
	account_name=None,
):
	"""Patch a customer's bank account in place (admin-initiated edit).

	Unlike the ENG-509 approve flow (which locks currency), a valid currency is
	required on every save — deliberately, so support can also HEAL records
	whose empty currency blanks the app's bankAccounts list.
	`name` and `is_default` are intentionally left untouched.
	"""
	erp_party = cstr(erp_party).strip()
	bank_name, account_number, account_type, currency = _validate_bank_fields(
		bank_name, account_number, account_type, currency
	)
	# The doc name stays as-is even when the bank changes — it is the app's
	# bankAccountId, and changing it would strand mobile references.
	bank_account = _owned_bank_account(bank_account_id, erp_party, for_update=True)

	collision = number_collision_message(erp_party, account_number, bank_account.name)
	if collision:
		frappe.throw(collision)

	_ensure_bank_master(bank_name)
	old_values = {
		"bank": bank_account.bank,
		"branch_code": bank_account.branch_code,
		"account_type": bank_account.account_type,
		"bank_account_no": bank_account.bank_account_no,
		"currency": bank_account.currency,
	}
	bank_account.bank = bank_name
	bank_account.branch_code = cstr(bank_branch).strip()
	bank_account.account_type = account_type
	bank_account.bank_account_no = account_number
	bank_account.currency = currency
	if cstr(account_name).strip():
		bank_account.account_name = cstr(account_name).strip()
	bank_account.save(ignore_permissions=True)
	frappe.db.commit()

	audit_log(
		"update_bank_account",
		"Bank Account",
		bank_account.name,
		{
			"party": erp_party,
			"old": old_values,
			"new": {
				"bank": bank_name,
				"branch_code": cstr(bank_branch).strip(),
				"account_type": account_type,
				"bank_account_no": account_number,
				"currency": currency,
			},
		},
	)
	return {"success": True}


@frappe.whitelist()
@require_admin()
@handle_api_errors
def set_default_bank_account(bank_account_id, erp_party):
	"""Make one of the customer's bank accounts the default (clears the rest)."""
	erp_party = cstr(erp_party).strip()
	bank_account = _owned_bank_account(bank_account_id, erp_party)
	for name in _enabled_bank_account_names(erp_party, exclude=bank_account.name):
		frappe.db.set_value("Bank Account", name, "is_default", 0)
	frappe.db.set_value("Bank Account", bank_account.name, "is_default", 1)
	frappe.db.commit()

	audit_log("set_default_bank_account", "Bank Account", bank_account.name, {"party": erp_party})
	return {"success": True}


def _elect_new_default(erp_party, removed_name, currency):
	"""Most recently modified remaining account, same currency first."""
	remaining = frappe.get_all(
		"Bank Account",
		filters={
			"party_type": "Customer",
			"party": erp_party,
			"disabled": 0,
			"name": ("!=", removed_name),
		},
		fields=["name", "currency"],
		order_by="modified desc",
	)
	if not remaining:
		return None
	same_currency = [row for row in remaining if row.currency == currency]
	new_default = (same_currency or remaining)[0].name
	frappe.db.set_value("Bank Account", new_default, "is_default", 1)
	return new_default


@frappe.whitelist()
@require_admin()
@handle_api_errors
def delete_bank_account(bank_account_id, erp_party):
	"""Remove one of the customer's bank accounts (customer self-serve).

	Hard delete when nothing references the record; otherwise (Cashouts,
	Payment Entries, past update requests) it is disabled and marked
	removed_by_customer, which hides it from every customer-facing read and write
	in this module; Cashout.validate refuses new cashouts to it.
	"""
	erp_party = cstr(erp_party).strip()
	bank_account = _owned_bank_account(bank_account_id, erp_party, for_update=True)
	name = bank_account.name
	was_default = bool(bank_account.is_default)

	# A pending edit for an account the customer just removed must not be
	# approvable later (same supersede rule as the ENG-509 approve flow).
	pending = frappe.get_all(
		"Bank Account Update Request",
		filters={"bank_account": name, "status": "Pending"},
		pluck="name",
	)
	for request in pending:
		frappe.db.set_value("Bank Account Update Request", request, "status", "Closed")

	# delete_doc runs on_trash hooks before its link check, so a refused delete
	# is rolled back to the savepoint rather than trusted to be side-effect free.
	frappe.db.savepoint("delete_bank_account")
	try:
		frappe.delete_doc("Bank Account", name, ignore_permissions=True)
		deleted = True
	except frappe.LinkExistsError:
		frappe.db.rollback(save_point="delete_bank_account")
		frappe.db.set_value("Bank Account", name, "disabled", 1)
		frappe.db.set_value("Bank Account", name, REMOVED_BY_CUSTOMER, 1)
		frappe.db.set_value("Bank Account", name, "is_default", 0)
		deleted = False

	new_default = _elect_new_default(erp_party, name, bank_account.currency) if was_default else None
	frappe.db.commit()

	# A hard-deleted doc cannot anchor a Comment, so that entry goes on the Customer.
	audit_log(
		"delete_bank_account",
		"Bank Account" if not deleted else "Customer",
		name if not deleted else erp_party,
		{
			"party": erp_party,
			"bank_account": name,
			"bank": bank_account.bank,
			"bank_account_no": _mask_account_number(bank_account.bank_account_no),
			"deleted": deleted,
			"disabled": not deleted,
			"closed_requests": pending,
			"new_default": new_default,
		},
	)
	return {
		"success": True,
		"bank_account_id": name,
		"deleted": deleted,
		"disabled": not deleted,
		"new_default": new_default,
	}
