"""after_migrate clears frappe's shared asset-manifest cache.

frappe's get_assets_json caches the manifest under a shared redis key that no
deploy step invalidates, so after a build that changes bundle hashes every
page linked old-hash CSS/JS that 404'd (prod after v1.30.0, 2026-10-07) until
the key was deleted by hand.
"""

import ast
import types
from pathlib import Path

from idv_stubs import frappe

from admin_panel.admin_panel import setup

SETUP_PY = Path(__file__).resolve().parents[1] / "admin_panel" / "setup.py"


def test_clears_the_shared_manifest_keys(monkeypatch):
	calls = []
	cache = types.SimpleNamespace(delete_value=lambda keys, **kwargs: calls.append((list(keys), kwargs)))
	monkeypatch.setattr(frappe, "cache", cache, raising=False)

	setup.clear_shared_assets_manifest()

	# shared=True: the key lives in the cross-site namespace; a site-scoped
	# delete (what `bench clear-cache` does) misses it.
	assert calls == [(["assets_json", "assets_json_rtl"], {"shared": True})]


def test_a_cache_failure_is_logged_and_never_fails_the_migrate(monkeypatch):
	def unreachable(*args, **kwargs):
		raise ConnectionError("cache unreachable")

	logged = []
	monkeypatch.setattr(frappe, "cache", types.SimpleNamespace(delete_value=unreachable), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	monkeypatch.setattr(
		frappe, "log_error", lambda title=None, message=None: logged.append((title, message)), raising=False
	)

	setup.clear_shared_assets_manifest()

	assert logged == [("Could not clear the shared asset manifest cache", "traceback")]


def test_even_a_failed_log_never_fails_the_migrate(monkeypatch):
	def boom(*args, **kwargs):
		raise RuntimeError("down")

	monkeypatch.setattr(frappe, "cache", types.SimpleNamespace(delete_value=boom), raising=False)
	monkeypatch.setattr(frappe, "get_traceback", lambda: "traceback", raising=False)
	monkeypatch.setattr(frappe, "log_error", boom, raising=False)

	setup.clear_shared_assets_manifest()


def test_after_migrate_clears_the_manifest_last():
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
