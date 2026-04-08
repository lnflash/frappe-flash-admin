import functools
import re
import requests as requests_lib
import frappe
from .graphql_client import GraphQLClient, GraphQLError


def handle_api_errors(func):
	"""Decorator to handle common API errors consistently"""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except GraphQLError as e:
			frappe.logger().error(f"GraphQL error in {func.__name__}: {e}")
			frappe.response['http_status_code'] = 500
			return {"success": False, "error": str(e)}
		except requests_lib.exceptions.RequestException as e:
			frappe.logger().error(f"Request error in {func.__name__}: {e}")
			frappe.response['http_status_code'] = 500
			return {"success": False, "error": str(e)}
		except ValueError as e:
			frappe.logger().error(f"Configuration error in {func.__name__}: {e}")
			frappe.response['http_status_code'] = 500
			return {"success": False, "error": str(e)}
		except Exception as e:
			frappe.logger().error(f"Unexpected error in {func.__name__}: {e}")
			frappe.response['http_status_code'] = 500
			return {"success": False, "error": "An internal error occurred"}
	return wrapper


@frappe.whitelist()
@handle_api_errors
def get_account_by_phone(phone):
	"""Get account details by phone number"""
	client = GraphQLClient()
	account = client.get_account_by_phone(phone)

	if account is None:
		frappe.response['http_status_code'] = 404
		return {"error": "Account not found"}

	return account


@frappe.whitelist()
@handle_api_errors
def update_account_level(uid, level):
	"""Update account level"""
	client = GraphQLClient()
	return client.update_account_level(uid, level)


@frappe.whitelist()
@handle_api_errors
def send_alert(title, message, tag="EMERGENCY"):
	"""Send broadcast alert to all users via admin API"""
	if not title or not message:
		frappe.response['http_status_code'] = 400
		return {"success": False, "error": "Title and message are required"}

	client = GraphQLClient()
	result = client.send_broadcast_alert(title, message, tag)

	if result.get('errors'):
		error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
		frappe.logger().error(f"Broadcast alert errors: {error_messages}")
		frappe.response['http_status_code'] = 400
		return {"success": False, "errors": error_messages}

	if not result.get('success'):
		frappe.response['http_status_code'] = 500
		return {"success": False, "error": "Failed to send alert"}

	frappe.get_doc({
		"doctype": "User Alerts",
		"title": title,
		"message": message,
		"tag": tag,
		"sent_by": frappe.session.user,
		"sent_on": frappe.utils.now_datetime()
	}).insert(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "message": f"Alert sent successfully: {title}"}


@frappe.whitelist()
@handle_api_errors
def get_user_alerts(limit=10):
	"""Return latest User Alerts"""
	logs = frappe.get_all(
		"User Alerts",
		fields=["title", "message", "tag", "sent_by", "sent_on"],
		order_by="sent_on desc",
		limit_page_length=int(limit)
	)
	return {"logs": logs}


@frappe.whitelist()
@handle_api_errors
def get_upgrade_requests(status=None, requested_level=None, page=1, page_size=10):
	"""Get paginated upgrade requests from Account Upgrade Request doctype"""
	filters = {}
	if status:
		filters["status"] = status
	if requested_level:
		filters["requested_level"] = requested_level

	page = int(page)
	page_size = min(int(page_size), 100)
	offset = (page - 1) * page_size

	total_count = frappe.db.count("Account Upgrade Request", filters=filters)
	upgrade_requests = frappe.get_all(
		"Account Upgrade Request",
		filters=filters,
		fields=["*"],
		order_by="creation desc",
		limit_start=offset,
		limit_page_length=page_size
	)

	return {
		"data": upgrade_requests,
		"total": total_count,
		"page": page,
		"page_size": page_size,
		"total_pages": (total_count + page_size - 1) // page_size
	}


@frappe.whitelist()
@handle_api_errors
def search_account(id: str):
	"""Search account by phone number or username"""
	if not id:
		frappe.response['http_status_code'] = 400
		return {"error": "Phone number or Username is required"}

	# Determine search field based on input type
	search_field = "phone_number" if len(re.sub(r'\D', '', id)) >= 10 else "username"

	results = frappe.get_all(
		"Account Upgrade Request",
		filters=[[search_field, "like", f"%{id}%"]],
		fields=["*"],
		order_by="creation desc",
		limit_page_length=50
	)

	if not results:
		frappe.response['http_status_code'] = 404
		return {"error": "Account not found"}

	return results

def _create_erp_records(req):
	"""Create Customer, Address, and Bank Account synchronously from upgrade request data.
	Returns (errors, customer_name) — errors is empty list on full success.
	"""
	errors = []
	customer_name = None

	# 1. Create Customer
	try:
		existing = frappe.db.get_value("Customer", {"mobile_no": req.phone_number}, "name")
		if existing:
			customer_name = existing
		else:
			customer = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": req.full_name,
				"customer_type": "Company" if req.address_title else "Individual",
				"mobile_no": req.phone_number,
				"email_id": req.email or "",
			})
			customer.insert(ignore_permissions=True)
			customer_name = customer.name
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"Customer creation failed for request {req.name}")
		errors.append(f"Customer: {e}")
		return errors, None  # Address and Bank Account depend on Customer — skip them

	# 2. Create Address (requires at minimum address_line1, city, country)
	if req.address_line1 and req.city and req.country:
		try:
			existing_addresses = frappe.get_all(
				"Address",
				filters=[
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", customer_name],
				],
				fields=["address_line1", "address_line2", "city", "state", "pincode", "country"]
			)
			address_unchanged = any(
				(a.address_line1 or "") == (req.address_line1 or "")
				and (a.address_line2 or "") == (req.address_line2 or "")
				and (a.city or "") == (req.city or "")
				and (a.state or "") == (req.state or "")
				and (a.pincode or "") == (req.pincode or "")
				and (a.country or "") == (req.country or "")
				for a in existing_addresses
			)
			if not address_unchanged:
				address = frappe.get_doc({
					"doctype": "Address",
					"address_title": req.address_title or req.full_name,
					"address_type": "Billing",
					"address_line1": req.address_line1,
					"address_line2": req.address_line2 or "",
					"city": req.city,
					"state": req.state or "",
					"pincode": req.pincode or "",
					"country": req.country,
					"links": [{
						"link_doctype": "Customer",
						"link_name": customer_name,
					}],
				})
				address.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Address creation failed for request {req.name}")
			errors.append(f"Address: {e}")

	# 3. Create Bank Account (requires bank_name and account_number)
	if req.bank_name and req.account_number:
		try:
			if not frappe.db.exists("Bank", req.bank_name):
				frappe.get_doc({
					"doctype": "Bank",
					"bank_name": req.bank_name,
				}).insert(ignore_permissions=True)

			if not frappe.db.exists("Bank Account", {"bank_account_no": req.account_number}):
				bank_account = frappe.get_doc({
					"doctype": "Bank Account",
					"account_name": req.address_title or req.full_name,
					"bank": req.bank_name,
					"bank_account_no": req.account_number,
					"branch_code": req.bank_branch or "",
					"account_type": req.account_type or "",
					"currency": req.currency or "",
					"is_company_account": 0,
					"party_type": "Customer",
					"party": customer_name,
				})
				bank_account.insert(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), f"Bank Account creation failed for request {req.name}")
			errors.append(f"Bank Account: {e}")

	return errors, customer_name


@frappe.whitelist()
@handle_api_errors
def approve_upgrade_request(request_id):
	"""Approve an account upgrade request and update account level via GraphQL"""
	req = frappe.get_doc("Account Upgrade Request", request_id, for_update=True)

	if req.status != "Pending":
		return {"success": False, "error": f"Request has already been {req.status.lower()}"}

	# Get account details to retrieve the UID
	client = GraphQLClient()
	account = client.get_account_by_phone(req.phone_number)
	if not account:
		return {"success": False, "error": "Account not found in external system"}

	# Create ERP records (Customer, Address, Bank Account) before mutation
	erp_party = None
	if req.requested_level in ("TWO", "THREE"):
		erp_errors, erp_party = _create_erp_records(req)
		if erp_errors:
			return {"success": False, "error": f"ERP record creation failed: {'; '.join(erp_errors)}"}

	# Update account level via GraphQL (ZERO, ONE, TWO, THREE)
	result = client.update_account_level(
		uid=account['id'],
		level=req.requested_level,
		erp_party=erp_party,
	)

	if result.get('errors'):
		error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
		return {"success": False, "errors": error_messages}

	# Update local request record
	req.status = "Approved"
	req.save()
	frappe.db.commit()

	return {
		"success": True,
		"message": "Request approved and account level updated.",
	}


@frappe.whitelist()
@handle_api_errors
def reject_upgrade_request(request_id, reason=None):
	"""Reject an account upgrade request (local record only, no level change)"""
	req = frappe.get_doc("Account Upgrade Request", request_id, for_update=True)

	if req.status != "Pending":
		return {"success": False, "error": f"Request has already been {req.status.lower()}"}

	# Update local request record only - rejection doesn't change account level
	req.status = "Rejected"
	req.support_note = reason or "No reason provided"
	req.save()

	frappe.db.commit()
	return {"success": True, "message": "Request rejected."}


DUMMY_CASHOUT_REQUESTS = [
	{
		"name": "CO-2026-00001", "username": "john_doe", "full_name": "John Doe",
		"phone_number": "12345678901", "email": "john@example.com",
		"offer_id": "OFFER-8821", "wallet_id": "WALLET-44301",
		"send": 500.00, "flash_fee": 5.00, "exchange_rate": 156.2500,
		"receive_jmd": 77625.00, "receive_usd": 495.00,
		"bank_account": "BA-00001", "bank_name": "First National Bank",
		"account_number": "****1234", "account_type": "Savings",
		"journal_entry": "JE-2026-00001", "status": "Pending", "payment_entry": None,
		"creation": "2026-04-01 10:00:00", "modified": "2026-04-01 10:00:00",
	},
	{
		"name": "CO-2026-00002", "username": "jane_smith", "full_name": "Jane Smith",
		"phone_number": "98765432101", "email": "jane@example.com",
		"offer_id": "OFFER-7734", "wallet_id": "WALLET-88102",
		"send": 1200.50, "flash_fee": 12.00, "exchange_rate": 156.5000,
		"receive_jmd": 185714.25, "receive_usd": 1188.50,
		"bank_account": "BA-00002", "bank_name": "City Bank",
		"account_number": "****5678", "account_type": "Chequing",
		"journal_entry": "JE-2026-00002", "status": "Paid",
		"payment_entry": "PE-2026-00001",
		"pe_paid_amount": 1200.50, "pe_currency": "USD",
		"pe_posting_date": "2026-04-01", "pe_mode_of_payment": "Bank Transfer",
		"creation": "2026-04-01 11:30:00", "modified": "2026-04-01 12:00:00",
	},
	{
		"name": "CO-2026-00003", "username": "ali_hassan", "full_name": "Ali Hassan",
		"phone_number": "55544433301", "email": "ali@example.com",
		"offer_id": "OFFER-5591", "wallet_id": "WALLET-22987",
		"send": 350.00, "flash_fee": 3.50, "exchange_rate": 157.0000,
		"receive_jmd": 53812.50, "receive_usd": 346.50,
		"bank_account": "BA-00003", "bank_name": "Metro Bank",
		"account_number": "****9012", "account_type": "Savings",
		"journal_entry": "JE-2026-00003", "status": "Pending", "payment_entry": None,
		"creation": "2026-04-02 09:15:00", "modified": "2026-04-02 09:15:00",
	},
	{
		"name": "CO-2026-00004", "username": "maria_lopez", "full_name": "Maria Lopez",
		"phone_number": "11122233401", "email": "maria@example.com",
		"offer_id": "OFFER-3302", "wallet_id": "WALLET-67541",
		"send": 75.00, "flash_fee": 0.75, "exchange_rate": 156.0000,
		"receive_jmd": 11566.25, "receive_usd": 74.25,
		"bank_account": "BA-00004", "bank_name": "Global Bank",
		"account_number": "****3456", "account_type": "Current",
		"journal_entry": "JE-2026-00004", "status": "Failed", "payment_entry": None,
		"creation": "2026-04-02 14:00:00", "modified": "2026-04-02 14:30:00",
	},
	{
		"name": "CO-2026-00005", "username": "chen_wei", "full_name": "Chen Wei",
		"phone_number": "66677788901", "email": "chen@example.com",
		"offer_id": "OFFER-9918", "wallet_id": "WALLET-11234",
		"send": 2500.00, "flash_fee": 25.00, "exchange_rate": 156.7500,
		"receive_jmd": 385312.50, "receive_usd": 2475.00,
		"bank_account": "BA-00005", "bank_name": "Pacific Bank",
		"account_number": "****7890", "account_type": "Savings",
		"journal_entry": "JE-2026-00005", "status": "Cancelled", "payment_entry": None,
		"creation": "2026-04-03 08:00:00", "modified": "2026-04-03 08:45:00",
	},
	{
		"name": "CO-2026-00006", "username": "anna_k", "full_name": "Anna Kowalski",
		"phone_number": "44433322201", "email": "anna@example.com",
		"offer_id": "OFFER-6647", "wallet_id": "WALLET-33890",
		"send": 890.75, "flash_fee": 8.90, "exchange_rate": 156.2500,
		"receive_jmd": 137316.56, "receive_usd": 881.85,
		"bank_account": "BA-00006", "bank_name": "Northern Bank",
		"account_number": "****2345", "account_type": "Savings",
		"journal_entry": "JE-2026-00006", "status": "Pending", "payment_entry": None,
		"creation": "2026-04-03 09:30:00", "modified": "2026-04-03 09:30:00",
	},
	{
		"name": "CO-2026-00007", "username": "omar_s", "full_name": "Omar Said",
		"phone_number": "99988877701", "email": "omar@example.com",
		"offer_id": "OFFER-2283", "wallet_id": "WALLET-55612",
		"send": 150.00, "flash_fee": 1.50, "exchange_rate": 157.2500,
		"receive_jmd": 23250.00, "receive_usd": 148.50,
		"bank_account": "BA-00007", "bank_name": "Eastern Bank",
		"account_number": "****6789", "account_type": "Chequing",
		"journal_entry": "JE-2026-00007", "status": "Paid",
		"payment_entry": "PE-2026-00002",
		"pe_paid_amount": 150.00, "pe_currency": "USD",
		"pe_posting_date": "2026-04-03", "pe_mode_of_payment": "Bank Transfer",
		"creation": "2026-04-03 10:00:00", "modified": "2026-04-03 10:20:00",
	},
]


@frappe.whitelist()
@handle_api_errors
def get_cashout_requests(status=None, page=1, page_size=10):
	"""Get paginated cashout requests (dummy data until doctype is implemented)"""
	page = int(page)
	page_size = min(int(page_size), 100)

	data = DUMMY_CASHOUT_REQUESTS
	if status:
		data = [r for r in data if r["status"] == status]

	total_count = len(data)
	offset = (page - 1) * page_size
	page_data = data[offset:offset + page_size]

	return {
		"data": page_data,
		"total": total_count,
		"page": page,
		"page_size": page_size,
		"total_pages": max(1, (total_count + page_size - 1) // page_size),
	}


@frappe.whitelist()
@handle_api_errors
def search_cashout_account(id: str):
	"""Search cashout requests by username or phone (dummy data)"""
	if not id:
		frappe.response['http_status_code'] = 400
		return {"error": "Phone number or Username is required"}

	import re as _re
	search_by_phone = len(_re.sub(r'\D', '', id)) >= 10
	id_lower = id.lower()

	if search_by_phone:
		results = [r for r in DUMMY_CASHOUT_REQUESTS if id_lower in _re.sub(r'\D', '', r.get("phone_number", ""))]
	else:
		results = [r for r in DUMMY_CASHOUT_REQUESTS if id_lower in r.get("username", "").lower()]

	if not results:
		frappe.response['http_status_code'] = 404
		return {"error": "Account not found"}

	return results


@frappe.whitelist()
@handle_api_errors
def record_cashout_payment(cashout_id):
	"""Record a Payment Entry for a cashout request (stub — real impl awaits doctype)"""
	if not cashout_id:
		frappe.response['http_status_code'] = 400
		return {"success": False, "error": "Cashout ID is required"}

	# Find in dummy data
	req = next((r for r in DUMMY_CASHOUT_REQUESTS if r["name"] == cashout_id), None)
	if not req:
		frappe.response['http_status_code'] = 404
		return {"success": False, "error": "Cashout request not found"}

	if req["status"] != "Pending":
		return {"success": False, "error": f"Cashout request has already been {req['status'].lower()}"}

	if req["payment_entry"]:
		return {"success": False, "error": "Payment Entry already exists for this cashout"}

	# Stub: generate a dummy payment entry name.
	# When the Cashout doctype is implemented, this will create a real Payment Entry
	# linked to the cashout, submit it, and update the cashout status and payment_entry field.
	import random
	from frappe.utils import today
	dummy_pe_name = f"PE-2026-{random.randint(10000, 99999):05d}"
	req["status"] = "Paid"
	req["payment_entry"] = dummy_pe_name
	req["pe_paid_amount"] = req.get("send")
	req["pe_currency"] = "USD"
	req["pe_posting_date"] = today()
	req["pe_mode_of_payment"] = "Bank Transfer"

	return {
		"success": True,
		"payment_entry": dummy_pe_name,
		"message": f"Payment Entry {dummy_pe_name} created and cashout marked as Paid.",
	}


@frappe.whitelist()
@handle_api_errors
def get_id_document_url(file_key):
	"""Get pre-signed URL for ID document from Digital Ocean Spaces"""
	if not file_key:
		frappe.response['http_status_code'] = 400
		return {"success": False, "error": "File key is required"}

	client = GraphQLClient()
	result = client.get_id_document_read_url(file_key)

	if result.get('errors'):
		error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
		frappe.logger().error(f"ID document URL errors: {error_messages}")
		frappe.response['http_status_code'] = 400
		return {"success": False, "errors": error_messages}

	return {"success": True, "url": result.get('readUrl')}
