"""System accounts treasury: bankowner / funder / dealer live balances,
activity, cashout-payables coverage, and gated fund movement.

Money-flow facts this module leans on (verified in the flash codebase):
- wallets.id in mongo IS the IBEX account id, for system accounts too.
- A cashout is the USER paying an LN invoice created on the bankowner
  IBEX account — the full amount lands in bankowner; the fee is retained
  spread. The fiat leg (JMD from the physical bank) is what the Cashout
  doctype tracks as a payable.
- So: bankowner float GROWS with each cashout; "coverage" is float minus
  the USD-equivalent of unpaid cashouts (Pending / Draft / In Progress).
- Treasury moves between our own accounts = add_invoice on the receiver,
  pay_invoice from the sender (the cutover primitive).
"""

import frappe

from .auth import audit_log, require_financial, require_roles
from .common import handle_api_errors
from .ibex_client import IbexClient
from .mongo_reader import load_accounts, load_wallets

SYSTEM_ROLES = ("bankowner", "funder", "dealer")

# Cashouts whose fiat leg has not been paid out yet.
OUTSTANDING_CASHOUT_STATUSES = ("Pending", "Draft", "In Progress")

# Hard ceiling on a single transfer unless site_config raises it.
DEFAULT_TRANSFER_CAP_USD = 100.0

CURRENCY_BY_ID = {0: "BTC", 3: "USD", 29: "USDT"}


def _resolve_system_accounts():
	"""All role accounts + the optional site_config watchlist, with their wallets.

	Watchlist entries (`system_watchlist` in site_config: usernames or mongo
	account ids) are VIEW-ONLY ops accounts (e.g. legacy float accounts) —
	never valid transfer endpoints.
	"""
	accounts = load_accounts()
	wallets = load_wallets()

	by_account = {}
	for wallet_id, w in wallets.items():
		by_account.setdefault(w["account_id"], []).append(
			{"wallet_id": wallet_id, "mongo_currency": w.get("currency")}
		)

	watchlist = frappe.conf.get("system_watchlist") or []
	watch_keys = {str(x).lower() for x in watchlist}

	resolved = []
	for account_id, acc in accounts.items():
		role = (acc.get("role") or "user").lower()
		is_role_account = role in SYSTEM_ROLES
		is_watch = account_id.lower() in watch_keys or str(acc.get("username") or "").lower() in watch_keys
		if not (is_role_account or is_watch):
			continue
		resolved.append(
			{
				"account_id": account_id,
				"username": acc.get("username"),
				"role": role if is_role_account else "watchlist",
				"status": acc.get("status"),
				"transferable": is_role_account,
				"wallets": sorted(by_account.get(account_id, []), key=lambda w: w["wallet_id"]),
			}
		)
	# bankowner first, then funder, dealer, watchlist
	order = {"bankowner": 0, "funder": 1, "dealer": 2, "watchlist": 3}
	resolved.sort(key=lambda a: (order.get(a["role"], 9), a["username"] or ""))
	return resolved


def _outstanding_payables():
	"""USD-equivalent of cashouts whose fiat payout hasn't happened.

	user_receives is denominated in `currency` (USD or JMD). For JMD rows
	the USD side is user_pays - flash_fee (what actually left the user's
	wallet minus our retained fee); fall back to user_receives / rate.
	"""
	rows = frappe.get_all(
		"Cashout",
		filters={"status": ["in", list(OUTSTANDING_CASHOUT_STATUSES)]},
		fields=["user_pays", "flash_fee", "user_receives", "currency", "exchange_rate"],
	)
	total = 0.0
	for r in rows:
		if (r.currency or "USD") == "JMD":
			usd = (r.user_pays or 0.0) - (r.flash_fee or 0.0)
			if not usd and r.exchange_rate:
				usd = (r.user_receives or 0.0) / r.exchange_rate
		else:
			usd = r.user_receives or 0.0
		total += max(usd, 0.0)
	return {"count": len(rows), "usd": round(total, 2)}


@frappe.whitelist()
@require_financial()
@handle_api_errors
def get_system_accounts():
	"""Live treasury snapshot: every system/watchlist wallet with its IBEX
	balance, plus payables coverage. Small N — fetched live, no snapshotting."""
	client = IbexClient()
	accounts = _resolve_system_accounts()

	bankowner_float = 0.0
	funder_float = 0.0
	for acc in accounts:
		for w in acc["wallets"]:
			details = client.get_account_details(w["wallet_id"])
			currency = CURRENCY_BY_ID.get(details.get("currencyId"), w.get("mongo_currency") or "USD")
			balance = float(details.get("balance") or 0.0)
			w["currency"] = currency
			w["balance"] = balance
			w["not_found"] = bool(details.get("not_found"))
			# BTC balances are sats — never dollars; exclude from float math.
			if currency in ("USD", "USDT"):
				if acc["role"] == "bankowner":
					bankowner_float += balance
				elif acc["role"] == "funder":
					funder_float += balance

	payables = _outstanding_payables()
	return {
		"accounts": accounts,
		"payables": payables,
		"totals": {
			"bankowner_float": round(bankowner_float, 2),
			"funder_float": round(funder_float, 2),
			"free_float": round(bankowner_float - payables["usd"], 2),
		},
		"transfer_cap_usd": float(frappe.conf.get("system_transfer_cap_usd") or DEFAULT_TRANSFER_CAP_USD),
		"now": str(frappe.utils.now_datetime()),
	}


@frappe.whitelist()
@require_financial()
@handle_api_errors
def get_system_account_activity(wallet_id, page=0, limit=20):
	"""Recent IBEX transactions for ONE system/watchlist wallet.

	Membership is re-derived server-side — this endpoint must not become a
	generic read-any-wallet proxy."""
	wallet_id = frappe.utils.cstr(wallet_id)
	known = {w["wallet_id"] for acc in _resolve_system_accounts() for w in acc["wallets"]}
	if wallet_id not in known:
		frappe.throw("Not a system-account wallet", frappe.PermissionError)
	limit = max(1, min(int(limit or 20), 50))
	page = max(0, int(page or 0))
	raw = IbexClient().get_account_transactions(wallet_id, limit=limit, page=page)
	# Same normalized shape as customer.get_customer_detail transactions,
	# so the page reuses the census tx-table rendering unchanged.
	transactions = [
		{
			"id": tx.get("id"),
			"created_at": tx.get("createdAt"),
			"amount": tx.get("amount"),
			"network_fee": tx.get("networkFee"),
			"currency": CURRENCY_BY_ID.get(tx.get("currencyId")),
			"type_id": tx.get("transactionTypeId"),
		}
		for tx in raw
	]
	return {"wallet_id": wallet_id, "page": page, "transactions": transactions}


@frappe.whitelist()
@require_roles(["System Manager"])
@handle_api_errors
def transfer_between_system_wallets(from_wallet_id, to_wallet_id, amount_usd, memo=None):
	"""Move funds between two ROLE wallets (bankowner/funder/dealer only —
	watchlist accounts are view-only). add_invoice on the receiver,
	pay_invoice from the sender; every attempt is a System Transfer Log doc.

	Capped per-transfer by site_config system_transfer_cap_usd
	(default DEFAULT_TRANSFER_CAP_USD). Raise deliberately, never in code.
	"""
	from_wallet_id = frappe.utils.cstr(from_wallet_id)
	to_wallet_id = frappe.utils.cstr(to_wallet_id)
	amount = float(amount_usd)
	memo = frappe.utils.cstr(memo or "ERP treasury transfer")

	if from_wallet_id == to_wallet_id:
		frappe.throw("Sender and receiver are the same wallet")
	if not amount or amount <= 0:
		frappe.throw("Amount must be positive")
	cap = float(frappe.conf.get("system_transfer_cap_usd") or DEFAULT_TRANSFER_CAP_USD)
	if amount > cap:
		frappe.throw(
			f"Amount exceeds the per-transfer cap of ${cap:,.2f} (site_config system_transfer_cap_usd)"
		)

	transferable = {
		w["wallet_id"]: {**w, "role": acc["role"], "username": acc["username"]}
		for acc in _resolve_system_accounts()
		if acc["transferable"]
		for w in acc["wallets"]
	}
	if from_wallet_id not in transferable:
		frappe.throw("Sender is not a role-account wallet")
	if to_wallet_id not in transferable:
		frappe.throw("Receiver is not a role-account wallet")

	log = frappe.get_doc(
		{
			"doctype": "System Transfer Log",
			"from_wallet": from_wallet_id,
			"to_wallet": to_wallet_id,
			"amount_usd": amount,
			"memo": memo,
			"status": "Draft",
			"initiated_by": frappe.session.user,
		}
	)
	log.insert(ignore_permissions=True)
	frappe.db.commit()

	client = IbexClient()
	try:
		invoice = client.add_invoice(to_wallet_id, amount, memo=memo)
		bolt11 = (invoice.get("invoice") or {}).get("bolt11")
		if not bolt11:
			raise ValueError(f"IBEX add_invoice returned no bolt11: {str(invoice)[:200]}")
		payment = client.pay_invoice(from_wallet_id, bolt11)
	except Exception as e:
		log.db_set("status", "Failed")
		log.db_set("error", str(e)[:500])
		frappe.db.commit()
		raise
	log.db_set("status", "Paid")
	log.db_set("ibex_payment_hash", frappe.utils.cstr(payment.get("hash") or "")[:140])
	audit_log(
		"system_transfer",
		"System Transfer Log",
		log.name,
		{"from": from_wallet_id, "to": to_wallet_id, "amount_usd": amount},
	)
	return {"success": True, "log": log.name, "payment": payment}
