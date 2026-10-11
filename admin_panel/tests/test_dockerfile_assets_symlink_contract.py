"""Contract tests for the admin_panel assets link baked into the image.

Why this exists (ENG-643): on the k8s ``sites-dir`` PVC, ``sites/assets`` is a
symlink into the image's own ``/home/frappe/frappe-bench/assets`` dir, so each
pod serves its own copy. The after_migrate heal only wrote ``admin_panel`` into
the migrate pod, and ``/assets/admin_panel/*`` 404'd on TEST and PROD. The
Dockerfile now bakes the link into the image; these pin that line as text.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (REPO_ROOT / "Dockerfile").read_text()

BENCH = "/home/frappe/frappe-bench"
LINK_TARGET = f"{BENCH}/apps/admin_panel/admin_panel/public"
LINK_PATH = f"{BENCH}/assets/admin_panel"
LN_CMD = f"ln -sfn {LINK_TARGET} {LINK_PATH}"
BUILD_CMD = "bench build --apps admin_panel"


def _run_chain():
	"""The single RUN instruction, with line continuations joined."""
	runs = [block for block in DOCKERFILE.split("\nRUN ")[1:]]
	assert len(runs) == 1, "expected exactly one RUN instruction"
	lines = []
	for line in runs[0].splitlines():
		lines.append(line.strip().rstrip("\\").strip())
		if not line.rstrip().endswith("\\"):
			break
	return " ".join(lines)


def test_dockerfile_bakes_admin_panel_assets_link():
	assert LN_CMD in DOCKERFILE


def test_assets_link_runs_after_bench_build():
	chain = _run_chain()
	assert BUILD_CMD in chain
	assert LN_CMD in chain
	assert chain.index(LN_CMD) > chain.index(BUILD_CMD)
	# Chained with && so a failed link fails the whole layer.
	assert f"{BUILD_CMD} && {LN_CMD}" in chain


def test_assets_link_targets_image_assets_not_sites():
	# sites/ is shadowed by the PVC; a link written there never reaches nginx.
	assert LN_CMD.split()[-1] == LINK_PATH
	assert "/sites/assets/admin_panel" not in _run_chain()


def test_build_asserts_link_is_a_symlink_that_resolves():
	# ln -sfn onto a real directory nests the link instead of replacing it;
	# these fail the image build in that case and when the JS is missing.
	chain = _run_chain()
	is_link = f"test -L {LINK_PATH}"
	resolves = f"test -f {LINK_PATH}/js/back_to_dashboard.js"
	assert f"{LN_CMD} && {is_link} && {resolves}" in chain
	assert (REPO_ROOT / "admin_panel" / "public" / "js" / "back_to_dashboard.js").is_file()
