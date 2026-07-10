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
from .common import handle_api_errors
from .ibex_client import IbexClient
from .mongo_reader import load_accounts, load_migrations, load_wallets

__all__ = [
	"build_census",
	"get_census_status",
	"get_latest_census",
	"run_census_job",
	"run_census_now",
	"start_census",
]

# A Running snapshot older than this is a dead run (beyond the 30-min job
# timeout) — mark it Failed instead of blocking new scans forever.
STALE_RUN_SECONDS = 2700

# How many snapshots to retain; older ones are purged after a successful run
# (rows_json holds the full per-account table, so rows are large).
KEEP_SNAPSHOTS = 20


# ── Whitelisted endpoints ─────────────────────────────────────────────────


@frappe.whitelist()
@require_admin()
@handle_api_errors
def start_census():
	"""Create a snapshot row and enqueue the long-running scan. Returns its name.

	If a run is already in flight, return it instead of starting a duplicate
	(the scan takes minutes and hits the IBEX API for every account).
	"""
	running = _resolve_running_snapshot()
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


def run_census_now():
	"""Create a snapshot and run the scan **synchronously** (no worker needed).

	Deliberately NOT whitelisted — bench-execute / console only, because it
	blocks the caller for the full scan. `start_census` enqueues onto the
	`long` queue, which requires a background worker. Deployments without one
	(e.g. the local docker-compose, or a `bench execute` smoke test) can call
	this instead — it blocks until the scan finishes and returns the resulting
	status. Fine for sandbox / small orgs; a full prod scan takes minutes and
	should use the queued path.
	"""
	running = _resolve_running_snapshot()
	if running:
		return get_census_status(running)

	snapshot = frappe.new_doc("Wallet Census Snapshot")
	snapshot.status = "Running"
	snapshot.started_at = frappe.utils.now_datetime()
	snapshot.insert(ignore_permissions=True)
	frappe.db.commit()
	run_census_job(snapshot.name)
	return get_census_status(snapshot.name)


@frappe.whitelist()
@require_admin()
@handle_api_errors
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
@handle_api_errors
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


def _resolve_running_snapshot():
	"""Return the name of a genuinely live Running snapshot, or None.

	A Running row whose worker died (deploy, OOM, kill) never flips to Failed
	and would block new runs forever. If the latest Running snapshot is older
	than STALE_RUN_SECONDS (or has no started_at), mark it Failed so the
	caller can start a fresh scan.
	"""
	running = _latest_snapshot_name(status="Running")
	if not running:
		return None

	started_at = frappe.db.get_value("Wallet Census Snapshot", running, "started_at")
	if started_at:
		age = frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), started_at)
		if age <= STALE_RUN_SECONDS:
			return running

	frappe.db.set_value(
		"Wallet Census Snapshot",
		running,
		{
			"status": "Failed",
			"error": "Marked stale by start_census: run exceeded timeout",
			"completed_at": frappe.utils.now_datetime(),
		},
		update_modified=False,
	)
	frappe.db.commit()
	return None


def _purge_old_snapshots(keep=KEEP_SNAPSHOTS):
	"""Hard-delete snapshots beyond the newest `keep` to bound table growth."""
	names = frappe.get_all(
		"Wallet Census Snapshot",
		order_by="creation desc",
		pluck="name",
	)
	for name in names[keep:]:
		frappe.delete_doc(
			"Wallet Census Snapshot", name, ignore_permissions=True, force=True, delete_permanently=True
		)


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

		# The mongo join enriches rows with username / status / migration state.
		# If it isn't configured (e.g. an IBEX-only sandbox smoke test), still
		# produce the census from IBEX alone — rows just lack those fields.
		if frappe.conf.get("customer_mongo_uri"):
			wallets = load_wallets()
			accounts = load_accounts()
			migrations = load_migrations()
		else:
			frappe.logger().warning(
				f"Wallet census {snapshot_name}: customer_mongo_uri not configured — "
				"running IBEX-only (no username/status/migration join)."
			)
			wallets, accounts, migrations = {}, {}, {}

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

		# Best-effort retention — a purge failure must not fail the run.
		try:
			_purge_old_snapshots()
		except Exception as purge_exc:
			frappe.logger().warning(f"Wallet census {snapshot_name}: snapshot purge failed: {purge_exc}")
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
