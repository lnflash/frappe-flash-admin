"""Bulk wallet-balance census (ENG-487).

Answers the operational questions that required hand-rolled mongo + jumpbox
scripts during the USDT cutover: which accounts hold money, what the total USD
float is, who a given funded account is.

The full scan pages through every IBEX org account (~5 min), so it runs as a
background job that writes a `Wallet Census Snapshot` DocType. The page reads
the latest snapshot and can trigger a fresh run.

`build_census` is a pure function (no IO) — all join / bucket / totals logic
lives there and is unit-tested against fixtures. The IO-bound `run_census_job`
just gathers inputs (IBEX + mongo), calls it, and persists the result.
"""

import json
import time

import frappe

from .auth import require_admin
from .census_core import build_census
from .ibex_client import IbexClient
from .mongo_reader import load_accounts, load_migrations, load_wallets

__all__ = [
	"build_census",
	"get_census_status",
	"get_latest_census",
	"run_census_job",
	"start_census",
]


# ── Whitelisted endpoints ─────────────────────────────────────────────────


@frappe.whitelist()
@require_admin()
def start_census():
	"""Create a snapshot row and enqueue the long-running scan. Returns its name.

	If a run is already in flight, return it instead of starting a duplicate
	(the scan takes minutes and hits the IBEX API for every account).
	"""
	running = _latest_snapshot_name(status="Running")
	if running:
		return {"snapshot": running, "status": "Running", "already_running": True}

	snapshot = frappe.new_doc("Wallet Census Snapshot")
	snapshot.status = "Running"
	snapshot.started_at = frappe.utils.now_datetime()
	snapshot.insert(ignore_permissions=True)
	frappe.db.commit()

	frappe.enqueue(
		"admin_panel.api.census.run_census_job",
		queue="long",
		timeout=1800,
		snapshot_name=snapshot.name,
	)
	return {"snapshot": snapshot.name, "status": "Running"}


@frappe.whitelist()
@require_admin()
def get_census_status(snapshot=None):
	"""Return status + progress for a snapshot (latest if none given)."""
	name = snapshot or _latest_snapshot_name()
	if not name:
		return {"snapshot": None, "status": "None"}
	doc = frappe.get_doc("Wallet Census Snapshot", name)
	return {
		"snapshot": doc.name,
		"status": doc.status,
		"started_at": str(doc.started_at) if doc.started_at else None,
		"completed_at": str(doc.completed_at) if doc.completed_at else None,
		"scanned_pages": doc.scanned_pages,
		"scanned_accounts": doc.scanned_accounts,
		"error": doc.error,
	}


@frappe.whitelist()
@require_admin()
def get_latest_census():
	"""Return the most recent completed snapshot's full result payload."""
	name = _latest_snapshot_name(status="Complete")
	if not name:
		return {"snapshot": None}
	doc = frappe.get_doc("Wallet Census Snapshot", name)
	return {
		"snapshot": doc.name,
		"status": doc.status,
		"started_at": str(doc.started_at) if doc.started_at else None,
		"completed_at": str(doc.completed_at) if doc.completed_at else None,
		"totals": json.loads(doc.totals_json or "{}"),
		"bucket_counts": json.loads(doc.bucket_counts_json or "{}"),
		"rows": json.loads(doc.rows_json or "[]"),
	}


def _latest_snapshot_name(status=None):
	filters = {"status": status} if status else None
	names = frappe.get_all(
		"Wallet Census Snapshot",
		filters=filters,
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	return names[0] if names else None


# ── Background job (IO) ───────────────────────────────────────────────────


def run_census_job(snapshot_name):
	"""Gather IBEX + mongo inputs, build the census, persist it to the snapshot."""
	doc = frappe.get_doc("Wallet Census Snapshot", snapshot_name)
	started = time.time()
	try:
		client = IbexClient()

		def _progress(pages, seen):
			# Persist progress so the page's status poll can show a live count.
			frappe.db.set_value(
				"Wallet Census Snapshot",
				snapshot_name,
				{"scanned_pages": pages, "scanned_accounts": seen},
				update_modified=False,
			)
			frappe.db.commit()

		ibex_accounts = list(client.iter_all_accounts(progress_cb=_progress))

		wallets = load_wallets()
		accounts = load_accounts()
		migrations = load_migrations()

		result = build_census(ibex_accounts, wallets, accounts, migrations)
		totals = result["totals"]

		doc.reload()
		doc.status = "Complete"
		doc.completed_at = frappe.utils.now_datetime()
		doc.total_accounts = totals["accounts"]
		doc.funded_count = totals["funded"]
		doc.zero_count = totals["zero"]
		doc.usd_total = totals["usd"]["balance"]
		doc.usdt_total = totals["usdt"]["balance"]
		doc.duration_seconds = round(time.time() - started, 1)
		doc.totals_json = json.dumps(totals)
		doc.bucket_counts_json = json.dumps(result["bucket_counts"])
		doc.rows_json = json.dumps(result["rows"])
		doc.save(ignore_permissions=True)
		frappe.db.commit()
	except Exception as exc:
		frappe.logger().error(f"Wallet census {snapshot_name} failed: {exc}")
		doc.reload()
		doc.status = "Failed"
		doc.completed_at = frappe.utils.now_datetime()
		doc.error = str(exc)[:500]
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		raise
