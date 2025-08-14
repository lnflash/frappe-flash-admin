import requests
import frappe

url=frappe.conf.get("graphql_api_url") or "http://localhost:4002/admin/graphql"
frappe.conf.get("graphql_api_key")
headers = {
	"Content-Type": "application/json",
	# "Authorization": f"Bearer {self.api_key}"  # adjust auth format as needed
}

@frappe.whitelist()
def get_account_by_id(id):
	print(f"Fetching account data for ID: {id}")
	payload = {
		"query": """
			query accountDetailsByAccountId($accountId: ID!) {
				accountDetailsByAccountId(accountId: $accountId) {
					id
					username
					level
					status
					title
					owner {
						id
						language
						phone
						email {
							address
							verified
						}
						createdAt
					}
					coordinates {
						latitude
						longitude
					}
					wallets {
						id
						walletCurrency
						accountId
						balance
						pendingIncomingBalance
					}
					createdAt
				}
			}
		""",
		"variables": { "accountId": id }
	}
	try:
		response = requests.post(
			url=url,
			json=payload,
			headers=headers,
			timeout=30
		)
	
		response.raise_for_status()
		graphql_response = response.json()

		print(f"GraphQL response: {graphql_response}")
		if 'errors' in graphql_response:
			error_messages = [error.get('message', 'Unknown error') for error in graphql_response['errors']]
			frappe.log_error(f"GraphQL errors for id {id}: {error_messages}", "Customer Account GraphQL")
			return {
					"success": False,
					"error": f"GraphQL errors: {', '.join(error_messages)}"
			}
			
		# Extract account data
		account_data = graphql_response.get('data', {}).get('accountDetailsByAccountId', {})
	
		if not account_data:
			return {
					"success": False,
					"error": f"No account found for id address: {id}"
			}
	
		# formatted_data = format_account_data(account_data)
	
		frappe.logger().info(f"Successfully retrieved account data for id: {id}")
	
		return {
				"success": True,
				"data": account_data
		}
	except requests.exceptions.Timeout:
		frappe.log_error(f"Timeout error for id {id}", "Customer Account API Timeout")
		return {
				"success": False,
				"error": "Request timed out. Please try again."
		}
	except requests.exceptions.ConnectionError:
		frappe.log_error(f"Connection error for id {id}", "Customer Account API Connection")
		return {
				"success": False,
				"error": "Could not connect to the external service. Please check your connection."
		}
	except requests.exceptions.RequestException as e:
		frappe.log_error(f"Request error for id {id}: {str(e)}", "Customer Account API Request")
		return {
				"success": False,
				"error": f"Network error: {str(e)}"
		}
	except Exception as e:
		frappe.log_error(f"Unexpected error for id {id}: {str(e)}", "Customer Account API General")
		return {
				"success": False,
				"error": f"An unexpected error occurred: {str(e)}"
		}

@frappe.whitelist()
def update_account_level(uid, level):
	print(f"Updating account with uid {uid} to level {level}")
	input = {
		"uid": uid, # Account _id field 
		"level": level
	}

	mutation = """
	mutation accountUpdateLevel($input: AccountUpdateLevelInput!) {
		accountUpdateLevel(input: $input) {
			errors {
				message
			}
			accountDetails {
				id
				username
				level
			}
		}
	}
	"""
	
	payload = {
		"query": mutation,
		"variables": { "input": input }
	}
	try:
		response = requests.post(
			url=url,
			json=payload,
			headers=headers,
			timeout=30
		)
	
		response.raise_for_status()
		return response.json().get("data", {}).get("accountUpdateLevel", {})
		# result = response.json()

		# if "errors" in result:
		# 	error_messages = [error["message"] for error in result["errors"]]
	
		# mutation_result = result.get("data", {}).get("accountUpdateLevel", {})
		# if mutation_result.get("errors"):
		# 	error_messages = [error["message"] for error in mutation_result["errors"]]
		
		# return mutation_result
	except requests.exceptions.RequestException as e:
		frappe.log_error(f"GraphQL API Error: {str(e)}", "Account Upgrade Failed")
		frappe.throw(f"Failed to upgrade account: {str(e)}")
	
	except Exception as e:
		frappe.log_error(f"Unexpected error: {str(e)}", "Account Upgrade Error")
		frappe.throw(f"Unexpected error occurred: {str(e)}")
