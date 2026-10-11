import re

import frappe
from frappe.model.document import Document

from admin_panel.api.flash_identifiers import is_flash_username_candidate

# Fields set from flash at insert time; none may change on a saved row.
IDENTITY_FIELDS = ("account", "account_id", "username", "account_uuid")

# flash's reader drops any account_id that is not a 24-hex Mongo ObjectId, and
# drops it silently (ENG-640-flash.md decision 1), so a row with any other
# shape would save cleanly and never pay.
MONGO_ID_RE = re.compile(r"[0-9a-f]{24}")


class ReferralPayoutAllowlist(Document):
	"""Accounts flash pays referral rewards to while its global pause is on.

	flash matches rows on ``account_id``, the account's Mongo ``_id`` string
	(the same id the Referral Rewards page joins inviters and invitees on),
	never on the username or the account uuid. The row is keyed by it too
	(autoname field:account_id), so one account can only be listed once.

	Saving is strict on purpose: this list gates money, and a row flash
	cannot confirm would grant nothing while looking like it does. Unlike
	Fee Discount there is no warn-and-save path and no ``verified`` flag.
	"""

	def before_insert(self):
		# Runs before set_new_name, so the document name is built from the
		# resolved account_id (the same ordering fee_discount.py relies on).
		self._resolve(self.account)

	def validate(self):
		# Never call flash on a saved row: unchecking Enabled or editing the
		# note must keep working during a flash outage, because that is the
		# kill path for a single account.
		# Every resolved identity field is guarded, not just ``account``:
		# read_only in the doctype JSON is enforced only in the desk UI, so a
		# REST PUT could otherwise repoint ``account_id`` (the field flash
		# matches on) while the name and display fields still show the
		# original account. The name is pinned to account_id for the same reason.
		if not self.is_new() and (
			any(self.has_value_changed(f) for f in IDENTITY_FIELDS) or self.account_id != self.name
		):
			frappe.throw("Identity cannot be edited; delete this row and add a new one.")

	def _resolve(self, value):
		value = (value or "").strip()
		if not value:
			frappe.throw("Flash username or account UUID is required.")
		self.account = value

		try:
			from admin_panel.api.graphql_client import GraphQLClient

			client = GraphQLClient()
			account = None
			# Same dispatch as the admin account lookup (admin_api.py): a
			# username-shaped input is tried as a username first, then as an
			# account uuid; anything else goes straight to the uuid lookup.
			# accountDetailsByAccountId resolves by uuid on the flash side.
			if is_flash_username_candidate(value):
				account = client.get_account_by_username(value)
			if account is None:
				account = client.get_account_by_id(value)
		except Exception:
			frappe.log_error(
				title="Referral Payout Allowlist: flash account check failed",
				message=frappe.get_traceback(),
			)
			frappe.throw("Could not verify against flash; nothing was saved. Try again.")

		if not account:
			frappe.throw(f"No flash account matches '{value}'. Use the username or account UUID.")

		account_id = account.get("id")
		if not account_id:
			frappe.throw(f"Flash returned an account for '{value}' without an account ID; nothing was saved.")

		account_id = str(account_id)
		if not MONGO_ID_RE.fullmatch(account_id):
			frappe.throw(
				f"Flash returned an account ID for '{value}' that is not a Mongo id; nothing was saved."
			)

		self.account_id = account_id
		self.username = account.get("username")
		self.account_uuid = account.get("uuid")
