import frappe
import requests
from .graphql_client import GraphQLClient, GraphQLError


@frappe.whitelist()
def get_account_by_phone(phone):
	"""Get account details by phone number"""
	try:
		client = GraphQLClient()
		account = client.get_account_by_phone(phone)
		
		if account is None:
			frappe.response['http_status_code'] = 404
			return {"error": "Account not found"}
		
		return account
		
	except GraphQLError as e:
		frappe.logger().error(f"GraphQL error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": f"GraphQL error: {str(e)}"}
		
	except requests.exceptions.RequestException as e:
		frappe.logger().error(f"Request error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": f"Request error: {str(e)}"}
		
	except Exception as e:
		frappe.logger().error(f"Unexpected error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": "An internal error occurred"}


@frappe.whitelist()
def update_account_level(uid, level):
	"""Update account level"""
	try:
		client = GraphQLClient()
		return client.update_account_level(uid, level)
		
	except Exception as e:
		frappe.logger().error(f"Error updating account {uid} to level {level}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": "An internal error occurred"}


@frappe.whitelist()
def send_alert(title, message, tag="EMERGENCY"):
	"""Send broadcast alert to all users via admin API"""
	try:
		# Validate inputs
		if not title or not message:
			frappe.response['http_status_code'] = 400
			return {"error": "Title and message are required"}
		
		# Call GraphQL API
		client = GraphQLClient()
		result = client.send_broadcast_alert(title, message, tag)
		
		# Check for errors in the response
		if result.get('errors'):
			error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
			frappe.logger().error(f"Broadcast alert errors: {error_messages}")
			frappe.response['http_status_code'] = 400
			return {
				"success": False,
				"errors": error_messages
			}
		
		# Success
		if result.get('success'):
			frappe.get_doc({
				"doctype": "User Alerts",
                "title": title,
                "message": message,
                "tag": tag,
                "sent_by": frappe.session.user,
                "sent_on": frappe.utils.now_datetime()
			}).insert(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"success": True,
				"message": f"Alert sent successfully: {title}"
			}
		else:
			frappe.response['http_status_code'] = 500
			return {
				"success": False,
				"error": "Failed to send alert"
			}
			
	except GraphQLError as e:
		frappe.logger().error(f"GraphQL error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": str(e)
		}
		
	except requests.exceptions.RequestException as e:
		frappe.logger().error(f"Request error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": str(e)
		}
		
	except Exception as e:
		frappe.logger().error(f"Unexpected error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": "An internal error occurred"
		}


@frappe.whitelist()
def get_user_alerts(limit=10):
    """Return latest User Alerts"""
    try:
        logs = frappe.get_all(
            "User Alerts",
            fields=["title", "message", "tag", "sent_by", "sent_on"],
            order_by="sent_on desc",
            limit_page_length=int(limit)
        )
        return {"logs": logs}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error fetching User Alerts")
        frappe.response["http_status_code"] = 500
        return {"error": str(e)}


@frappe.whitelist()
def get_upgrade_requests(status=None, requested_level=None):
    """Get all pending upgrade requests from Account Upgrade Request doctype"""
    try:
        filters = {}
        if status:
            filters["status"] = status

        if requested_level:
            filters["requested_level"] = requested_level

        requests = frappe.get_all(
            "Account Upgrade Request",
            filters=filters,
            fields=["*"],
            order_by="creation desc"
        )

        return requests

    except Exception as e:
        frappe.logger().error(f"Error fetching upgrade requests: {str(e)}")
        frappe.response["http_status_code"] = 500
        return {"error": "An internal error occurred"}


@frappe.whitelist()
def search_account(query):
    """Search account by phone number"""
    try:
        if not query:
            frappe.response['http_status_code'] = 400
            return {"error": "Phone number is required"}
   
        cleaned_query = ''.join(filter(str.isdigit, query))
        if len(cleaned_query) >= 10:
            requests = frappe.get_all(
                "Account Upgrade Request",
                filters=[["phone_number", "like", f"%{query}%"]],
                fields=["*"],
                order_by="creation desc"
            )

            if requests:
                return requests
            else:
                frappe.response['http_status_code'] = 404
                return {"error": "Account not found"}
        else:
            requests = frappe.get_all(
                "Account Upgrade Request",
                filters=[["username", "like", f"%{query}%"]],
                fields=["*"],
                order_by="creation desc"
            )
    
            if requests:
                return requests
            else:
                frappe.response['http_status_code'] = 404
                return {"error": "Account not found"}
        

    except Exception as e:
        frappe.logger().error(f"Error searching account: {str(e)}")
        frappe.response['http_status_code'] = 500
        return {"error": "An internal error occurred"}

@frappe.whitelist()
def approve_upgrade_request(request_id):
    req = frappe.get_doc("Account Upgrade Request", request_id)

    req.status = "Approved"
    req.approved_by = frappe.session.user
    req.approval_date = frappe.utils.now_datetime()
    req.save()

    frappe.db.commit()

    return {"success": True, "message": "Request approved and user level updated."}

@frappe.whitelist()
def reject_upgrade_request(request_id, reason=None):
    req = frappe.get_doc("Account Upgrade Request", request_id)

    req.status = "Rejected"
    req.rejection_reason = reason or "No reason provided"
    req.approved_by = frappe.session.user  # store the person who rejected
    req.approval_date = frappe.utils.now_datetime()
    req.save()

    frappe.db.commit()

    return {"success": True, "message": "Request rejected."}
