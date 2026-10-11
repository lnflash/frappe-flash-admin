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


def _run_instructions(text):
	"""Every RUN instruction in ``text``, with line continuations joined."""
	chains = []
	for block in text.split("\nRUN ")[1:]:
		lines = []
		for line in block.splitlines():
			lines.append(line.strip().rstrip("\\").strip())
			if not line.rstrip().endswith("\\"):
				break
		chains.append(" ".join(lines))
	return chains


def _build_chain(text):
	"""The RUN instruction that runs ``bench build``, whatever else the file runs."""
	chain = next((c for c in _run_instructions(text) if BUILD_CMD in c), None)
	assert chain is not None, f"no RUN instruction contains {BUILD_CMD!r}"
	return chain


def _run_chain():
	return _build_chain(DOCKERFILE)


def _ln_segment(chain):
	"""The ``ln -sfn`` command in an ``&&`` chain, split into tokens."""
	segments = [seg.split() for seg in chain.split("&&")]
	matches = [seg for seg in segments if seg[:2] == ["ln", "-sfn"]]
	assert len(matches) == 1, f"expected exactly one ln -sfn in the chain, got {len(matches)}"
	return matches[0]


def test_build_chain_is_found_among_other_run_instructions():
	# An unrelated RUN (before or after) must not break the link contract.
	text = (
		"FROM base\n"
		"RUN apt-get update && apt-get install -y curl\n"
		f"RUN bench get-app x && \\\n    {BUILD_CMD} && \\\n    {LN_CMD}\n"
		"RUN echo done\n"
	)
	chain = _build_chain(text)
	assert chain.startswith("bench get-app x")
	assert f"{BUILD_CMD} && {LN_CMD}" in chain


def test_assets_link_runs_after_bench_build():
	chain = _run_chain()
	assert BUILD_CMD in chain
	assert LN_CMD in chain
	assert chain.index(LN_CMD) > chain.index(BUILD_CMD)
	# Chained with && so a failed link fails the whole layer.
	assert f"{BUILD_CMD} && {LN_CMD}" in chain


def test_assets_link_targets_image_assets_not_sites():
	# sites/ is shadowed by the PVC; a link written there never reaches nginx.
	ln = _ln_segment(_run_chain())
	assert ln[-2:] == [LINK_TARGET, LINK_PATH]
	assert "/sites/assets/admin_panel" not in _run_chain()


def test_ln_segment_reads_the_destination_from_the_chain():
	# Guards the parser itself: a wrong destination must be seen as wrong.
	chain = f"{BUILD_CMD} && ln -sfn {LINK_TARGET} {BENCH}/sites/assets/admin_panel && true"
	assert _ln_segment(chain)[-1] == f"{BENCH}/sites/assets/admin_panel"
	assert _ln_segment(chain)[-1] != LINK_PATH


def test_build_asserts_link_is_a_symlink_that_resolves():
	# ln -sfn onto a real directory nests the link instead of replacing it;
	# these fail the image build in that case and when the JS is missing.
	chain = _run_chain()
	is_link = f"test -L {LINK_PATH}"
	resolves = f"test -f {LINK_PATH}/js/back_to_dashboard.js"
	assert f"{LN_CMD} && {is_link} && {resolves}" in chain
	assert (REPO_ROOT / "admin_panel" / "public" / "js" / "back_to_dashboard.js").is_file()
