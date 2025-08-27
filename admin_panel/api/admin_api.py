import frappe
import requests
from .graphql_client import GraphQLClient, GraphQLError

GENERIC_ERROR = { "error": "An internal error occurred."}

@frappe.whitelist()
def get_account_by_phone(phone):
	try:
		account = GraphQLClient().get_account_by_phone(phone)
		if account is None:
			frappe.response['http_status_code'] = 404
			return "Account not found"
		else:
			return account
	except Exception as e:
		frappe.logger().error(f"Unexpected error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return GENERIC_ERROR

@frappe.whitelist()
def update_account_level(uid, level):
	try:
		return GraphQLClient().update_account_level(uid, level)
	except Exception as e:
		frappe.logger().error(f"Unexpected error updating account {uid} to level {level}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return GENERIC_ERROR
