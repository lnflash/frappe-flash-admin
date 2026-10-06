"""Bridge KYC → Level 2: who qualifies and what the request says — no Frappe runtime.

Policy (operator decision, 2026-10-06): a Flash account whose Bridge customer
has passed KYC — Bridge customer status ``active``, the same mapping flash's
KYC webhook uses for ``approved`` — has a verified identity, and that is
enough for Level 2. ``bridge_kyc_upgrade`` applies the policy through the
normal Account Upgrade Request path; this module holds the rules so they can
be tested without a bench.
"""

import json

TARGET_LEVEL = "TWO"
REASON_CODE = "APPROVE_BRIDGE_KYC"
BRIDGE_APPROVED = "active"
INDIVIDUAL = "individual"

# Mongo stores the level as an int; a missing level is Level 0 (flash's
# effectiveAccountLevel does the same).
ELIGIBLE_LEVELS = (0, 1)
# The same levels as flash's admin GraphQL names them.
ELIGIBLE_LEVEL_NAMES = ("ZERO", "ONE")

# Upper bound on upgrades per scheduled run. The first run after the switch
# is turned on is the backfill; the cap spreads it over a few runs rather
# than firing every approval in one job.
MAX_UPGRADES_PER_RUN = 25

# A failed upgrade writes an Error Log titled FAILURE_TITLE_PREFIX + username,
# and the account is not tried again until RETRY_AFTER_HOURS have passed, so a
# persistent failure is retried daily instead of every 15 minutes.
FAILURE_TITLE_PREFIX = "Bridge KYC auto-upgrade failed for "
RETRY_AFTER_HOURS = 24

# Skip reasons. Stable strings: the preview endpoint and the run summary
# report them as-is.
SKIP_MISSING_AT_BRIDGE = "missing_at_bridge"
SKIP_BUSINESS = "business_customer"
SKIP_SHARED_CUSTOMER = "bridge_customer_linked_to_multiple_accounts"
SKIP_NOT_ACTIVE = "account_not_active"
SKIP_NO_USERNAME = "no_username"
SKIP_PENDING_REQUEST = "pending_upgrade_request"
SKIP_NO_PHONE = "no_phone"
SKIP_NO_LEGAL_NAME = "no_legal_name"
SKIP_ALREADY_UPGRADED = "already_level_two_or_above"
SKIP_ERP_PARTY_MISMATCH = "erp_party_not_found_by_mobile"
SKIP_RECENT_FAILURE = "failed_in_the_last_day"


def _level(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return 0


def legal_name(customer):
	"""The name Bridge verified, or None."""
	first = (customer.get("first_name") or "").strip()
	last = (customer.get("last_name") or "").strip()
	return f"{first} {last}".strip() or None


def _skip(row, reason):
	return {
		"username": row.get("username"),
		"bridge_customer_id": row.get("bridge_customer_id"),
		"reason": reason,
	}


def select_candidates(accounts, customers, pending_usernames, recently_failed=()):
	"""Split Bridge-linked Flash accounts into upgrade candidates and skips.

	``accounts`` are ``mongo_reader.load_bridge_accounts()`` rows,
	``customers`` is ``BridgeClient.list_customers()`` (live: Bridge, not the
	status flash stored, is the source of truth for KYC state),
	``pending_usernames`` are usernames with a Pending Account Upgrade Request,
	which a reviewer owns, and ``recently_failed`` are usernames whose upgrade
	failed within RETRY_AFTER_HOURS.

	Accounts already at Level 2 or above and customers that have not passed
	KYC are the steady state, so they are left out silently. Everything else
	that is not upgraded is reported with a reason.

	Returns ``(candidates, skipped)``: candidates are
	``{"account": row, "customer": customer}``, oldest account first.
	"""
	by_id = {c.get("id"): c for c in customers or [] if c.get("id")}
	links = {}
	for row in accounts or []:
		links.setdefault(row.get("bridge_customer_id"), []).append(row)
	pending = set(pending_usernames or [])
	recently_failed = set(recently_failed or [])

	candidates, skipped = [], []
	for customer_id, rows in links.items():
		for row in rows:
			if _level(row.get("level")) not in ELIGIBLE_LEVELS:
				continue
			customer = by_id.get(customer_id)
			if customer is None:
				skipped.append(_skip(row, SKIP_MISSING_AT_BRIDGE))
				continue
			if customer.get("status") != BRIDGE_APPROVED:
				continue
			if (customer.get("type") or INDIVIDUAL) != INDIVIDUAL:
				# Business KYB is the Level 3 conversation, not Level 2.
				skipped.append(_skip(row, SKIP_BUSINESS))
			elif len(rows) > 1:
				# One verified person, several Flash accounts: the KYC belongs to
				# at most one of them, and nothing here can say which.
				skipped.append(_skip(row, SKIP_SHARED_CUSTOMER))
			elif row.get("status") not in (None, "active"):
				skipped.append(_skip(row, SKIP_NOT_ACTIVE))
			elif not row.get("username"):
				skipped.append(_skip(row, SKIP_NO_USERNAME))
			elif row.get("username") in pending:
				skipped.append(_skip(row, SKIP_PENDING_REQUEST))
			elif row.get("username") in recently_failed:
				skipped.append(_skip(row, SKIP_RECENT_FAILURE))
			else:
				candidates.append({"account": row, "customer": customer})

	candidates.sort(key=lambda c: (c["account"].get("created_at") or "", c["account"].get("username")))
	return candidates, skipped


def build_request(account, customer):
	"""Account Upgrade Request fields for one candidate: ``(fields, None)`` or ``(None, reason)``.

	``account`` is the live admin-GraphQL account (AccountDetail fragment),
	re-read just before upgrading. Its phone is what ``approve_upgrade_request``
	finds the account by, and what ``_create_erp_records`` matches or creates
	the ERP Customer on. The name comes from Bridge, which verified it.
	"""
	level = account.get("level")
	if level not in ELIGIBLE_LEVEL_NAMES:
		return None, SKIP_ALREADY_UPGRADED
	if (account.get("status") or "").upper() != "ACTIVE":
		return None, SKIP_NOT_ACTIVE
	owner = account.get("owner") or {}
	phone = (owner.get("phone") or "").strip()
	if not phone:
		return None, SKIP_NO_PHONE
	name = legal_name(customer)
	if not name:
		return None, SKIP_NO_LEGAL_NAME
	email = (customer.get("email") or (owner.get("email") or {}).get("address") or "").strip()

	return {
		"username": account.get("username"),
		"full_name": name,
		"phone_number": phone,
		"email": email or None,
		"current_level": level,
		"requested_level": TARGET_LEVEL,
		"status": "Pending",
		"terminal_requested": 0,
	}, None


def reviewer_note(customer):
	"""Why the request exists, for the ID Verification's internal reviewer note.

	Not the request's support_note: the reviewer pages show that one under
	"Rejection Reason".
	"""
	return (
		f"Automatic: identity verified by Bridge KYC (customer {customer.get('id')}). "
		"Level 2 under the Bridge KYC auto-upgrade policy. No address or bank account collected."
	)


def bridge_snapshot(customer):
	"""The slice of the Bridge customer kept on the ID Verification.

	Same slice flash stores (src/services/bridge/customer-snapshot.ts): id,
	status, updated_at, endorsements — no name, email or address.
	"""
	return json.dumps(
		{
			"id": customer.get("id"),
			"status": customer.get("status"),
			"updated_at": customer.get("updated_at"),
			"endorsements": customer.get("endorsements"),
		},
		sort_keys=True,
	)
