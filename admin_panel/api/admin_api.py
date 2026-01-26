import functools
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
	page_size = int(page_size)
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
	cleaned_id = ''.join(filter(str.isdigit, id))
	search_field = "phone_number" if len(cleaned_id) >= 10 else "username"

	results = frappe.get_all(
		"Account Upgrade Request",
		filters=[[search_field, "like", f"%{id}%"]],
		fields=["*"],
		order_by="creation desc"
	)

	if not results:
		frappe.response['http_status_code'] = 404
		return {"error": "Account not found"}

	return results

@frappe.whitelist()
@handle_api_errors
def approve_upgrade_request(request_id):
	"""Approve an account upgrade request"""
	req = frappe.get_doc("Account Upgrade Request", request_id)

	req.status = "Approved"
	req.approved_by = frappe.session.user
	req.approval_date = frappe.utils.now_datetime()
	req.save()

	# Create bank account if all bank details are provided
	bank_fields = [req.bank_name, req.bank_branch, req.account_type, req.currency, req.account_number]
	if all(bank_fields):
		frappe.get_doc({
			"doctype": "Bank Account",
			"account_name": f"{req.username}-{req.bank_name}",
			"bank": req.bank_name,
			"account_type": req.account_type,
			"branch_code": req.bank_branch,
			"bank_account_no": req.account_number
		}).insert()

	frappe.db.commit()
	return {"success": True, "message": "Request approved and user level updated."}


@frappe.whitelist()
@handle_api_errors
def reject_upgrade_request(request_id, reason=None):
	"""Reject an account upgrade request"""
	req = frappe.get_doc("Account Upgrade Request", request_id)

	req.status = "Rejected"
	req.rejection_reason = reason or "No reason provided"
	req.approved_by = frappe.session.user
	req.approval_date = frappe.utils.now_datetime()
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
