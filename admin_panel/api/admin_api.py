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