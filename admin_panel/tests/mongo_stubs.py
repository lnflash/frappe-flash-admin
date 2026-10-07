"""Shared in-memory Mongo helpers for the tests that run mongo_reader.

A fake collection that hands back whole seeded documents hides a projection
bug: a reader that projects the wrong field still reads it in the test, while
real Mongo leaves it out (``KeyError``, or a silently empty value). Fakes
built on ``mongo_project`` return only what the projection asks for, like the
server, so that bug fails here too.
"""


def mongo_project(doc, projection):
	"""What Mongo returns for an inclusion projection: ``_id`` plus only the
	projected fields, a dotted path keeping just that part of its subdocument."""
	if projection is None:
		return dict(doc)
	out = {"_id": doc["_id"]} if "_id" in doc and projection.get("_id", 1) else {}
	for path, keep in projection.items():
		if not keep or path == "_id":
			continue
		*parents, leaf = path.split(".")
		src, dst = doc, out
		for key in parents:
			if not isinstance(src.get(key), dict):
				break
			src, dst = src[key], dst.setdefault(key, {})
		else:
			if leaf in src:
				dst[leaf] = src[leaf]
	return out
