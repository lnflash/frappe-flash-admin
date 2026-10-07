"""mongo_reader's users ↔ accounts joins.

A users document names the Kratos identity ``userId``; the account stores the
same id as ``kratosUserId``. users has no ``kratosUserId`` field (prod: 0 of
7,184 documents on 2026-10-07), so these tests seed users exactly that way.
Querying users on ``kratosUserId`` matches nothing in them, as in prod, where
it left payer phones, phone search and the customer page's phone empty.

The fake collections filter and project like the server, so a reader that
projects the wrong users field gets it back missing here, as it would in prod.
"""

import types

import idv_stubs  # installs the frappe stub the api package imports
import pytest
from mongo_stubs import mongo_project

from admin_panel.api import mongo_reader


class FakeObjectId:
	"""The slice of bson.ObjectId mongo_reader uses (CI installs no pymongo)."""

	def __init__(self, value):
		self.value = str(value)

	@staticmethod
	def is_valid(value):
		return isinstance(value, str) and len(value) == 24 and all(c in "0123456789abcdef" for c in value)

	def __eq__(self, other):
		return isinstance(other, FakeObjectId) and other.value == self.value

	def __hash__(self):
		return hash(self.value)

	def __str__(self):
		return self.value


def _matches(doc, filters):
	for key, expected in filters.items():
		if key == "$or":
			if not any(_matches(doc, sub) for sub in expected):
				return False
			continue
		actual = doc.get(key)
		if isinstance(expected, dict) and "$in" in expected:
			if actual not in expected["$in"]:
				return False
		elif actual != expected:
			return False
	return True


class Cursor(list):
	def sort(self, key, direction=1):
		return Cursor(sorted(self, key=lambda d: d.get(key) or "", reverse=direction < 0))


class Collection:
	"""Filters, then projects each match with mongo_project, as Mongo does."""

	def __init__(self, docs):
		self.docs = docs

	def find(self, filters=None, projection=None):
		return Cursor(mongo_project(d, projection) for d in self.docs if _matches(d, filters or {}))

	def find_one(self, filters=None, projection=None):
		return next(iter(self.find(filters, projection)), None)


ACCOUNT_ID = "6a770f76f0452bcc2db47c43"
USER_ID = FakeObjectId("6a770f76f0452bcc2db47c44")


@pytest.fixture()
def db(monkeypatch):
	monkeypatch.setitem(__import__("sys").modules, "bson", types.SimpleNamespace(ObjectId=FakeObjectId))
	fake = types.SimpleNamespace(
		accounts=Collection(
			[
				{
					"_id": FakeObjectId(ACCOUNT_ID),
					"id": "e8cf14a9-uuid",
					"username": "creech147",
					"kratosUserId": "ac294a2f-kratos",
					"erpParty": "William Creech",
					"level": 2,
					"defaultWalletId": "w-usdt",
					"statusHistory": [{"status": "active"}],
				}
			]
		),
		# Shaped like prod: userId, never kratosUserId.
		users=Collection(
			[
				{
					"_id": USER_ID,
					"userId": "ac294a2f-kratos",
					"phone": "+16066129241",
					"deviceId": "dev-1",
					"deviceTokens": ["t1", "t2"],
					"phoneMetadata": {"countryCode": "US"},
				}
			]
		),
		wallets=Collection(
			[{"id": "w-usdt", "_accountId": FakeObjectId(ACCOUNT_ID), "currency": "USDT", "type": "checking"}]
		),
		cashwalletmigrations=Collection([]),
	)
	monkeypatch.setattr(mongo_reader, "_get_db", lambda: fake)
	return fake


def test_the_fake_returns_only_the_projected_fields(db):
	# Both find and find_one project. If they returned the whole document, a
	# reader projecting kratosUserId would still read userId here and pass,
	# while real Mongo leaves userId out (KeyError, or no phone).
	assert db.users.find_one({"userId": "ac294a2f-kratos"}, {"phone": 1}) == {
		"_id": USER_ID,
		"phone": "+16066129241",
	}
	assert db.users.find({}, {"kratosUserId": 1}) == [{"_id": USER_ID}]


def test_payer_identities_carry_the_owner_phone(db):
	identities = mongo_reader.load_payer_identities([ACCOUNT_ID], ["creech147"])

	identity = identities[ACCOUNT_ID]
	assert identity == {
		"account_id": ACCOUNT_ID,
		"username": "creech147",
		"phone": "+16066129241",
		"erp_party": "William Creech",
	}
	# Answerable by every handle a transfer row can carry.
	assert identities["creech147"] is identity and identities["e8cf14a9-uuid"] is identity


def test_payer_identities_without_a_user_row_have_no_phone(db):
	db.users.docs.clear()
	assert mongo_reader.load_payer_identities([ACCOUNT_ID], [])[ACCOUNT_ID]["phone"] is None


@pytest.mark.parametrize(
	"query",
	[
		"+16066129241",
		"+1 606-612-9241",
		"+1 (606) 612 9241",
		"1 606 612 9241",
		# NANP national formats, with no country code, as support pastes them.
		"606-612-9241",
		"(606) 612-9241",
		"606.612.9241",
		"6066129241",
	],
)
def test_find_account_resolves_a_phone_through_users_userid(db, query):
	account = mongo_reader.find_account(query)
	assert account is not None and account["username"] == "creech147"


@pytest.mark.parametrize("query", ["+18765550100", "876-555-0100"])
def test_find_account_by_an_unknown_phone_finds_nothing(db, query):
	assert mongo_reader.find_account(query) is None


def test_customer_bundle_reads_phone_and_devices_from_the_user(db):
	bundle = mongo_reader.customer_bundle(db.accounts.docs[0])

	assert bundle["identity"]["phone"] == "+16066129241"
	assert bundle["devices"] == {"device_id": "dev-1", "push_tokens": 2}
	# The whole row, so a field dropped from the wallets projection fails here.
	assert bundle["wallets"] == [
		{"wallet_id": "w-usdt", "currency": "USDT", "type": "checking", "is_default": True}
	]
