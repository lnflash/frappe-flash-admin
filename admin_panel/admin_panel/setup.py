import logging
import os
import sys

import frappe

from admin_panel.admin_panel.doctype.allowed_country.seed import seed_allowed_countries
from admin_panel.api.compliance_audit import seed_chain_genesis


def after_migrate():
	ensure_roles()
	ensure_service_account_roles()
	sync_pages()
	delete_legacy_pages()
	ensure_desk_home_page()
	ensure_public_assets_symlink()
	seed_allowed_countries()
	seed_decision_reasons()
	seed_identity_document_types()
	seed_chain_genesis()
	# A backup only. The fix is heal_stale_assets_manifest on the scheduler.
	clear_shared_assets_manifest()


def ensure_roles():
	"""Create custom roles referenced by RBAC (admin_panel.api.auth) if missing.

	The Account Upgrade Request permissions and the require_admin decorator
	reference "Flash Admin"; without the Role record it cannot be assigned.
	"""
	# (role_name, desk_access) — "Support Lookup" gates the nostr-dm-bridge's
	# support contact relay (api.support_lookup); its service user never needs
	# the desk.
	for role_name, desk_access in (("Flash Admin", 1), ("Support Lookup", 0)):
		if not frappe.db.exists("Role", role_name):
			role = frappe.new_doc("Role")
			role.role_name = role_name
			role.desk_access = desk_access
			role.flags.ignore_permissions = True
			role.insert()
	frappe.db.commit()


# One Flash backend service-account User per environment (prod / test). Whichever
# exists on this site gets the roles; the other is simply absent. Optional
# `flash_service_account` site_config key overrides the list without a code change.
SERVICE_ACCOUNT_CANDIDATES = (
	"flash_sa@getflash.io",
	"flash-service-account@getflash.io",
)

# Flash Admin gates the admin_panel custom doctypes (Account Upgrade Request,
# Bank Account Update Request); Accounts Manager gates the standard ERPNext
# doctypes the flash backend reads (Bank Account, Currency Exchange, Customer,
# Journal Entry, Bank). Losing either breaks a slice of cashout/upgrade with 403s.
SERVICE_ACCOUNT_ROLES = ("Flash Admin", "Accounts Manager")


def ensure_service_account_roles():
	"""Idempotently re-assert the Flash backend service account's roles.

	Role *definitions* ship in doctype JSON (versioned); the role *assignment* on
	the User record is not, and has silently dropped before — breaking cashout and
	the upgrade flow with 403s. This runs on every ``bench migrate`` (via
	after_migrate), so the assignment self-heals on every deploy.
	"""
	configured = frappe.conf.get("flash_service_account")
	candidates = [configured] if configured else list(SERVICE_ACCOUNT_CANDIDATES)
	for email in candidates:
		if not email or not frappe.db.exists("User", email):
			continue
		existing = {
			r.role
			for r in frappe.get_all(
				"Has Role",
				filters={"parent": email, "parenttype": "User"},
				fields=["role"],
			)
		}
		missing = [r for r in SERVICE_ACCOUNT_ROLES if r not in existing]
		if not missing:
			continue  # already converged — no needless User.save() this migrate
		frappe.get_doc("User", email).add_roles(*missing)
	frappe.db.commit()


def sync_pages():
	pages = [
		{
			"name": "alert-users",
			"title": "Alert Users",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "account-management",
			"title": "Account Management",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "account-hub",
			"title": "Account Hub",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "admin-dashboard",
			"title": "Dashboard",
			"module": "Admin Panel",
			"standard": "Yes",
			# The ONLY page here that carries roles, and it is load-bearing:
			# this is the desk home page (see ensure_desk_home_page), and
			# boot.add_home_page falls back to the Workspaces view when
			# Page.is_permitted() says no. Role-gating the page is therefore
			# what gives every non-admin desk user their normal landing page
			# back, with no separate opt-out list to maintain. Mirrors
			# admin_panel.api.auth.ADMIN_ROLES.
			"roles": [
				{"role": "System Manager"},
				{"role": "Accounts Manager"},
				{"role": "Flash Admin"},
			],
		},
		{
			"name": "transfer-requests",
			"title": "Transfer Requests",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "system-accounts",
			"title": "System Accounts",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "wallet-census",
			"title": "Wallet Census",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "referral-rewards",
			"title": "Referral Rewards",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "bridge-kyc",
			"title": "Bridge KYC",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
	]

	for page_data in pages:
		name = page_data["name"]
		if frappe.db.exists("Page", name):
			doc = frappe.get_doc("Page", name)
			doc.update(page_data)
		else:
			doc = frappe.new_doc("Page")
			doc.update(page_data)

		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.save()

	frappe.db.commit()


def delete_legacy_pages():
	if frappe.db.exists("Page", "cashout-requests"):
		frappe.delete_doc("Page", "cashout-requests", ignore_permissions=True, force=True)
		frappe.db.commit()


# The Page that desk users land on at /app. Overridable per-site with the
# `desk_home_page` site_config key; set it to an empty value to opt out and
# keep Frappe's stock Workspaces landing.
DESK_HOME_PAGE = "admin-dashboard"


def ensure_desk_home_page():
	"""Make the Admin Dashboard the desk landing page.

	``frappe.boot.add_home_page`` reads the GLOBAL default ``desktop:home_page``
	and hands it to ``frappe.desk.desk_page.get``, falling back to the
	``Workspaces`` view on DoesNotExistError or PermissionError. So this one
	default plus the Page's roles is the whole mechanism: admins get the
	dashboard, everyone else keeps Workspaces, and no user record is touched.

	Re-asserted on every migrate so a restored or re-seeded site converges,
	and skipped when already correct so a deploy is a no-op.
	"""
	configured = frappe.conf.get("desk_home_page", DESK_HOME_PAGE)
	current = frappe.db.get_default("desktop:home_page")
	if not configured:
		# Opting out must also undo the default a previous migrate of this
		# app set — otherwise the opt-out is inert on any site that has
		# migrated once, and admins keep landing on the dashboard the
		# operator just asked to be rid of. Only our own value is cleared;
		# a page the operator chose themselves is left alone.
		if current == DESK_HOME_PAGE:
			frappe.defaults.clear_default("desktop:home_page", parent="__default")
			frappe.db.commit()
		return
	if current == configured:
		return
	frappe.db.set_default("desktop:home_page", configured)
	frappe.db.commit()


def _ensure_symlink(link, target):
	"""Idempotently point ``link`` at ``target``; leave a real directory alone.

	Pure helper (no frappe) so the branch logic is testable with tmp paths.
	Returns what it did: "created", "repointed", "ok", or "kept-dir".
	"""
	if os.path.islink(link):
		if os.readlink(link) == target:
			return "ok"
		os.remove(link)
		os.symlink(target, link)
		return "repointed"
	if os.path.isdir(link):
		# Some setups copy assets instead of symlinking; don't fight them.
		return "kept-dir"
	os.symlink(target, link)
	return "created"


def ensure_public_assets_symlink():
	"""Make ``sites/assets/admin_panel`` exist on the runtime volume.

	nginx serves ``/assets`` with ``root .../sites`` (``try_files $uri``), and
	in the k8s deployment ``sites/`` is the shared PVC mounted OVER the
	image's own sites dir. ``bench build`` wrote the assets symlink into the
	image layer at build time — exactly where nginx never looks — so the
	app's public files 404'd on every environment while frappe/erpnext
	(provisioned onto the volume at install) served fine. Runs on every
	migrate, which executes with the PVC mounted; harmless on a plain bench
	where the link already exists and is correct.
	"""
	bench_path = frappe.utils.get_bench_path()
	_ensure_symlink(
		os.path.join(bench_path, "sites", "assets", "admin_panel"),
		os.path.join(bench_path, "apps", "admin_panel", "admin_panel", "public"),
	)


# The key frappe.utils.get_assets_json caches the merged manifest under (a
# literal there). Only read here: deletes go through frappe's own key list.
ASSETS_JSON_KEY = "assets_json"
# This image's manifest, relative to sites/ (see _shipped_assets_manifest).
SHIPPED_MANIFEST = "assets/assets.json"

# The heal's log, set up like bridge_kyc_upgrade._logger. frappe.logger()
# drops INFO on the cluster (its level is ERROR off a dev server) and writes
# its files to a pod with no volume, so _logger raises the level and copies
# each line to stdout (support_lookup._audit_logger has the details). One
# handler object, attached by identity, so attaching it on every run is a no-op.
_STDOUT_HANDLER = logging.StreamHandler(sys.stdout)
_STDOUT_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))


def _logger():
	logger = frappe.logger("assets_manifest", max_size=1_000_000, file_count=5)
	logger.setLevel(logging.INFO)
	logger.addHandler(_STDOUT_HANDLER)
	return logger


def heal_stale_assets_manifest():
	"""Scheduler job, every minute: delete the cached asset manifest if this image did not ship it.

	frappe.utils.get_assets_json caches the merged assets.json + assets-rtl.json
	under one shared (cross-site), never-expiring key, and every page links its
	CSS/JS bundles through it. ``bench migrate`` already deletes that key as it
	starts (SiteMigration.setUp -> clear_global_cache). It still went stale
	after deploys (both envs 2026-08-31, prod 2026-10-07) because an old-image
	process re-cached its own manifest after that clear. The migrate Job runs
	alongside the rolling update, and every container resolves sites/assets to
	the manifest baked into its own image. So any old-image render writes the
	OLD manifest back: the old gunicorn rendering the maintenance page, or any
	page until its replacement is Ready, or an old long worker running the
	search-index rebuild the migrate enqueues. Pages then link bundle hashes
	the new image does not ship, and the CSS/JS 404s. A delete at any fixed
	point in the deploy can lose that race.

	This job does not depend on deploy timing. It deletes the key only when it
	differs from this worker's own manifest, and the next render rebuilds it.
	An old process still alive may cache its manifest again and the next run
	deletes that too. The first run after the last old process exits clears
	whatever is left, and from then on only the new image writes the key. It
	reads without a generator and never writes the key itself, so on an old
	worker mid-rollout the worst it can do is force one rebuild. It does
	nothing when the key matches or is absent.

	Scheduled Job Log says "Complete" after every run, delete or not, so the
	job logs through _logger. A delete logs one INFO line naming the first
	differing bundle both ways: cached= is the build that wrote the key,
	shipped= is this worker's own. A line whose shipped= is the release being
	deployed is the race. A line whose shipped= is the previous release comes
	from the outgoing worker, which runs this job too and deletes the new
	manifest until it is replaced, so count only the former.
	A key it cannot check, because this worker has no manifest of its own, is
	left alone with a WARNING on every run, since on that worker the heal is off.
	"""
	cached = frappe.cache.get_value(ASSETS_JSON_KEY, shared=True)
	if cached is None:
		return
	shipped = _shipped_assets_manifest()
	if not shipped:
		_logger().warning(
			"left the shared assets_json alone: no usable manifest at %s to check it against",
			os.path.abspath(SHIPPED_MANIFEST),
		)
		return
	if cached == shipped:
		return
	if clear_shared_assets_manifest():
		_logger().info("cleared the stale shared assets_json: %s", _manifest_difference(cached, shipped))


def _shipped_assets_manifest():
	"""This image's merged manifest, built the way get_assets_json builds it.

	The paths are relative to sites/, where every bench process runs and where
	sites/assets resolves to the assets baked into this container's image.
	None when there is no manifest to compare against.
	"""
	assets = frappe.parse_json(frappe.read_file(SHIPPED_MANIFEST))
	if not assets:
		return None
	if assets_rtl := frappe.read_file("assets/assets-rtl.json"):
		assets.update(frappe.parse_json(assets_rtl))
	return assets


def _manifest_difference(cached, shipped):
	"""The heal's evidence: how many entries differ, and the first one both ways.

	Runs after the delete, on whatever was cached, so it never raises on a
	value that is not a manifest.
	"""
	if not isinstance(cached, dict):
		return f"cached={type(cached).__name__} (not a manifest)"
	differing = [name for name in cached.keys() | shipped.keys() if cached.get(name) != shipped.get(name)]
	first = min(differing, key=str, default=None)
	return (
		f"differing_entries={len(differing)} first={first}"
		f" cached={cached.get(first)} shipped={shipped.get(first)}"
	)


def clear_shared_assets_manifest():
	"""Delete frappe's shared asset-manifest cache key. Never raises.

	A backup to heal_stale_assets_manifest, run at the end of every migrate.
	frappe already made this same delete when the migrate started, so it only
	helps when an old process re-cached the key during the migrate and is gone
	by its end. Pages then heal at once instead of on the next scheduler run
	(or at all, when the scheduler is not running). It uses frappe's own key
	list (cache_manager.bench_cache_keys), so it deletes what frappe deletes.

	Connection failures are silently skipped by frappe
	(RedisWrapper.delete_value swallows redis ConnectionError), so they still
	return True. Other redis errors, such as a timeout, are logged to the Error
	Log and return False, so the heal does not log them as a delete.
	"""
	try:
		from frappe.cache_manager import bench_cache_keys

		frappe.cache.delete_value(bench_cache_keys, shared=True)
	except Exception:
		try:
			frappe.log_error(
				title="Could not clear the shared asset manifest cache",
				message=frappe.get_traceback(),
			)
		except Exception:
			pass
		return False
	return True


# ── ID verification seed data ─────────────────────────────────────────────

# (code, outcome, label, user_facing_message). The message is what the user
# reads: plain language, says what to fix, never why we suspect them.
DECISION_REASONS = (
	(
		"APPROVE_VERIFIED",
		"approve",
		"Identity verified",
		"Your identity has been verified and your account has been upgraded.",
	),
	(
		"APPROVE_BRIDGE_KYC",
		"approve",
		"Verified via Bridge KYC",
		"Your identity was confirmed through your completed KYC and your account has been upgraded.",
	),
	(
		"REJECT_NAME_MISMATCH",
		"reject",
		"Name does not match",
		"The name on your ID does not match the name on your account. "
		"Update your account name to match your ID exactly, then apply again.",
	),
	(
		"REJECT_EXPIRED_DOCUMENT",
		"reject",
		"Document expired",
		"The ID you submitted has expired. Please apply again with a valid, unexpired ID.",
	),
	(
		"REJECT_DUPLICATE_DOCUMENT",
		"reject",
		"Document already used",
		"This ID is already linked to another account. If you believe this is a mistake, contact support.",
	),
	(
		"REJECT_SUSPECTED_FORGERY",
		"reject",
		"Document could not be authenticated",
		"We could not authenticate the ID you submitted. Please contact support.",
	),
	(
		"REJECT_SANCTIONS_HIT",
		"reject",
		"Sanctions screening",
		"We are unable to upgrade your account at this time. Please contact support.",
	),
	(
		"REJECT_UNSUPPORTED_DOCUMENT",
		"reject",
		"Document type not accepted",
		"We do not accept this type of ID. Please apply again with a passport, "
		"driver's licence or national ID card.",
	),
	(
		"REJECT_OTHER",
		"reject",
		"Other",
		"We were unable to approve your upgrade. Please contact support for details.",
	),
	(
		"RESUBMIT_BLURRY",
		"resubmit",
		"Photo too blurry",
		"Your ID photo is too blurry to read. Hold the camera steady in good light and try again.",
	),
	(
		"RESUBMIT_GLARE",
		"resubmit",
		"Glare on document",
		"There is glare covering part of your ID. Move away from direct light and try again.",
	),
	(
		"RESUBMIT_CROPPED",
		"resubmit",
		"Document cut off",
		"Part of your ID is cut off. Make sure all four corners are visible and try again.",
	),
	(
		"RESUBMIT_WRONG_DOCUMENT",
		"resubmit",
		"Wrong document",
		"The photo you sent is not an accepted ID. Please submit a passport, "
		"driver's licence or national ID card.",
	),
	(
		"RESUBMIT_SELFIE_MISSING",
		"resubmit",
		"Selfie missing",
		"We need a selfie to match against your ID. Please take a clear selfie and try again.",
	),
)


def seed_decision_reasons():
	"""Idempotently seed Decision Reason codes.

	Missing codes are inserted. Existing rows keep their operator-tuned label,
	message and active flag; only ``outcome`` is re-asserted, because the API
	validates a code's outcome against the action being taken.
	"""
	created = 0
	for code, outcome, label, message in DECISION_REASONS:
		if frappe.db.exists("Decision Reason", code):
			if frappe.db.get_value("Decision Reason", code, "outcome") != outcome:
				frappe.db.set_value("Decision Reason", code, "outcome", outcome)
			continue
		doc = frappe.new_doc("Decision Reason")
		doc.update(
			{
				"code": code,
				"outcome": outcome,
				"label": label,
				"user_facing_message": message,
				"active": 1,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert()
		created += 1
	frappe.db.commit()
	print(f"Decision Reason seed: {created} created, {len(DECISION_REASONS) - created} existing")


def _document_type(code, country, document_name, **overrides):
	row = {
		"code": code,
		"country": country,
		"document_name": document_name,
		"has_mrz": 0,
		"sides": "1",
		"base_confidence": 0.5,
		"enabled": 0,
		"sample_verified": 0,
		"vendor_extraction": 0,
		"template_keywords": "",
	}
	row.update(overrides)
	return row


def _passport(code, country):
	return _document_type(
		code,
		country,
		"Passport",
		has_mrz=1,
		enabled=1,
		base_confidence=0.9,
		template_keywords="PASSPORT\nP<",
	)


# ``country`` values are Frappe `Country` document names. A row whose country
# is missing on the site is skipped (logged), never fatal.
IDENTITY_DOCUMENT_TYPES = (
	_passport("JM_PASSPORT", "Jamaica"),
	_passport("KY_PASSPORT", "Cayman Islands"),
	_passport("TT_PASSPORT", "Trinidad and Tobago"),
	_passport("BB_PASSPORT", "Barbados"),
	_passport("BS_PASSPORT", "Bahamas"),
	_passport("SV_PASSPORT", "El Salvador"),
	_document_type(
		"JM_DRIVERS_LICENCE",
		"Jamaica",
		"Driver's Licence",
		sides="2",
		enabled=1,
		base_confidence=0.6,
		template_keywords="DRIVER'S LICENCE\nJAMAICA",
	),
	_document_type("JM_VOTER_ID", "Jamaica", "Voter ID", enabled=1, base_confidence=0.4),
	_document_type("JM_NIDS", "Jamaica", "National ID Card (NIDS)", sides="2"),
	_document_type("KY_DRIVERS_LICENCE", "Cayman Islands", "Driver's Licence", sides="2"),
	_document_type("TT_NATIONAL_ID", "Trinidad and Tobago", "National ID Card", sides="2"),
	_document_type("TT_DRIVERS_PERMIT", "Trinidad and Tobago", "Driver's Permit", sides="2"),
	_document_type("BB_NATIONAL_ID", "Barbados", "National ID Card", sides="2"),
	_document_type("BB_DRIVERS_LICENCE", "Barbados", "Driver's Licence", sides="2"),
	_document_type("BS_DRIVERS_LICENCE", "Bahamas", "Driver's Licence", sides="2"),
	_document_type("BS_VOTERS_CARD", "Bahamas", "Voter's Card"),
	_document_type(
		"SV_DUI",
		"El Salvador",
		"DUI (Documento Único de Identidad)",
		sides="2",
		enabled=1,
		base_confidence=0.6,
	),
)


def seed_identity_document_types():
	"""Idempotently seed the Identity Document Type registry.

	Insert-only: an existing code is left exactly as the operator has it
	(enabled / sample_verified / keywords are tuned in production). A row
	whose ``Country`` does not exist on this site is skipped with a log line
	so a missing country can never fail the migrate.
	"""
	created = skipped = existing = 0
	for row in IDENTITY_DOCUMENT_TYPES:
		if frappe.db.exists("Identity Document Type", row["code"]):
			existing += 1
			continue
		if not frappe.db.exists("Country", row["country"]):
			frappe.logger().warning(
				f"Identity Document Type seed: skipping {row['code']} — Country '{row['country']}' not found"
			)
			skipped += 1
			continue
		doc = frappe.new_doc("Identity Document Type")
		doc.update(row)
		doc.flags.ignore_permissions = True
		doc.insert()
		created += 1
	frappe.db.commit()
	print(f"Identity Document Type seed: {created} created, {existing} existing, {skipped} skipped")
