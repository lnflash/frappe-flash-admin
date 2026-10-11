"""Contract + controller tests for the Referral Payout Allowlist doctype (ENG-640).

flash reads this doctype to pay referral rewards to chosen accounts while its
global ``referralReward.enabled`` flag stays off. flash matches rows on
``account_id``, which is the account's Mongo ``_id`` string, NOT the account
uuid: an allowlist keyed on the wrong identifier would save cleanly and never
match, silently deferring every listed account. Runs under plain ``pytest``
with no Frappe runtime, matching the existing contract-test style.
"""

import importlib
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_PANEL = REPO_ROOT / "admin_panel"
ALLOWLIST_DIR = ADMIN_PANEL / "admin_panel" / "doctype" / "referral_payout_allowlist"

# The exact fieldnames the flash reader selects — keep in sync with the
# referral payout allowlist reader in the flash repo (ENG-640).
FLASH_CONTRACT_FIELDS = (
	"account_id",
	"enabled",
)


def load_doctype():
	return json.loads((ALLOWLIST_DIR / "referral_payout_allowlist.json").read_text())


def fields_by_name():
	return {f["fieldname"]: f for f in load_doctype()["fields"]}


# ---------------------------------------------------------------------------
# Static contract
# ---------------------------------------------------------------------------


def test_doctype_defines_every_flash_contract_field():
	doctype = load_doctype()
	fields = fields_by_name()

	# The reader addresses the resource by this name; renaming it is as silent
	# as a fieldname drift.
	assert doctype["name"] == "Referral Payout Allowlist"
	assert doctype["module"] == "Admin Panel"
	for fieldname in FLASH_CONTRACT_FIELDS:
		assert fieldname in fields, f"{fieldname} missing from Referral Payout Allowlist"
		assert fieldname in doctype["field_order"]
	assert fields["enabled"]["fieldtype"] == "Check"
	assert fields["account_id"]["fieldtype"] == "Data"


def test_account_id_is_unique_read_only_and_the_document_name():
	doctype = load_doctype()
	fields = fields_by_name()

	assert fields["account_id"]["unique"] == 1
	# Set by the controller from flash, never typed by an operator.
	assert fields["account_id"]["read_only"] == 1
	# Naming by account_id makes one row per account a primary-key fact.
	assert doctype["autoname"] == "field:account_id"
	assert doctype["naming_rule"] == "By fieldname"
	assert doctype["allow_rename"] == 0


def test_resolved_display_fields_are_read_only():
	fields = fields_by_name()

	for fieldname in ("username", "account_uuid"):
		assert fields[fieldname]["read_only"] == 1, fieldname


def test_operator_input_is_required_and_set_only_once():
	fields = fields_by_name()

	assert fields["account"]["reqd"] == 1
	assert fields["account"]["set_only_once"] == 1
	# accountDetailsByAccountId resolves by uuid on the flash side, so the
	# operator is told "account UUID", never "account ID".
	assert "UUID" in fields["account"]["label"]


def test_enabled_defaults_on():
	assert fields_by_name()["enabled"]["default"] == "1"


def test_track_changes_is_on():
	# Who allowlisted whom, and who turned it off, must survive.
	assert load_doctype()["track_changes"] == 1


def test_permissions_include_system_manager_and_accounts_manager():
	perms = {p["role"]: p for p in load_doctype()["permissions"]}

	for role in ("System Manager", "Accounts Manager"):
		for right in ("read", "write", "create", "delete", "report"):
			assert perms[role].get(right) == 1, f"{role} lacks {right}"


def test_referral_settings_points_operators_at_the_allowlist():
	settings = json.loads(
		(ADMIN_PANEL / "admin_panel" / "doctype" / "referral_settings" / "referral_settings.json").read_text()
	)
	description = {f["fieldname"]: f for f in settings["fields"]}["rewards_enabled"]["description"]

	assert "Referral Payout Allowlist" in description
	assert "Unchecking it stops every payout, allowlisted or not." in description


# ---------------------------------------------------------------------------
# Controller behaviour. Same frappe stub approach as
# test_fee_discount_contract.py: import-time gaps are filled hasattr-guarded,
# call-time surfaces are monkeypatched per test.
# ---------------------------------------------------------------------------


def _ensure_module(name):
	try:
		__import__(name)
	except ImportError:
		sys.modules.setdefault(name, types.ModuleType(name))
	return sys.modules[name]


class _ValidationError(Exception):
	pass


def _throw(msg, *args, **kwargs):
	raise _ValidationError(msg)


_frappe = _ensure_module("frappe")
_frappe_model = _ensure_module("frappe.model")
_frappe_document = _ensure_module("frappe.model.document")
if not hasattr(_frappe_document, "Document"):

	class _Document:  # stand-in for frappe.model.document.Document
		pass

	_frappe_document.Document = _Document
if not hasattr(_frappe_model, "document"):
	_frappe_model.document = _frappe_document


@pytest.fixture(autouse=True)
def frappe_runtime(monkeypatch):
	logged = []
	monkeypatch.setattr(_frappe, "throw", _throw, raising=False)
	monkeypatch.setattr(_frappe, "log_error", lambda *a, **k: logged.append(k), raising=False)
	monkeypatch.setattr(_frappe, "get_traceback", lambda *a, **k: "", raising=False)
	return types.SimpleNamespace(logged=logged)


@pytest.fixture()
def flash(monkeypatch):
	"""Stub the lazy GraphQLClient import with scriptable account lookups.

	``by_username`` / ``by_id`` map the lookup argument to the account dict
	flash would return (missing key → None, i.e. not found). ``error`` makes
	every lookup raise (flash down); ``init_error`` models a missing
	flash_admin_api_url / admin_api_key, which GraphQLClient.__init__ raises
	before any lookup.
	"""
	state = types.SimpleNamespace(by_username={}, by_id={}, error=None, init_error=None, lookups=[])

	class _StubGraphQLClient:
		def __init__(self):
			if state.init_error is not None:
				raise state.init_error

		def get_account_by_username(self, username):
			state.lookups.append(("username", username))
			if state.error is not None:
				raise state.error
			return state.by_username.get(username)

		def get_account_by_id(self, account_id):
			state.lookups.append(("id", account_id))
			if state.error is not None:
				raise state.error
			return state.by_id.get(account_id)

	stub = types.ModuleType("admin_panel.api.graphql_client")
	stub.GraphQLClient = _StubGraphQLClient
	monkeypatch.setitem(sys.modules, "admin_panel.api.graphql_client", stub)
	return state


MONGO_ID = "65f1c2a9e4b0a1b2c3d4e5f6"
ACCOUNT_UUID = "3f2a1b4c-5d6e-4f70-8a9b-0c1d2e3f4a5b"
ALICE = {"id": MONGO_ID, "uuid": ACCOUNT_UUID, "username": "alice"}


def _make_doc(**attrs):
	module = importlib.import_module(
		"admin_panel.admin_panel.doctype.referral_payout_allowlist.referral_payout_allowlist"
	)
	doc = module.ReferralPayoutAllowlist.__new__(module.ReferralPayoutAllowlist)
	doc.is_new = lambda: True
	doc.has_value_changed = lambda fieldname: False
	defaults = {
		"doctype": "Referral Payout Allowlist",
		"account": "alice",
		"enabled": 1,
		"note": None,
		"account_id": None,
		"username": None,
		"account_uuid": None,
	}
	defaults.update(attrs)
	for key, value in defaults.items():
		setattr(doc, key, value)
	return doc


def _unresolved(doc):
	return doc.account_id is None and doc.username is None and doc.account_uuid is None


def test_username_resolves_to_mongo_id_not_uuid(flash):
	# The bug this guards against: keying on the uuid, which flash never
	# matches. The stub returns distinct id and uuid; account_id must be the id.
	flash.by_username["alice"] = ALICE
	doc = _make_doc(account="  alice  ")

	doc.before_insert()

	assert doc.account_id == MONGO_ID
	assert doc.account_id != ACCOUNT_UUID
	assert doc.account_uuid == ACCOUNT_UUID
	assert doc.username == "alice"
	assert doc.account == "alice"
	assert flash.lookups == [("username", "alice")]


def test_non_username_input_goes_straight_to_the_uuid_lookup(flash):
	flash.by_id[ACCOUNT_UUID] = ALICE
	doc = _make_doc(account=ACCOUNT_UUID)

	doc.before_insert()

	# A uuid (hyphens) is not username-shaped: no username lookup is spent.
	assert flash.lookups == [("id", ACCOUNT_UUID)]
	assert doc.account_id == MONGO_ID


def test_username_shaped_miss_falls_back_to_the_uuid_lookup(flash):
	# A hyphen-free uuid is username-shaped; when the username lookup misses,
	# the by-id lookup gets a turn (same dispatch as the admin account search).
	flat_uuid = "af2a1b4c5d6e4f708a9b0c1d2e3f4a5b"
	flash.by_id[flat_uuid] = ALICE
	doc = _make_doc(account=flat_uuid)

	doc.before_insert()

	assert flash.lookups == [("username", flat_uuid), ("id", flat_uuid)]
	assert doc.account_id == MONGO_ID


def test_unknown_account_is_refused(flash):
	doc = _make_doc(account="nobody_here")

	with pytest.raises(_ValidationError, match="No flash account matches 'nobody_here'"):
		doc.before_insert()

	assert flash.lookups == [("username", "nobody_here"), ("id", "nobody_here")]
	assert _unresolved(doc)


def test_flash_outage_refuses_the_save_and_sets_nothing(flash, frappe_runtime):
	flash.error = RuntimeError("connection refused")
	doc = _make_doc(account="alice")

	with pytest.raises(_ValidationError, match="Could not verify against flash; nothing was saved"):
		doc.before_insert()

	assert _unresolved(doc)
	assert len(frappe_runtime.logged) == 1


def test_missing_flash_config_refuses_the_save(flash, frappe_runtime):
	flash.init_error = ValueError("admin_api_key is not configured in site_config.json")
	doc = _make_doc(account="alice")

	with pytest.raises(_ValidationError, match="Could not verify against flash"):
		doc.before_insert()

	assert flash.lookups == []
	assert _unresolved(doc)
	assert len(frappe_runtime.logged) == 1


def test_response_without_id_is_refused(flash):
	flash.by_username["alice"] = {"uuid": ACCOUNT_UUID, "username": "alice"}
	doc = _make_doc(account="alice")

	with pytest.raises(_ValidationError, match="without an account ID"):
		doc.before_insert()

	assert _unresolved(doc)


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_blank_input_is_refused_without_a_lookup(flash, blank):
	doc = _make_doc(account=blank)

	with pytest.raises(_ValidationError, match="required"):
		doc.before_insert()

	assert flash.lookups == []


def test_saved_row_identity_edit_is_refused(flash):
	doc = _make_doc(account="bob", account_id=MONGO_ID)
	doc.is_new = lambda: False
	doc.has_value_changed = lambda fieldname: fieldname == "account"

	with pytest.raises(_ValidationError, match="Identity cannot be edited"):
		doc.validate()

	assert flash.lookups == []


def test_saved_row_toggling_enabled_never_calls_flash(flash):
	# The per-account kill path must work during a flash outage.
	flash.error = RuntimeError("flash is down")
	flash.init_error = ValueError("not configured")
	doc = _make_doc(account="alice", account_id=MONGO_ID, enabled=0, note="paused")
	doc.is_new = lambda: False
	doc.has_value_changed = lambda fieldname: fieldname in ("enabled", "note")

	doc.validate()

	assert flash.lookups == []
	assert doc.account_id == MONGO_ID
