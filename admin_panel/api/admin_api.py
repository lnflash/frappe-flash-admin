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
	Returns a list of error strings — empty list means full success.
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
		return errors  # Address and Bank Account depend on Customer — skip them

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

	return errors


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
	erp_errors = []
	if req.requested_level in ("TWO", "THREE"):
		erp_errors = _create_erp_records(req)
		if erp_errors:
			return {"success": False, "error": f"ERP record creation failed: {'; '.join(erp_errors)}"}

	# Update account level via GraphQL (ZERO, ONE, TWO, THREE)
	result = client.update_account_level(
		uid=account['id'],
		level=req.requested_level
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
