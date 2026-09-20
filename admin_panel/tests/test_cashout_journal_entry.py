"""Cashout payable Journal Entry: a zero Flash fee must not book a zero row.

ERPNext rejects any Journal Entry row whose debit and credit are both zero
("Row 3: Both Debit and Credit values cannot be zero"), which failed the whole
Cashout insert for users on a 100% cashout Fee Discount.
"""

import types

import pytest
from idv_stubs import frappe

from admin_panel.admin_panel.doctype.cashout import cashout as module

SETTINGS = types.SimpleNamespace(
	operating_account="Operating - F",
	payables_account_jmd="Payables JMD - F",
	payables_account_usd="Payables USD - F",
	service_fees_account="Service Fees - F",
)


class FakeJournalEntry:
	"""Mimics ERPNext's zero-row validation on insert."""

	def __init__(self, data):
		self.name = "JE-0001"
		self.data = data
		self.accounts = list(data["accounts"])
		self.inserted = False

	def append(self, field, row):
		assert field == "accounts"
		self.accounts.append(row)

	def insert(self):
		for idx, row in enumerate(self.accounts, start=1):
			debit = row.get("debit") or 0
			credit = row.get("credit") or 0
			if not debit and not credit:
				raise frappe.ValidationError(f"Row {idx}: Both Debit and Credit values cannot be zero")
		self.inserted = True


@pytest.fixture()
def entries(monkeypatch):
	created = []

	def get_doc(data):
		je = FakeJournalEntry(data)
		created.append(je)
		return je

	monkeypatch.setattr(frappe, "get_doc", get_doc, raising=False)
	monkeypatch.setattr(frappe, "get_single", lambda doctype: SETTINGS, raising=False)
	monkeypatch.setattr(
		frappe,
		"defaults",
		types.SimpleNamespace(get_user_default=lambda key: "Flash"),
		raising=False,
	)
	monkeypatch.setattr(frappe.utils, "today", lambda: "2026-09-20", raising=False)
	return created


def make(**values):
	doc = module.Cashout()
	defaults = {
		"transaction_id": "hash",
		"wallet_id": "wallet",
		"currency": "JMD",
		"exchange_rate": 151.8,
		"user_pays": 730,
		"user_receives": 110814,
		"flash_fee": 0,
	}
	for key, value in {**defaults, **values}.items():
		setattr(doc, key, value)
	doc.saved = {}
	doc.db_set = lambda field, value, update_modified=True: doc.saved.update({field: value})
	return doc


def accounts_of(je):
	return [row["account"] for row in je.accounts]


@pytest.mark.parametrize("fee", [0, 0.0, None])
def test_zero_fee_cashout_books_no_fee_row(entries, fee):
	doc = make(flash_fee=fee)
	doc.create_payable_journal_entry()

	(je,) = entries
	assert je.inserted
	assert accounts_of(je) == ["Operating - F", "Payables JMD - F"]
	assert doc.saved == {"journal_entry": "JE-0001"}


@pytest.mark.parametrize(
	("currency", "exchange_rate", "user_receives"),
	[
		("USD", None, 730),
		# The JMD path is the one with arithmetic: credit = user_receives / exchange_rate.
		("JMD", 151.8, 110814),
	],
)
def test_zero_fee_entry_balances_in_company_currency(entries, currency, exchange_rate, user_receives):
	make(
		currency=currency, exchange_rate=exchange_rate, user_pays=730, user_receives=user_receives
	).create_payable_journal_entry()

	(je,) = entries
	assert je.inserted
	debit = sum(row.get("debit") or 0 for row in je.accounts)
	credit = sum(row.get("credit") or 0 for row in je.accounts)
	assert debit == 730
	assert credit == pytest.approx(730)
	assert debit == pytest.approx(credit)


def test_fee_bearing_cashout_still_books_the_fee_row(entries):
	doc = make(currency="USD", exchange_rate=None, user_pays=730, user_receives=715.4, flash_fee=14.6)
	doc.create_payable_journal_entry()

	(je,) = entries
	assert je.inserted
	assert accounts_of(je) == ["Operating - F", "Payables USD - F", "Service Fees - F"]
	fee_row = je.accounts[2]
	assert fee_row["credit"] == 14.6
	assert fee_row["credit_in_account_currency"] == 14.6
	assert fee_row["account_currency"] == "USD"
	debit = sum(row.get("debit") or 0 for row in je.accounts)
	credit = sum(row.get("credit") or 0 for row in je.accounts)
	assert debit == pytest.approx(credit)


def test_jmd_payable_row_uses_the_exchange_rate(entries):
	make(flash_fee=14.6, user_receives=108597.72).create_payable_journal_entry()

	(je,) = entries
	payable = je.accounts[1]
	assert payable["account"] == "Payables JMD - F"
	assert payable["credit_in_account_currency"] == 108597.72
	assert payable["credit"] == pytest.approx(108597.72 / 151.8)
