"""Read-only reader for the customer MongoDB (Galoy `galoy` database).

Loads the three collections the wallet census joins against IBEX accounts:
`wallets`, `accounts`, and `cashwalletmigrations`. Everything is bulk-loaded
into plain dicts keyed by the join field so the pure `census.build_census`
function can run without any IO.

Verified join keys (see census.py):
  IBEX account.id   == wallets.id
  IBEX account.name == str(accounts._id) == str(wallets._accountId)
                    == cashwalletmigrations.accountId

Config (site_config.json / frappe.conf):
  customer_mongo_uri   (required) — the MONGODB_CON connection string
  customer_mongo_db    (optional) — database name, defaults to "galoy"
"""

import frappe

_client = None


def _get_db():
	uri = frappe.conf.get("customer_mongo_uri")
	if not uri:
		raise ValueError("customer_mongo_uri is not configured in site_config.json")

	global _client
	if _client is None:
		# Imported lazily so the app loads even where pymongo isn't installed
		# (e.g. contract tests that never touch mongo).
		from pymongo import MongoClient

		_client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)

	db_name = frappe.conf.get("customer_mongo_db") or "galoy"
	return _client[db_name]


def _latest_status(status_history):
	"""Account status is the last entry of statusHistory (no flat field)."""
	if not status_history:
		return None
	return status_history[-1].get("status")


def load_wallets() -> dict:
	"""wallet id -> {account_id, currency, type}."""
	db = _get_db()
	out = {}
	cursor = db.wallets.find({}, {"id": 1, "_accountId": 1, "currency": 1, "type": 1})
	for doc in cursor:
		wid = doc.get("id")
		if not wid:
			continue
		out[wid] = {
			"account_id": str(doc["_accountId"]) if doc.get("_accountId") else None,
			"currency": doc.get("currency"),
			"type": doc.get("type"),
		}
	return out


def load_accounts() -> dict:
	"""str(account _id) -> {username, level, status, role, created_at, default_wallet_id, npub}."""
	db = _get_db()
	out = {}
	cursor = db.accounts.find(
		{},
		{
			"_id": 1,
			"username": 1,
			"level": 1,
			"role": 1,
			"statusHistory": 1,
			"defaultWalletId": 1,
			"created_at": 1,
			"npub": 1,
		},
	)
	for doc in cursor:
		out[str(doc["_id"])] = {
			"username": doc.get("username"),
			"level": doc.get("level"),
			"role": doc.get("role") or "user",
			"status": _latest_status(doc.get("statusHistory")),
			"default_wallet_id": doc.get("defaultWalletId"),
			"created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
			"npub": doc.get("npub"),
		}
	return out


def load_migrations() -> dict:
	"""accountId -> {status, run_id, completed_at}. Keeps the most recent run per account."""
	db = _get_db()
	out = {}
	cursor = db.cashwalletmigrations.find(
		{},
		{"accountId": 1, "status": 1, "runId": 1, "completedAt": 1, "updatedAt": 1},
	)
	for doc in cursor:
		account_id = doc.get("accountId")
		if not account_id:
			continue
		stamp = doc.get("completedAt") or doc.get("updatedAt")
		existing = out.get(account_id)
		if existing and existing["_stamp"] and stamp and stamp <= existing["_stamp"]:
			continue
		out[account_id] = {
			"status": doc.get("status"),
			"run_id": doc.get("runId"),
			"completed_at": doc.get("completedAt").isoformat() if doc.get("completedAt") else None,
			"_stamp": stamp,
		}
	# Drop the internal sort key before returning.
	for value in out.values():
		value.pop("_stamp", None)
	return out
