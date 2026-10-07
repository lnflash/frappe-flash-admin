"""frappe's shared asset-manifest cache heals itself after a deploy.

frappe.utils.get_assets_json caches the merged assets.json + assets-rtl.json
under one shared, never-expiring key, and every page links its CSS/JS through
it. ``bench migrate`` deletes that key as it starts, but an old-image process
still alive during the rolling update re-caches its OLD manifest afterwards,
so every page links bundle hashes the new image does not ship (both envs
2026-08-31, prod 2026-10-07).

heal_stale_assets_manifest (scheduler, every minute) deletes the key whenever
it is not this image's manifest; clear_shared_assets_manifest is the
after_migrate backup. They run against stand-ins for the slice of frappe they
touch: the shared cache, read_file / parse_json (frappe v15 semantics) and
cache_manager.bench_cache_keys.
"""

import ast
import importlib
import json
import sys
import types
from pathlib import Path

import pytest
from idv_stubs import frappe

from admin_panel.admin_panel import setup

ADMIN_PANEL = Path(__file__).resolve().parents[1]
SETUP_PY = ADMIN_PANEL / "admin_panel" / "setup.py"
HOOKS_PY = ADMIN_PANEL / "hooks.py"

# Real entries: controls.bundle.js is XTQ4CE6N in the v1.30.1 image (frappe
# 15.121.3) and RG3B2JBD in v1.23.0 (frappe 15.118.0).
SHIPPED_LTR = {
	"controls.bundle.js": "/assets/frappe/dist/js/controls.bundle.XTQ4CE6N.js",
	"desk.bundle.js": "/assets/frappe/dist/js/desk.bundle.KR73TTV3.js",
}
SHIPPED_RTL = {"rtl_desk.bundle.css": "/assets/frappe/dist/css-rtl/desk.bundle.XW33JWA6.css"}
# What get_assets_json caches on the new image: assets.json updated with assets-rtl.json.
SHIPPED = {**SHIPPED_LTR, **SHIPPED_RTL}
OLD_IMAGE = {**SHIPPED, "controls.bundle.js": "/assets/frappe/dist/js/controls.bundle.RG3B2JBD.js"}


class SharedCache:
	"""RedisWrapper's get_value / delete_value over the shared (cross-site) keys.

	A site-scoped call (shared=False) gets a site-prefixed key in frappe, so here
	it never sees or touches the shared ones.
	"""

	def __init__(self, keys=None):
		self.keys = dict(keys or {})
		self.deletes = []

	def get_value(self, key, generator=None, user=None, expires=False, shared=False):
		val = self.keys.get(key) if shared else None
		if val is None and generator:
			val = generator()
			if shared:
				self.keys[key] = val
		return val

	def delete_value(self, keys, user=None, make_keys=True, shared=False):
		self.deletes.append((keys, {"shared": shared}))
		if shared:
			for key in keys:
				self.keys.pop(key, None)


class RedisTimeoutError(Exception):
	"""Stands in for redis.exceptions.TimeoutError, which RedisWrapper.delete_value
	lets through. It swallows only redis.exceptions.ConnectionError (a sibling,
	not a parent), so an unreachable cache never reaches our except at all."""


def read_file(path):
	"""frappe.read_file: the file's text, or None when there is no such file."""
	return Path(path).read_text() if Path(path).exists() else None


def parse_json(val):
	"""frappe.parse_json: decode a string, pass anything else through."""
	return json.loads(val) if isinstance(val, str) else val


@pytest.fixture
def bench(monkeypatch, tmp_path):
	"""A worker of the NEW image: cwd is sites/, and sites/assets is its own build."""
	sites = tmp_path / "sites"
	(sites / "assets").mkdir(parents=True)
	monkeypatch.chdir(sites)
	monkeypatch.setattr(frappe, "read_file", read_file, raising=False)
	monkeypatch.setattr(frappe, "parse_json", parse_json, raising=False)

	cache_manager = types.ModuleType("frappe.cache_manager")
	cache_manager.bench_cache_keys = ("assets_json",)
	monkeypatch.setitem(sys.modules, "frappe.cache_manager", cache_manager)

	def ship(ltr=SHIPPED_LTR, rtl=SHIPPED_RTL):
		if ltr is not None:
			(sites / "assets" / "assets.json").write_text(json.dumps(ltr))
		if rtl is not None:
			(sites / "assets" / "assets-rtl.json").write_text(json.dumps(rtl))

	def cache(**keys):
		shared = SharedCache(keys)
		monkeypatch.setattr(frappe, "cache", shared, raising=False)
		return shared

	return types.SimpleNamespace(ship=ship, cache=cache, bench_cache_keys=cache_manager.bench_cache_keys)


# ── heal_stale_assets_manifest (the scheduler job) ───────────────────────


def test_heal_deletes_a_manifest_the_old_image_cached(bench):
	bench.ship()
	cache = bench.cache(assets_json=OLD_IMAGE)

	setup.heal_stale_assets_manifest()

	assert "assets_json" not in cache.keys  # the next render rebuilds it from this image
	assert cache.deletes == [(bench.bench_cache_keys, {"shared": True})]


def test_heal_leaves_this_images_own_manifest_alone(bench):
	"""The cached value includes the RTL entries, so this also proves the
	shipped manifest is merged the way get_assets_json merges it."""
	bench.ship()
	cache = bench.cache(assets_json=SHIPPED)

	setup.heal_stale_assets_manifest()

	assert cache.keys == {"assets_json": SHIPPED}
	assert cache.deletes == []


def test_heal_deletes_when_only_an_rtl_bundle_changed(bench):
	bench.ship()
	stale_rtl = {**SHIPPED, "rtl_desk.bundle.css": "/assets/frappe/dist/css-rtl/desk.bundle.OLDHASH0.css"}
	cache = bench.cache(assets_json=stale_rtl)

	setup.heal_stale_assets_manifest()

	assert "assets_json" not in cache.keys


def test_heal_deletes_an_empty_cached_manifest(bench):
	"""{} is broken, not absent: bundled_asset falls back to the unhashed
	bundle name for every link, and each one 404s."""
	bench.ship()
	cache = bench.cache(assets_json={})

	setup.heal_stale_assets_manifest()

	assert "assets_json" not in cache.keys


def test_heal_never_writes_an_absent_key(bench):
	"""Run on an old-image worker mid-rollout, a write would cache the OLD
	manifest. Absent stays absent; the next render builds it."""
	bench.ship()
	cache = bench.cache()

	setup.heal_stale_assets_manifest()

	assert cache.keys == {}
	assert cache.deletes == []


@pytest.mark.parametrize(
	"ltr,rtl",
	[(None, None), (None, SHIPPED_RTL), ({}, None)],
	ids=["no-manifest", "rtl-only", "empty-manifest"],
)
def test_heal_does_nothing_without_a_manifest_to_compare(bench, ltr, rtl):
	bench.ship(ltr=ltr, rtl=rtl)
	cache = bench.cache(assets_json=OLD_IMAGE)

	setup.heal_stale_assets_manifest()

	assert cache.keys == {"assets_json": OLD_IMAGE}
	assert cache.deletes == []


def test_heal_is_scheduled_every_minute_and_is_not_an_endpoint():
	tree = ast.parse(HOOKS_PY.read_text())
	assign = next(
		n
		for n in ast.walk(tree)
		if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "scheduler_events" for t in n.targets)
	)
	[path] = ast.literal_eval(assign.value)["cron"]["* * * * *"]
	module, _, name = path.rpartition(".")
	assert getattr(importlib.import_module(module), name) is setup.heal_stale_assets_manifest

	fn = next(
		n
		for n in ast.parse(SETUP_PY.read_text()).body
		if isinstance(n, ast.FunctionDef) and n.name == "heal_stale_assets_manifest"
	)
	assert fn.decorator_list == []  # not @frappe.whitelist(): nothing calls it over HTTP


# ── clear_shared_assets_manifest (the after_migrate backup) ──────────────


def test_clear_deletes_frappes_own_bench_cache_keys_shared(bench):
	cache = bench.cache(assets_json=OLD_IMAGE)

	setup.clear_shared_assets_manifest()

	# frappe's own tuple (clear_global_cache deletes the same one), not a
	# copy; shared=True, because a site-scoped delete misses the key.
	[(keys, kwargs)] = cache.deletes
	assert keys is bench.bench_cache_keys
	assert kwargs == {"shared": True}
	assert cache.keys == {}


def test_a_redis_timeout_is_logged_and_never_fails_the_migrate(bench, monkeypatch):
	attempted = []

	def timeout(keys, **kwargs):
		attempted.append((keys, kwargs))
		raise RedisTimeoutError("Timeout reading from socket")

	logged = []
	monkeypatch.setattr(frappe, "cache", types.SimpleNamespace(delete_value=timeout), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	monkeypatch.setattr(
		frappe, "log_error", lambda title=None, message=None: logged.append((title, message)), raising=False
	)

	setup.clear_shared_assets_manifest()

	assert attempted == [(bench.bench_cache_keys, {"shared": True})]
	assert logged == [("Could not clear the shared asset manifest cache", "traceback")]


def test_a_frappe_without_bench_cache_keys_is_logged_not_raised(bench, monkeypatch):
	monkeypatch.setitem(sys.modules, "frappe.cache_manager", types.ModuleType("frappe.cache_manager"))
	cache = bench.cache(assets_json=OLD_IMAGE)
	logged = []
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	monkeypatch.setattr(
		frappe, "log_error", lambda title=None, message=None: logged.append((title, message)), raising=False
	)

	setup.clear_shared_assets_manifest()

	assert cache.deletes == []
	assert logged == [("Could not clear the shared asset manifest cache", "traceback")]


def test_even_a_failed_log_never_fails_the_migrate(bench, monkeypatch):
	def boom(*args, **kwargs):
		raise RuntimeError("down")

	monkeypatch.setattr(frappe, "cache", types.SimpleNamespace(delete_value=boom), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	monkeypatch.setattr(frappe, "log_error", boom, raising=False)

	setup.clear_shared_assets_manifest()


def test_after_migrate_clears_the_manifest_last():
	"""Last, so nothing else in after_migrate runs after it. That only narrows
	the window: an old-image process can still re-cache after this returns,
	which is why heal_stale_assets_manifest exists."""
	tree = ast.parse(SETUP_PY.read_text())
	fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "after_migrate")
	calls = [
		node.value.func.id
		for node in fn.body
		if isinstance(node, ast.Expr)
		and isinstance(node.value, ast.Call)
		and isinstance(node.value.func, ast.Name)
	]
	assert calls[-1] == "clear_shared_assets_manifest"
