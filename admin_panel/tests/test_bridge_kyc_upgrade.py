"""Bridge KYC → Level 2 auto-upgrade.

The eligibility rules (bridge_kyc_upgrade_core) are tested pure. The job is
tested against FakeFrappe with the REAL approve_upgrade_request, its flash /
ERP-record / ledger side effects stubbed the same way as
test_admin_api_id_verification, so these tests prove the upgrade goes through
the normal approval rather than around it.
"""

import json
import logging
import types
from datetime import timedelta
from pathlib import Path

import pytest
from idv_stubs import frappe

from admin_panel.api import admin_api, bridge_kyc_upgrade
from admin_panel.api import bridge_kyc_upgrade_core as core

SETTINGS = "ID Verification Settings"


def customer(cid="cus-1", status="active", type_="individual", first="William", last="Creech", email=None):
	return {
		"id": cid,
		"status": status,
		"type": type_,
		"first_name": first,
		"last_name": last,
		"email": email if email is not None else f"{cid}@example.com",
		"updated_at": "2026-10-01T00:00:00Z",
		"endorsements": [{"name": "base", "status": "approved"}],
		"residential_address": {"street_line_1": "1 Main St"},
	}


def row(
	username="creech147",
	cid="cus-1",
	level=1,
	status="active",
	created_at="2026-08-08T00:00:00",
	phone="+16065550123",
	lookup="US",
):
	return {
		"bridge_customer_id": cid,
		"bridge_kyc_status": "approved",
		"username": username,
		"level": level,
		"status": status,
		"created_at": created_at,
		"phone": phone,
		"phone_lookup_country": lookup,
	}


def live(username="creech147", level="ONE", status="ACTIVE", phone="+16065550123", email="flash@example.com"):
	return {
		"id": f"acct-{username}",
		"username": username,
		"level": level,
		"status": status,
		"owner": {"phone": phone, "email": {"address": email, "verified": True}},
	}


# Flash markets for these tests (the "Allowed Country" flash_allowed set).
ALLOWED = {"US", "JM"}


def select(accounts, customers, pending_usernames=(), recently_failed=(), allowed=ALLOWED):
	return core.select_candidates(
		accounts, customers, pending_usernames, recently_failed, allowed_countries=allowed
	)


def usernames(items):
	return [c["account"]["username"] for c in items]


def reasons(skipped):
	return {s["username"]: s["reason"] for s in skipped}


# ── select_candidates ───────────────────────────────────────────────────


def test_level_zero_and_one_accounts_of_approved_individuals_are_candidates_oldest_first():
	accounts = [
		row("newer", "cus-1", level=1, created_at="2026-09-01T00:00:00"),
		row("older", "cus-2", level=0, created_at="2026-07-01T00:00:00"),
	]
	candidates, skipped = select(accounts, [customer("cus-1"), customer("cus-2")], pending_usernames=[])
	assert usernames(candidates) == ["older", "newer"]
	assert candidates[0]["customer"]["id"] == "cus-2"
	assert skipped == []


def test_a_missing_level_counts_as_level_zero():
	candidates, _ = select([row(level=None)], [customer()], [])
	assert usernames(candidates) == ["creech147"]


@pytest.mark.parametrize("level", [2, 3])
def test_level_two_and_up_are_left_out_silently(level):
	assert select([row(level=level)], [customer()], []) == ([], [])


@pytest.mark.parametrize(
	"status", ["not_started", "incomplete", "under_review", "paused", "rejected", "offboarded"]
)
def test_customers_that_have_not_passed_kyc_are_left_out_silently(status):
	assert select([row()], [customer(status=status)], []) == ([], [])


def test_bridge_is_the_source_of_truth_not_the_stored_status():
	stale = {**row(), "bridge_kyc_status": "under_review"}
	candidates, _ = select([stale], [customer()], [])
	assert usernames(candidates) == ["creech147"]


@pytest.mark.parametrize(
	"accounts,customers,pending,expected",
	[
		([row()], [], [], core.SKIP_MISSING_AT_BRIDGE),
		([row()], [customer(type_="business")], [], core.SKIP_BUSINESS),
		([row(status="locked")], [customer()], [], core.SKIP_NOT_ACTIVE),
		([row(status="closed")], [customer()], [], core.SKIP_NOT_ACTIVE),
		([row(username=None)], [customer()], [], core.SKIP_NO_USERNAME),
		([row()], [customer()], ["creech147"], core.SKIP_PENDING_REQUEST),
	],
)
def test_reported_skips(accounts, customers, pending, expected):
	candidates, skipped = select(accounts, customers, pending)
	assert candidates == []
	assert [s["reason"] for s in skipped] == [expected]
	assert skipped[0]["bridge_customer_id"] == "cus-1"


def test_recently_failed_accounts_wait_out_the_retry_window():
	candidates, skipped = select([row()], [customer()], [], recently_failed={"creech147"})
	assert candidates == []
	assert reasons(skipped) == {"creech147": core.SKIP_RECENT_FAILURE}


def test_an_account_without_a_status_history_is_still_a_candidate():
	candidates, _ = select([row(status=None)], [customer()], [])
	assert usernames(candidates) == ["creech147"]


def test_a_customer_linked_to_several_accounts_upgrades_none_of_them():
	accounts = [row("a", "cus-1"), row("b", "cus-1"), row("c", "cus-2")]
	candidates, skipped = select(accounts, [customer("cus-1"), customer("cus-2")], [])
	assert usernames(candidates) == ["c"]
	assert reasons(skipped) == {"a": core.SKIP_SHARED_CUSTOMER, "b": core.SKIP_SHARED_CUSTOMER}


def test_a_shared_customer_still_blocks_when_the_other_account_is_already_level_two():
	accounts = [row("a", "cus-1", level=2), row("b", "cus-1", level=1)]
	candidates, skipped = select(accounts, [customer("cus-1")], [])
	assert candidates == []
	assert reasons(skipped) == {"b": core.SKIP_SHARED_CUSTOMER}


# ── country rule (the same as flash's Bridge KYC gate) ──────────────────


@pytest.mark.parametrize(
	"phone,lookup,expected",
	[
		("+18764250250", None, ["JM"]),
		("+919876543210", None, ["IN"]),
		("+18764250250", "JM", ["JM"]),
		# A stale signup stamp: Jamaican SIM at signup, Nigerian number now.
		("+2348031234567", "JM", ["NG"]),
		# The stamp stands when the number cannot be resolved.
		("not a number", "US", ["US"]),
		(None, "JM", ["JM"]),
		(None, None, []),
		# Non-geographic: no country at all.
		("+80012345678", None, []),
	],
)
def test_phone_countries_mirror_the_kyc_gate(phone, lookup, expected):
	assert core.phone_countries(phone, lookup) == expected


def test_an_unattributable_number_counts_every_region_on_its_calling_code():
	countries = core.phone_countries("+15550100")
	assert "US" in countries and "JM" in countries
	# Any allowed candidate passes, as at the gate.
	assert core.country_allowed(countries, {"JM"})


def test_accounts_outside_flash_markets_are_skipped_with_their_country():
	accounts = [row("ravi", "cus-1", phone="+919876543210", lookup="IN"), row("ok", "cus-2")]
	candidates, skipped = select(accounts, [customer("cus-1"), customer("cus-2")])
	assert usernames(candidates) == ["ok"]
	assert skipped == [
		{
			"username": "ravi",
			"bridge_customer_id": "cus-1",
			"reason": core.SKIP_COUNTRY_NOT_ALLOWED,
			"country": "IN",
		}
	]


def test_the_number_overrules_a_stale_signup_stamp():
	candidates, skipped = select([row(phone="+2348031234567", lookup="JM")], [customer()])
	assert candidates == []
	assert skipped[0]["reason"] == core.SKIP_COUNTRY_NOT_ALLOWED and skipped[0]["country"] == "NG"


def test_an_account_with_no_resolvable_phone_country_is_skipped():
	candidates, skipped = select([row(phone=None, lookup=None)], [customer()])
	assert candidates == []
	assert skipped[0]["reason"] == core.SKIP_PHONE_COUNTRY_UNKNOWN and skipped[0]["country"] is None


def test_an_empty_allowlist_allows_nobody():
	candidates, skipped = select([row()], [customer()], allowed=set())
	assert candidates == []
	assert skipped[0]["reason"] == core.SKIP_COUNTRY_NOT_ALLOWED


def test_candidates_carry_their_resolved_country():
	candidates, _ = select([row(phone="+18764250250", lookup="JM")], [customer()])
	assert candidates[0]["countries"] == ["JM"]


def test_the_live_number_is_held_to_the_country_rule_again():
	assert core.build_request(live(phone="+919876543210"), customer(), ALLOWED) == (
		None,
		core.SKIP_COUNTRY_NOT_ALLOWED,
	)


# ── build_request ───────────────────────────────────────────────────────


def test_request_carries_the_bridge_name_the_live_phone_and_no_address():
	fields, reason = core.build_request(live(), customer(email="kyc@example.com"), ALLOWED)
	assert reason is None
	assert fields == {
		"username": "creech147",
		"full_name": "William Creech",
		"phone_number": "+16065550123",
		"email": "kyc@example.com",
		"current_level": "ONE",
		"requested_level": "TWO",
		"status": "Pending",
		"terminal_requested": 0,
	}


def test_the_reviewer_note_says_why_the_request_exists():
	assert core.reviewer_note(customer()) == (
		"Automatic: identity verified by Bridge KYC (customer cus-1). "
		"Level 2 under the Bridge KYC auto-upgrade policy. No address or bank account collected."
	)


def test_email_falls_back_to_the_flash_email_then_to_none():
	fields, _ = core.build_request(live(), customer(email=""), ALLOWED)
	assert fields["email"] == "flash@example.com"
	no_email = live()
	no_email["owner"]["email"] = None
	fields, _ = core.build_request(no_email, customer(email=""), ALLOWED)
	assert fields["email"] is None


@pytest.mark.parametrize(
	"account,cust,expected",
	[
		(live(level="TWO"), customer(), core.SKIP_ALREADY_UPGRADED),
		(live(level="THREE"), customer(), core.SKIP_ALREADY_UPGRADED),
		(live(status="LOCKED"), customer(), core.SKIP_NOT_ACTIVE),
		(live(phone=""), customer(), core.SKIP_NO_PHONE),
		(live(phone=None), customer(), core.SKIP_NO_PHONE),
		(live(), customer(first="", last=" "), core.SKIP_NO_LEGAL_NAME),
	],
)
def test_live_recheck_refusals(account, cust, expected):
	assert core.build_request(account, cust, ALLOWED) == (None, expected)


def test_snapshot_keeps_no_name_email_or_address():
	snapshot = json.loads(core.bridge_snapshot(customer()))
	assert snapshot == {
		"id": "cus-1",
		"status": "active",
		"updated_at": "2026-10-01T00:00:00Z",
		"endorsements": [{"name": "base", "status": "approved"}],
	}


# ── the job ─────────────────────────────────────────────────────────────

DOCTYPES = Path(__file__).resolve().parents[1] / "admin_panel" / "doctype"


def required_fields(folder):
	fields = json.loads((DOCTYPES / folder / f"{folder}.json").read_text())["fields"]
	return [f["fieldname"] for f in fields if f.get("reqd")]


# Read from the real doctype JSON: frappe checks these on every insert AND
# every save (Document._validate_mandatory), unless the doc carries
# flags.ignore_mandatory. FakeDoc checks nothing on its own, which is how an
# approval that re-saves an address-less request once passed these tests.
REQUIRED = {
	"Account Upgrade Request": required_fields("account_upgrade_request"),
	"ID Verification": required_fields("id_verification"),
}


class MandatoryError(Exception):
	pass


SITE_DEFAULTS = {"country": "United States", "currency": "USD"}


def enforce_mandatory(doc):
	if getattr(doc.flags, "ignore_mandatory", False):
		return
	missing = [f for f in REQUIRED.get(doc.doctype, ()) if not str(doc.get(f) or "").strip()]
	if missing:
		raise MandatoryError(f"[{doc.doctype}]: {', '.join(missing)}")


@pytest.fixture()
def job(fake, monkeypatch):
	fake.seed(
		"Decision Reason",
		{
			"name": "APPROVE_BRIDGE_KYC",
			"code": "APPROVE_BRIDGE_KYC",
			"outcome": "approve",
			"label": "Verified via Bridge KYC",
			"user_facing_message": "Verified via KYC.",
		},
	)
	fake.seed(
		"Allowed Country",
		{"name": "US", "alpha2_code": "US", "flash_allowed": 1},
		{"name": "JM", "alpha2_code": "JM", "flash_allowed": 1},
		{"name": "IN", "alpha2_code": "IN", "flash_allowed": 0},
	)
	fake.singles[SETTINGS] = {
		"doctype": SETTINGS,
		"name": SETTINGS,
		"bridge_kyc_satisfies_identity": 1,
		"auto_upgrade_bridge_kyc": 1,
	}
	fake.commit()

	state = types.SimpleNamespace(
		accounts=[row()],
		customers=[customer()],
		live={"creech147": live()},
		level_updates=[],
		lookups=[],
		flash_result={},
		erp=[],
		events=[],
		errors=[],
		reads=[],
		flags={},
		raise_for=set(),
		fail_idv_for=set(),
		# Second and later reads of an account (the post-failure check).
		live_after={},
		unreadable_after=set(),
		reads_by_user={},
		save_fails_for=set(),
	)

	def load_accounts():
		state.reads.append("mongo")
		return [dict(r) for r in state.accounts]

	class StubBridge:
		def list_customers(self):
			state.reads.append("bridge")
			return state.customers

	class StubPlanClient:
		def get_account_by_username(self, username):
			if username in state.raise_for:
				raise RuntimeError(f"flash unreachable for {username}")
			seen = state.reads_by_user.get(username, 0)
			state.reads_by_user[username] = seen + 1
			if seen:
				if username in state.unreadable_after:
					raise RuntimeError(f"flash unreachable for {username}")
				if username in state.live_after:
					return state.live_after[username]
			return state.live.get(username)

	class StubApproveClient:
		def get_account_by_phone(self, phone):
			state.lookups.append(phone)
			return {"id": f"uid-{phone}"}

		def update_account_level(self, uid, level, erp_party=None):
			state.level_updates.append((uid, level, erp_party))
			return state.flash_result

	def create_erp_records(req):
		state.erp.append(req.name)
		name = f"CUST-{req.username}"
		frappe.get_doc({"doctype": "Customer", "name": name, "mobile_no": req.phone_number}).insert(
			ignore_permissions=True
		)
		return [], name

	real_insert = fake.insert
	real_update = fake.update

	def spy_insert(doc, ignore_permissions=False):
		state.flags[doc.doctype] = dict(vars(doc.flags))
		if doc.doctype == "ID Verification" and doc.username in state.fail_idv_for:
			raise RuntimeError(f"ID Verification insert failed for {doc.username}")
		if doc.doctype == "Account Upgrade Request":
			# frappe's update_if_missing on insert: an empty Link field takes the
			# site's global default unless the doc lists it in
			# dont_update_if_missing. Prod's default Country is "United States".
			keep_empty = getattr(doc, "dont_update_if_missing", None) or []
			for field, value in SITE_DEFAULTS.items():
				if doc.get(field) is None and field not in keep_empty:
					setattr(doc, field, value)
		enforce_mandatory(doc)
		real_insert(doc, ignore_permissions=ignore_permissions)

	def spy_update(doc):
		enforce_mandatory(doc)
		if doc.doctype == "Account Upgrade Request" and doc.username in state.save_fails_for:
			raise RuntimeError("database went away")
		real_update(doc)

	monkeypatch.setattr(fake, "insert", spy_insert)
	monkeypatch.setattr(fake, "update", spy_update)
	monkeypatch.setattr(bridge_kyc_upgrade, "load_bridge_accounts", load_accounts)
	monkeypatch.setattr(bridge_kyc_upgrade, "BridgeClient", StubBridge)
	monkeypatch.setattr(bridge_kyc_upgrade, "GraphQLClient", StubPlanClient)
	monkeypatch.setattr(admin_api, "GraphQLClient", StubApproveClient)
	monkeypatch.setattr(admin_api, "_create_erp_records", create_erp_records)
	monkeypatch.setattr(admin_api, "record_event", lambda *args: state.events.append(args))
	monkeypatch.setattr(admin_api, "audit_log", lambda *args: None)

	def log_error(title=None, message=None, reference_doctype=None, reference_name=None):
		# Like frappe: an Error Log row inside the current transaction.
		state.errors.append((title, message))
		fake.rows("Error Log").append(
			{
				"doctype": "Error Log",
				"method": title,
				"error": message,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"creation": fake.now_datetime(),
			}
		)

	monkeypatch.setattr(frappe, "log_error", log_error, raising=False)

	# A real logger that starts at ERROR, like frappe's on the cluster, so a
	# summary line only lands if the module raises the level itself.
	state.log = []

	class Capture(logging.Handler):
		def emit(self, record):
			state.log.append((record.levelname, record.getMessage()))

	logger = logging.getLogger("test-bridge-kyc-upgrade")
	logger.handlers = [Capture()]
	logger.propagate = False
	logger.setLevel(logging.ERROR)
	monkeypatch.setattr(frappe, "logger", lambda *args, **kwargs: logger, raising=False)
	monkeypatch.setattr(bridge_kyc_upgrade, "_STDOUT_HANDLER", logging.NullHandler())

	state.fake = fake
	return state


def requests_(state):
	return state.fake.rows("Account Upgrade Request")


def idvs(state):
	return state.fake.rows("ID Verification")


def test_switch_off_is_a_no_op_that_reads_nothing(job):
	job.fake.singles[SETTINGS]["auto_upgrade_bridge_kyc"] = 0
	assert bridge_kyc_upgrade.run_auto_upgrade() == {
		"enabled": False,
		"reason": "Auto-Upgrade Bridge KYC to Level 2 is off",
	}
	assert job.reads == [] and requests_(job) == [] and job.level_updates == []


def test_bridge_identity_off_disables_it_even_with_the_switch_on(job):
	job.fake.singles[SETTINGS]["bridge_kyc_satisfies_identity"] = 0
	result = bridge_kyc_upgrade.run_auto_upgrade()
	assert result == {"enabled": False, "reason": "Bridge KYC Satisfies Identity is off"}
	assert job.reads == [] and job.level_updates == []


def test_upgrade_goes_through_the_normal_approval(job):
	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == ["creech147"]
	assert summary["failed"] == [] and summary["deferred"] == 0

	# Flash: looked up by the live phone, set to TWO with the ERP party the
	# approval created.
	assert job.lookups == ["+16065550123"]
	assert job.level_updates == [("uid-+16065550123", "TWO", "CUST-creech147")]

	[req] = requests_(job)
	assert req["status"] == "Approved"
	assert req["decision_reason"] == "APPROVE_BRIDGE_KYC"
	assert req["reviewed_by"] == "reviewer@getflash.io"
	assert req["full_name"] == "William Creech"
	assert req["current_level"] == "ONE" and req["requested_level"] == "TWO"
	assert job.erp == [req["name"]]
	# No address, and nothing bypasses the required-field check: the fixture
	# enforces the doctype's reqd fields on every insert and save.
	assert req.get("address_line1") is None
	# Not the site's default Country / Currency: nobody supplied them.
	assert req.get("country") is None and req.get("currency") is None
	assert not job.flags["Account Upgrade Request"].get("ignore_mandatory")
	# Reviewer pages show support_note as "Rejection Reason"; the why lives on
	# the ID Verification instead.
	assert req.get("support_note") is None
	assert [c["name"] for c in job.fake.rows("Customer")] == ["CUST-creech147"]

	[idv] = idvs(job)
	assert idv["upgrade_request"] == req["name"]
	assert idv["identity_source"] == "bridge_kyc"
	assert idv["bridge_customer_id"] == "cus-1"
	assert "Creech" not in idv["bridge_snapshot_json"]
	assert idv["reviewer_note"].startswith("Automatic: identity verified by Bridge KYC (customer cus-1)")
	assert idv["status"] == "Approved" and idv["decision_reason"] == "APPROVE_BRIDGE_KYC"

	[event] = job.events
	assert event[0] == "upgrade_approved" and event[3]["decision_reason"] == "APPROVE_BRIDGE_KYC"


def test_an_account_upgraded_since_the_bulk_read_is_skipped_without_a_request(job):
	job.live["creech147"] = live(level="TWO")
	summary = bridge_kyc_upgrade.run_auto_upgrade()
	assert summary["upgraded"] == []
	assert {"username": "creech147", "outcome": "skipped", "reason": core.SKIP_ALREADY_UPGRADED} in summary[
		"skipped"
	]
	assert requests_(job) == [] and job.level_updates == []


def test_an_existing_erp_party_found_by_mobile_is_upgraded(job):
	job.fake.seed("Customer", {"name": "William Creech", "mobile_no": "+16065550123"})
	job.live["creech147"] = {**live(), "erpParty": "William Creech"}
	assert bridge_kyc_upgrade.run_auto_upgrade()["upgraded"] == ["creech147"]


def test_an_existing_erp_party_not_found_by_mobile_is_left_for_a_human(job):
	job.fake.seed("Customer", {"name": "Old Party", "mobile_no": "+18765550000"})
	job.live["creech147"] = {**live(), "erpParty": "Old Party"}

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == []
	assert reasons(summary["skipped"]) == {"creech147": core.SKIP_ERP_PARTY_MISMATCH}
	assert requests_(job) == [] and job.level_updates == []


def error_logs(state):
	return [r["method"] for r in state.fake.rows("Error Log")]


def test_a_failure_before_flash_moves_leaves_no_trace_and_waits_a_day(job):
	job.flash_result = {"errors": [{"message": "erpParty rejected"}]}

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	[failure] = summary["failed"]
	assert failure["username"] == "creech147" and "erpParty rejected" in failure["error"]
	assert "flash_changed" not in failure
	# No request the user never filed (the app would show it as pending), no
	# ID Verification, no Customer.
	assert requests_(job) == [] and idvs(job) == [] and job.fake.rows("Customer") == []
	assert error_logs(job) == ["Bridge KYC auto-upgrade failed for creech147"]

	job.flash_result = {}
	again = bridge_kyc_upgrade.run_auto_upgrade()
	assert again["upgraded"] == [] and again["failed"] == []
	assert reasons(again["skipped"]) == {"creech147": core.SKIP_RECENT_FAILURE}

	job.fake.clock += timedelta(hours=core.RETRY_AFTER_HOURS, minutes=1)
	assert bridge_kyc_upgrade.run_auto_upgrade()["upgraded"] == ["creech147"]


def test_a_failure_after_flash_moved_keeps_the_customer_and_the_pending_request(job):
	"""Flash is already at Level 2 with erpParty naming the new Customer, so
	rolling back would leave erpParty pointing at nothing."""
	job.save_fails_for = {"creech147"}
	job.live_after["creech147"] = live(level="TWO")

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	[failure] = summary["failed"]
	assert failure["flash_changed"] is True
	assert job.level_updates == [("uid-+16065550123", "TWO", "CUST-creech147")]
	assert [c["name"] for c in job.fake.rows("Customer")] == ["CUST-creech147"]
	[req] = requests_(job)
	assert req["status"] == "Pending" and failure["request"] == req["name"]
	assert len(idvs(job)) == 1
	[log] = job.fake.rows("Error Log")
	assert log["reference_doctype"] == "Account Upgrade Request" and log["reference_name"] == req["name"]
	# The pending request now keeps the account out of later runs.
	job.save_fails_for = set()
	job.fake.clock += timedelta(hours=core.RETRY_AFTER_HOURS, minutes=1)
	assert reasons(bridge_kyc_upgrade.run_auto_upgrade()["skipped"]) == {
		"creech147": core.SKIP_PENDING_REQUEST
	}


def test_when_flash_cannot_be_read_after_a_failure_the_records_are_kept(job):
	job.flash_result = {"errors": [{"message": "timeout"}]}
	job.unreadable_after = {"creech147"}

	[failure] = bridge_kyc_upgrade.run_auto_upgrade()["failed"]

	assert failure["flash_changed"] is True
	assert [r["status"] for r in requests_(job)] == ["Pending"]
	assert [c["name"] for c in job.fake.rows("Customer")] == ["CUST-creech147"]


def test_an_error_log_survives_the_next_accounts_rollback(job):
	job.accounts = [
		row("first", "cus-1", created_at="2026-07-01T00:00:00"),
		row("second", "cus-2", created_at="2026-08-08T00:00:00"),
	]
	job.customers = [customer("cus-1"), customer("cus-2")]
	job.live = {"first": live("first", phone="+16065550001"), "second": live("second")}
	job.flash_result = {"errors": [{"message": "flash said no"}]}
	job.fail_idv_for = {"second"}

	bridge_kyc_upgrade.run_auto_upgrade()

	assert error_logs(job) == [
		"Bridge KYC auto-upgrade failed for first",
		"Bridge KYC auto-upgrade failed for second",
	]


def test_an_exception_rolls_back_that_account_and_the_run_continues(job):
	job.accounts = [
		row("broken", "cus-1", created_at="2026-07-01T00:00:00"),
		row("creech147", "cus-2", created_at="2026-08-08T00:00:00"),
	]
	job.customers = [customer("cus-1"), customer("cus-2")]
	job.live = {"broken": live("broken"), "creech147": live()}
	job.raise_for = {"broken"}

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == ["creech147"]
	assert [f["username"] for f in summary["failed"]] == ["broken"]
	assert [r["username"] for r in requests_(job)] == ["creech147"]
	title, message = job.errors[0]
	assert title == "Bridge KYC auto-upgrade failed for broken"
	assert "RuntimeError: flash unreachable for broken" in message


def test_a_failure_after_the_request_insert_leaves_no_orphan_request(job):
	"""Without the rollback, the next account's commit would persist a Pending
	request that has no ID Verification and was never approved."""
	job.accounts = [
		row("halfway", "cus-1", created_at="2026-07-01T00:00:00"),
		row("creech147", "cus-2", created_at="2026-08-08T00:00:00"),
	]
	job.customers = [customer("cus-1"), customer("cus-2")]
	job.live = {"halfway": live("halfway", phone="+16065550999"), "creech147": live()}
	job.fail_idv_for = {"halfway"}

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert [f["username"] for f in summary["failed"]] == ["halfway"]
	assert summary["upgraded"] == ["creech147"]
	assert [r["username"] for r in requests_(job)] == ["creech147"]
	assert [i["username"] for i in idvs(job)] == ["creech147"]


def test_the_per_run_cap_defers_the_rest(job, monkeypatch):
	monkeypatch.setattr(bridge_kyc_upgrade, "MAX_UPGRADES_PER_RUN", 2)
	job.accounts = [row(f"u{i}", f"cus-{i}", created_at=f"2026-07-0{i}T00:00:00") for i in range(1, 4)]
	job.customers = [customer(f"cus-{i}") for i in range(1, 4)]
	job.live = {f"u{i}": live(f"u{i}", phone=f"+1606555000{i}") for i in range(1, 4)}

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == ["u1", "u2"]
	assert summary["candidates"] == 3 and summary["deferred"] == 1


def test_the_summary_line_is_emitted_despite_an_error_level_logger(job):
	bridge_kyc_upgrade.run_auto_upgrade()
	assert job.log == [("INFO", "bridge_kyc_upgrade upgraded=['creech147'] failed=[] deferred=0")]


def test_a_run_with_only_skips_logs_nothing(job):
	job.live["creech147"] = live(phone="")
	summary = bridge_kyc_upgrade.run_auto_upgrade()
	assert reasons(summary["skipped"]) == {"creech147": core.SKIP_NO_PHONE}
	assert job.log == []


def test_preview_reports_without_writing(job):
	job.accounts = [row(), row("someone", "cus-9")]
	job.fake.singles[SETTINGS]["auto_upgrade_bridge_kyc"] = 0

	preview = bridge_kyc_upgrade.preview_bridge_kyc_upgrades()

	assert preview["success"] is True
	assert preview["enabled"] is False
	assert preview["candidates"] == [
		{"username": "creech147", "level": 1, "country": "US", "bridge_customer_id": "cus-1"}
	]
	assert preview["allowed_countries"] == 2
	assert reasons(preview["skipped"]) == {"someone": core.SKIP_MISSING_AT_BRIDGE}
	assert requests_(job) == [] and job.level_updates == [] and job.lookups == []


def test_the_request_address_is_only_required_for_level_three_and_only_in_the_form():
	"""The server enforces static reqd only (frappe ignores mandatory_depends_on
	there), so an address-less Level 2 request can be saved, approved, rejected
	and closed. Flash's API still requires an address on customer requests."""
	fields = {
		f["fieldname"]: f
		for f in json.loads(
			(DOCTYPES / "account_upgrade_request" / "account_upgrade_request.json").read_text()
		)["fields"]
	}
	for name in ("address_title", "address_line1", "city", "state", "country"):
		assert not fields[name].get("reqd"), name
		assert fields[name]["mandatory_depends_on"] == "eval:doc.requested_level=='THREE'"
	assert set(REQUIRED["Account Upgrade Request"]) == {"username", "full_name", "phone_number"}


def test_accounts_outside_flash_markets_are_not_upgraded(job):
	job.accounts = [row("ravi", "cus-1", phone="+919876543210", lookup="IN")]

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == [] and summary["candidates"] == 0
	assert reasons(summary["skipped"]) == {"ravi": core.SKIP_COUNTRY_NOT_ALLOWED}
	assert requests_(job) == [] and job.level_updates == [] and job.lookups == []


def test_an_empty_allowed_country_list_upgrades_nobody(job):
	job.fake.tables["Allowed Country"] = []

	summary = bridge_kyc_upgrade.run_auto_upgrade()

	assert summary["upgraded"] == []
	assert reasons(summary["skipped"]) == {"creech147": core.SKIP_COUNTRY_NOT_ALLOWED}
	assert requests_(job) == []


def test_every_link_field_the_job_leaves_empty_is_kept_from_site_defaults():
	fields = json.loads((DOCTYPES / "account_upgrade_request" / "account_upgrade_request.json").read_text())[
		"fields"
	]
	links = {f["fieldname"] for f in fields if f["fieldtype"] == "Link"}
	set_by_job = set(core.build_request(live(), customer(), ALLOWED)[0])
	set_by_approval = {"reviewed_by", "decision_reason"}
	assert links - set_by_job - set_by_approval <= set(core.UNSUPPLIED_FIELDS)


def test_load_bridge_accounts_joins_the_owner_phone_and_lookup_country(monkeypatch):
	from admin_panel.api import mongo_reader

	class Collection:
		def __init__(self, docs):
			self.docs = docs
			self.filters = []

		def find(self, filters, projection=None):
			self.filters.append(filters)
			return list(self.docs)

	accounts = Collection(
		[
			{"bridgeCustomerId": "cus-1", "username": "a", "level": 1, "kratosUserId": "k1"},
			{"bridgeCustomerId": "cus-2", "username": "b", "level": 1, "kratosUserId": "k2"},
		]
	)
	users = Collection([{"userId": "k1", "phone": "+18764250250", "phoneMetadata": {"countryCode": "JM"}}])
	monkeypatch.setattr(
		mongo_reader, "_get_db", lambda: types.SimpleNamespace(accounts=accounts, users=users)
	)

	rows = mongo_reader.load_bridge_accounts()

	assert users.filters == [{"userId": {"$in": ["k1", "k2"]}}]
	assert (rows[0]["phone"], rows[0]["phone_lookup_country"]) == ("+18764250250", "JM")
	assert (rows[1]["phone"], rows[1]["phone_lookup_country"]) == (None, None)


def test_preview_is_whitelisted_and_admin_gated():
	source = (Path(__file__).resolve().parents[1] / "api" / "bridge_kyc_upgrade.py").read_text()
	stack = "@frappe.whitelist()\n@require_admin()\n@handle_api_errors\ndef preview_bridge_kyc_upgrades():"
	assert stack in source
