"""Bridge KYC → Level 2 auto-upgrade. Policy and rules: ``bridge_kyc_upgrade_core``.

Every 15 minutes (hooks.py), while ID Verification Settings has both
``bridge_kyc_satisfies_identity`` and ``auto_upgrade_bridge_kyc`` on, each
Flash account linked to a KYC-approved individual Bridge customer and still
below Level 2 is upgraded through the reviewer path, not around it: an
Account Upgrade Request plus an ID Verification (identity_source
``bridge_kyc``), approved by ``approve_upgrade_request`` with reason
APPROVE_BRIDGE_KYC. That approval creates (or reuses, by mobile number) the
ERP Customer that flash requires as ``erpParty`` for Level 2, stamps the
decision, mirrors it onto the ID Verification and writes the ledger event.
Scheduled approvals are stamped as reviewed by the scheduler's session user
(Administrator).

A request whose approval fails is left Pending. It lands in the reviewer
queue, and the next run skips the account (it has a pending request) instead
of retrying it every 15 minutes.
"""

import logging
import sys
import traceback

import frappe

from .admin_api import approve_upgrade_request
from .auth import require_admin
from .bridge_client import BridgeClient
from .bridge_kyc_upgrade_core import (
	MAX_UPGRADES_PER_RUN,
	REASON_CODE,
	SKIP_ERP_PARTY_MISMATCH,
	bridge_snapshot,
	build_request,
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


def _plan():
	pending = frappe.get_all("Account Upgrade Request", filters={"status": "Pending"}, pluck="username")
	return select_candidates(load_bridge_accounts(), BridgeClient().list_customers(), pending)


def _upgrade(candidate, client):
	"""File and approve one Bridge KYC upgrade. Returns the outcome."""
	customer = candidate["customer"]
	username = candidate["account"].get("username")

	# Re-read live: the plan came from a bulk read, and the request must carry
	# the account's current phone and level.
	account = client.get_account_by_username(username)
	if not account:
		return {"username": username, "outcome": "skipped", "reason": "account_not_found"}
	fields, reason = build_request(account, customer)
	if reason:
		return {"username": username, "outcome": "skipped", "reason": reason}
	# The approval finds the ERP Customer by mobile number. If that is not the
	# party the account already has, approving would repoint erpParty at a new
	# Customer and strand what hangs off the old one (bank accounts, cashouts).
	party = account.get("erpParty")
	if party and frappe.db.get_value("Customer", {"mobile_no": fields["phone_number"]}, "name") != party:
		return {"username": username, "outcome": "skipped", "reason": SKIP_ERP_PARTY_MISMATCH}

	req = frappe.get_doc({"doctype": "Account Upgrade Request", **fields})
	# The address block is mandatory on the form, and a Bridge-only upgrade has
	# none. _create_erp_records already treats address and bank as optional.
	req.flags.ignore_mandatory = True
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
		}
	).insert(ignore_permissions=True)
	# Committed before flash is touched, so a run that dies mid-approval still
	# leaves the request on record for a reviewer.
	frappe.db.commit()

	result = approve_upgrade_request(req.name, reason_code=REASON_CODE) or {}
	if result.get("success"):
		outcome = {"username": username, "outcome": "upgraded", "request": req.name}
		if result.get("warning"):
			outcome["warning"] = result["warning"]
		return outcome
	error = result.get("error") or "; ".join(result.get("errors") or []) or "approval returned no result"
	return {"username": username, "outcome": "failed", "request": req.name, "error": error}


def run_auto_upgrade():
	"""Scheduled every 15 minutes. A no-op unless both switches are on."""
	enabled, reason = _switches()
	if not enabled:
		return {"enabled": False, "reason": reason}

	candidates, skipped = _plan()
	client = GraphQLClient()
	outcomes = []
	for candidate in candidates[:MAX_UPGRADES_PER_RUN]:
		username = candidate["account"].get("username")
		detail = None
		try:
			outcome = _upgrade(candidate, client)
		except Exception as exc:
			# Discards a request/ID Verification inserted but not yet committed.
			frappe.db.rollback()
			detail = traceback.format_exc()
			outcome = {"username": username, "outcome": "failed", "error": str(exc)}
		if outcome["outcome"] == "failed":
			# Error Log rows live in the database, unlike frappe.logger() files.
			frappe.log_error(
				title=f"Bridge KYC auto-upgrade failed for {username}",
				message=detail or str(outcome),
			)
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
	candidates, skipped = _plan()
	return {
		"success": True,
		"enabled": enabled,
		"disabled_reason": reason,
		"max_per_run": MAX_UPGRADES_PER_RUN,
		"candidates": [
			{
				"username": c["account"].get("username"),
				"level": c["account"].get("level"),
				"bridge_customer_id": c["customer"].get("id"),
			}
			for c in candidates
		],
		"skipped": skipped,
	}
