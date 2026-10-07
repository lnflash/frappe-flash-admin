"""Bridge KYC → Level 2 auto-upgrade. Policy and rules: ``bridge_kyc_upgrade_core``.

Every 15 minutes (hooks.py), while ID Verification Settings has both
``bridge_kyc_satisfies_identity`` and ``auto_upgrade_bridge_kyc`` on, each
Flash account linked to a KYC-approved individual Bridge customer, still
below Level 2, and with a phone country marked flash_allowed in "Allowed
Country" (the list flash's Bridge KYC gate uses) is upgraded through the
reviewer path, not around it: an
Account Upgrade Request plus an ID Verification (identity_source
``bridge_kyc``), approved by ``approve_upgrade_request`` with reason
APPROVE_BRIDGE_KYC. That approval creates (or reuses, by mobile number) the
ERP Customer that flash requires as ``erpParty`` for Level 2, stamps the
decision, mirrors it onto the ID Verification and writes the ledger event.
Scheduled approvals are stamped as reviewed by the scheduler's session user
(Administrator).

Nothing is committed until the approval commits it. When an approval fails:
- if flash is still below Level 2, everything is rolled back (no request the
  user never filed, no Customer), and the account is retried after
  RETRY_AFTER_HOURS;
- if flash already moved, or cannot be read to tell, the records are kept:
  flash's erpParty may now name the new Customer, and the request stays
  Pending for a reviewer.
Either way an Error Log row is written and committed on its own.
"""

import logging
import sys
import traceback
from datetime import timedelta

import frappe

from .admin_api import approve_upgrade_request
from .auth import require_admin
from .bridge_client import BridgeClient
from .bridge_kyc_upgrade_core import (
	ELIGIBLE_LEVEL_NAMES,
	FAILURE_TITLE_PREFIX,
	MAX_UPGRADES_PER_RUN,
	REASON_CODE,
	RETRY_AFTER_HOURS,
	SKIP_ERP_PARTY_MISMATCH,
	UNSUPPLIED_FIELDS,
	bridge_snapshot,
	build_request,
	reviewer_note,
	select_candidates,
)
from .common import handle_api_errors
from .graphql_client import GraphQLClient
from .idv_core import SETTINGS_DOCTYPE
from .mongo_reader import load_bridge_accounts

# One handler object, attached by identity, so re-attaching per run is a
# no-op. Why the explicit stdout handler and setLevel at all: see
# support_lookup._audit_logger — frappe.logger() drops INFO on the cluster
# and keeps its files on a pod with no volume.
_STDOUT_HANDLER = logging.StreamHandler(sys.stdout)
_STDOUT_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))


def _logger():
	logger = frappe.logger("bridge_kyc_upgrade", max_size=1_000_000, file_count=5)
	logger.setLevel(logging.INFO)
	logger.addHandler(_STDOUT_HANDLER)
	return logger


def _switches():
	"""``(enabled, reason_if_not)`` from ID Verification Settings."""
	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	if not frappe.utils.cint(settings.get("bridge_kyc_satisfies_identity")):
		return False, "Bridge KYC Satisfies Identity is off"
	if not frappe.utils.cint(settings.get("auto_upgrade_bridge_kyc")):
		return False, "Auto-Upgrade Bridge KYC to Level 2 is off"
	return True, None


def _recently_failed():
	"""Usernames with a failure Error Log inside the retry window."""
	cutoff = frappe.utils.now_datetime() - timedelta(hours=RETRY_AFTER_HOURS)
	titles = frappe.get_all("Error Log", filters={"creation": [">=", cutoff]}, pluck="method")
	return {t[len(FAILURE_TITLE_PREFIX) :] for t in titles if (t or "").startswith(FAILURE_TITLE_PREFIX)}


def _allowed_countries():
	"""Alpha-2 codes with flash_allowed = 1. Empty means nobody qualifies."""
	codes = frappe.get_all("Allowed Country", filters={"flash_allowed": 1}, pluck="alpha2_code")
	return {code.strip().upper() for code in codes if code and code.strip()}


def _plan(allowed):
	pending = frappe.get_all("Account Upgrade Request", filters={"status": "Pending"}, pluck="username")
	return select_candidates(
		load_bridge_accounts(),
		BridgeClient().list_customers(),
		pending,
		_recently_failed(),
		allowed_countries=allowed,
	)


def _flash_still_below_level_two(client, username):
	"""True only when flash is readable and the account is still below Level 2."""
	try:
		account = client.get_account_by_username(username)
	except Exception:
		return False
	return bool(account) and account.get("level") in ELIGIBLE_LEVEL_NAMES


def _upgrade(candidate, client, allowed):
	"""File and approve one Bridge KYC upgrade. Returns the outcome."""
	customer = candidate["customer"]
	username = candidate["account"].get("username")

	# Re-read live: the plan came from a bulk read, and the request must carry
	# the account's current phone and level.
	account = client.get_account_by_username(username)
	if not account:
		return {"username": username, "outcome": "skipped", "reason": "account_not_found"}
	fields, reason = build_request(account, customer, allowed)
	if reason:
		return {"username": username, "outcome": "skipped", "reason": reason}
	# The approval finds the ERP Customer by mobile number. If that is not the
	# party the account already has, approving would repoint erpParty at a new
	# Customer and strand what hangs off the old one (bank accounts, cashouts).
	party = account.get("erpParty")
	if party and frappe.db.get_value("Customer", {"mobile_no": fields["phone_number"]}, "name") != party:
		return {"username": username, "outcome": "skipped", "reason": SKIP_ERP_PARTY_MISMATCH}

	# No address: the request doctype only requires one for Level 3, and
	# _create_erp_records already treats address and bank as optional. The
	# unsupplied fields stay NULL instead of taking the site's default Country
	# and Currency.
	req = frappe.get_doc({"doctype": "Account Upgrade Request", **fields})
	req.dont_update_if_missing = list(UNSUPPLIED_FIELDS)
	req.insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "ID Verification",
			"upgrade_request": req.name,
			"username": username,
			"requested_level": fields["requested_level"],
			"status": "Ready for review",
			"identity_source": "bridge_kyc",
			"bridge_customer_id": customer.get("id"),
			"bridge_snapshot_json": bridge_snapshot(customer),
			"reviewer_note": reviewer_note(customer),
		}
	).insert(ignore_permissions=True)

	# Not committed yet: the approval commits once flash has moved.
	detail = None
	try:
		result = approve_upgrade_request(req.name, reason_code=REASON_CODE) or {}
	except Exception as exc:
		detail = traceback.format_exc()
		result = {"error": f"{type(exc).__name__}: {exc}"}
	if result.get("success"):
		outcome = {"username": username, "outcome": "upgraded", "request": req.name}
		if result.get("warning"):
			outcome["warning"] = result["warning"]
		return outcome

	error = result.get("error") or "; ".join(result.get("errors") or []) or "approval returned no result"
	outcome = {"username": username, "outcome": "failed", "error": error, "detail": detail}
	if _flash_still_below_level_two(client, username):
		# Flash never moved: leave no trace and retry after the backoff.
		frappe.db.rollback()
		return outcome
	# Flash moved (or cannot be read): its erpParty may name the Customer this
	# approval created, so keep it, and leave the request Pending for a reviewer.
	frappe.db.commit()
	return {**outcome, "request": req.name, "flash_changed": True}


def run_auto_upgrade():
	"""Scheduled every 15 minutes. A no-op unless both switches are on."""
	enabled, reason = _switches()
	if not enabled:
		return {"enabled": False, "reason": reason}

	allowed = _allowed_countries()
	candidates, skipped = _plan(allowed)
	client = GraphQLClient()
	outcomes = []
	for candidate in candidates[:MAX_UPGRADES_PER_RUN]:
		username = candidate["account"].get("username")
		try:
			outcome = _upgrade(candidate, client, allowed)
		except Exception as exc:
			# Raised before the approval ran, so flash is untouched: discard the
			# uncommitted request / ID Verification.
			frappe.db.rollback()
			outcome = {
				"username": username,
				"outcome": "failed",
				"error": str(exc),
				"detail": traceback.format_exc(),
			}
		if outcome["outcome"] == "failed":
			detail = outcome.pop("detail", None)
			# Error Log rows live in the database, unlike frappe.logger() files.
			# Logged after the rollback/commit above and committed on its own, so
			# the next account's rollback cannot take it with it.
			frappe.log_error(
				title=f"{FAILURE_TITLE_PREFIX}{username}",
				message=f"{outcome}\n\n{detail}" if detail else str(outcome),
				reference_doctype="Account Upgrade Request" if outcome.get("request") else None,
				reference_name=outcome.get("request"),
			)
			frappe.db.commit()
		outcomes.append(outcome)

	summary = {
		"enabled": True,
		"candidates": len(candidates),
		"deferred": max(len(candidates) - MAX_UPGRADES_PER_RUN, 0),
		"upgraded": [o["username"] for o in outcomes if o["outcome"] == "upgraded"],
		"failed": [o for o in outcomes if o["outcome"] == "failed"],
		"skipped": skipped + [o for o in outcomes if o["outcome"] == "skipped"],
	}
	# Quiet unless something changed: skips are the steady state and would
	# otherwise log the same lines every 15 minutes.
	if summary["upgraded"] or summary["failed"]:
		_logger().info(
			"bridge_kyc_upgrade upgraded=%s failed=%s deferred=%s",
			summary["upgraded"],
			[o["username"] for o in summary["failed"]],
			summary["deferred"],
		)
	return summary


@frappe.whitelist()
@require_admin()
@handle_api_errors
def preview_bridge_kyc_upgrades():
	"""Read-only: who the auto-upgrade would move to Level 2, who it skips and why."""
	enabled, reason = _switches()
	allowed = _allowed_countries()
	candidates, skipped = _plan(allowed)
	return {
		"success": True,
		"enabled": enabled,
		"disabled_reason": reason,
		"max_per_run": MAX_UPGRADES_PER_RUN,
		"allowed_countries": len(allowed),
		"candidates": [
			{
				"username": c["account"].get("username"),
				"level": c["account"].get("level"),
				"country": "/".join(c["countries"]),
				"bridge_customer_id": c["customer"].get("id"),
			}
			for c in candidates
		],
		"skipped": skipped,
	}
