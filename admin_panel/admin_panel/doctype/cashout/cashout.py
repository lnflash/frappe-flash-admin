import frappe
from frappe.model.document import Document


@frappe.whitelist()
def submit_cashout(name):
	frappe.get_doc("Cashout", name).submit()


class Cashout(Document):

	def validate(self):
		bank_account = frappe.get_doc("Bank Account", self.bank_account)
		if bank_account.party_type != "Customer" or bank_account.party != self.customer:
			frappe.throw("Bank Account does not belong to the selected Customer.")

		# account_currency = frappe.get_value("Account", bank_account.account, "account_currency")
		# self.currency = account_currency or "USD"

	def after_insert(self):
		self.create_payable_journal_entry()

	def before_submit(self):
		if not self.transaction_id:
			frappe.throw("Transaction ID is required before submitting.")

	def on_submit(self):
		je = frappe.get_doc("Journal Entry", self.journal_entry)
		je.submit()
		self.db_set("status", "In Progress")

	def create_payable_journal_entry(self):
		company = frappe.defaults.get_user_default("Company")

		is_jmd = self.currency == "JMD"

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"multi_currency": 1,
			"posting_date": frappe.utils.today(),
			"user_remark": f'{{"transactionId": "{self.transaction_id}", "walletId": "{self.wallet_id}"}}',
			"accounts": [
				{
					"account": "Ibex Operating - F",
					"account_currency": "USD",
					"debit_in_account_currency": self.user_pays,
					"debit": self.user_pays,
					"exchange_rate": 1,
				},
				{
					"account": f"Cashout Payables ({self.currency}) - F",
					"account_currency": self.currency,
					"credit_in_account_currency": self.user_receives,
					"credit": self.user_receives / self.exchange_rate if is_jmd else self.user_receives,
					"exchange_rate": 1 / self.exchange_rate if is_jmd else 1,
					# "party_type": "Customer",
					# "party": self.customer,
				},
				{
					"account": "Service Fees - F",
					"account_currency": "USD",
					"credit_in_account_currency": self.flash_fee,
					"credit": self.flash_fee,
					"exchange_rate": 1,
				},
			]
		})

		je.insert(ignore_permissions=True)
		self.db_set("journal_entry", je.name, update_modified=False)

	@frappe.whitelist()
	def create_payment_journal_entry(self):
		if self.payment_journal_entry:
			frappe.throw("Payment Journal Entry already exists.")

		if self.status != "In Progress":
			frappe.throw("Cashout must be In Progress before marking as Completed.")

		company = frappe.defaults.get_user_default("Company")
		is_jmd = self.currency == "JMD"

		bank_accounts = frappe.get_all(
			"Bank Account",
			filters={"company": company, "is_company_account": 1},
			fields=["account"]
		)
		company_bank_account = next(
			(ba.account for ba in bank_accounts
			 if frappe.get_value("Account", ba.account, "account_currency") == self.currency),
			None
		)
		if not company_bank_account:
			frappe.throw(f"No company Bank Account found for currency {self.currency}.")

		payout_entry = {
			"account_currency": self.currency,
			"debit_in_account_currency": self.user_receives,
			"credit_in_account_currency": 0,
			"debit": self.user_receives / self.exchange_rate if is_jmd else self.user_receives,
			"exchange_rate": 1 / self.exchange_rate if is_jmd else 1,
		}

		je = frappe.get_doc({
			"doctype": "Journal Entry",
			"voucher_type": "Bank Entry",
			"company": company,
			"multi_currency": 1,
			"posting_date": frappe.utils.today(),
			"user_remark": f'{{"transactionId": "{self.transaction_id}", "walletId": "{self.wallet_id}"}}',
			"accounts": [
				{
					**payout_entry,
					"account": f"Cashout Payables ({self.currency}) - F",
					# "party_type": "Customer",
					# "party": self.customer,
				},
				{
					**payout_entry,
					"account": company_bank_account,
					"debit_in_account_currency": 0,
					"debit": 0,
					"credit_in_account_currency": self.user_receives,
					"credit": self.user_receives / self.exchange_rate if is_jmd else self.user_receives,
				},
			]
		})

		je.insert(ignore_permissions=True)
		je.submit()

		self.db_set("payment_journal_entry", je.name)
		self.db_set("status", "Completed")
		frappe.msgprint(f"Payment Journal Entry {je.name} created.")
