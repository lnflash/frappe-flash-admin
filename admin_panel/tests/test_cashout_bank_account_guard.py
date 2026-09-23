"""Cashout.validate is where a removed bank account has to stop working.

delete_bank_account soft-deletes (disabled=1) exactly the accounts that already
have Cashouts — the ones whose bankAccountId clients and in-flight offers
already know. Hiding them from the banking endpoints is not enough: the write
that moves money is the Cashout insert.
"""

import pytest
from idv_stubs import frappe

from admin_panel.admin_panel.doctype.cashout import cashout as module

PARTY = "CUST-0001"


@pytest.fixture()
def accounts(fake, monkeypatch):
	class Thrown(frappe.ValidationError):
		pass

	def throw(msg, exc=None, *args, **kwargs):
		raise (exc or Thrown)(msg)

	monkeypatch.setattr(frappe, "throw", throw, raising=False)
	fake.Thrown = Thrown

	def seed(**extra):
		fake.seed(
			"Bank Account",
			{
				"name": "A - NCB",
				"party_type": "Customer",
				"party": PARTY,
				"disabled": 0,
				"is_company_account": 0,
				**extra,
			},
		)
		return fake

	return seed


def cashout(new=True, customer=PARTY):
	doc = module.Cashout()
	doc.bank_account = "A - NCB"
	doc.customer = customer
	doc.is_new = lambda: new
	return doc


def test_new_cashout_to_a_live_account_passes(accounts):
	accounts()

	cashout().validate()


def test_new_cashout_to_a_removed_account_is_rejected(accounts):
	fake = accounts(disabled=1, removed_by_customer=1)

	with pytest.raises(fake.Thrown, match="no longer available"):
		cashout().validate()


def test_new_cashout_to_an_admin_disabled_account_is_rejected(accounts):
	fake = accounts(disabled=1)

	with pytest.raises(fake.Thrown, match="no longer available"):
		cashout().validate()


def test_new_cashout_to_a_company_account_is_rejected(accounts):
	fake = accounts(is_company_account=1)

	with pytest.raises(fake.Thrown, match="no longer available"):
		cashout().validate()


def test_ownership_is_still_checked_first(accounts):
	fake = accounts(disabled=1)

	with pytest.raises(fake.Thrown, match="does not belong"):
		cashout(customer="CUST-0002").validate()


def test_existing_cashout_stays_saveable_after_the_account_is_removed(accounts):
	"""validate also runs on submit. A Cashout inserted before the removal has
	already debited the customer; ops must still be able to submit it."""
	accounts(disabled=1, removed_by_customer=1)

	cashout(new=False).validate()
