"""Per-customer detail view (ENG-487).

Assembles a single customer's full picture from the same direct IBEX + mongo
path the census uses: identity + devices/contacts + migration history (mongo),
each wallet's **live** IBEX balance, and recent IBEX transactions. Backs the
detail panel opened from a census row, and a standalone search.

Account Hub already covers GraphQL-based identity/merchant tools — the census
detail panel links out to it rather than duplicating them.
"""

import frappe

from .auth import require_admin
from .census_core import CURRENCY_BY_ID
from .common import handle_api_errors
from .ibex_client import IbexClient
from .mongo_reader import customer_bundle, find_account

__all__ = ["get_customer_detail"]


@frappe.whitelist()
@require_admin()
@handle_api_errors
def get_customer_detail(query, tx_limit=25):
	"""Resolve a customer by username / phone / accountId / wallet id and return
	identity + wallets (with live IBEX balance) + migration state + recent
	transactions. `{"found": False}` if no account matches.
	"""
	query = frappe.utils.cstr(query).strip()
	tx_limit = max(1, min(frappe.utils.cint(tx_limit) or 25, 100))

	if not frappe.conf.get("customer_mongo_uri"):
		return {"found": False, "error": "customer_mongo_uri is not configured"}

	account = find_account(query)
	if not account:
		return {"found": False, "query": query}

	bundle = customer_bundle(account)
	client = IbexClient()

	# Live IBEX balance per wallet (wallet id == IBEX account id).
	for wallet in bundle["wallets"]:
		details = client.get_account_details(wallet["wallet_id"])
		raw = details.get("balance")
		wallet["live_balance"] = float(raw) if raw else 0.0
		wallet["balance_not_found"] = bool(details.get("not_found"))

	# Recent transactions for the default wallet (fall back to the first wallet).
	default_wallet_id = bundle["identity"].get("default_wallet_id")
	tx_wallet = default_wallet_id or (bundle["wallets"][0]["wallet_id"] if bundle["wallets"] else None)
	transactions = []
	if tx_wallet:
		for tx in client.get_account_transactions(tx_wallet, limit=tx_limit):
			transactions.append(
				{
					"id": tx.get("id"),
					"created_at": tx.get("createdAt"),
					"amount": tx.get("amount"),
					"network_fee": tx.get("networkFee"),
					"currency": CURRENCY_BY_ID.get(tx.get("currencyId")),
					"type_id": tx.get("transactionTypeId"),
				}
			)

	return {
		"found": True,
		"identity": bundle["identity"],
		"wallets": bundle["wallets"],
		"migrations": bundle["migrations"],
		"devices": bundle["devices"],
		"contacts": bundle["contacts"],
		"transactions": transactions,
		"tx_wallet_id": tx_wallet,
	}
