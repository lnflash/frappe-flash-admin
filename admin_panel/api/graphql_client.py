import requests
import frappe
import jwt
import time


class GraphQLError(Exception):
	"""GraphQL-specific error"""
	pass


class GraphQLClient:
	"""GraphQL client for admin API operations with JWT authentication"""
	
	def __init__(self):
		self.url = frappe.conf.get("flash_admin_api_url")
		self.api_key = frappe.conf.get("admin_api_key")
	
	def create_jwt_token(self, user_id, roles, secret):
		"""Create JWT token with user context and expiration"""
		now = int(time.time())
		payload = {
			"userId": user_id,
			"roles": roles,
			"iat": now,
			"exp": now + 3600,
			"iss": "frappe-admin-panel"
		}
		return jwt.encode(payload, secret, algorithm='HS256')
	
	def get_headers(self):
		"""Get headers with JWT authentication context"""
		user = frappe.session.user
		user_roles = frappe.get_roles(user) if user else []
		jwt_token = self.create_jwt_token(user, user_roles, self.api_key)
		return {
			"Content-Type": "application/json",
			"Authorization": f"Bearer {jwt_token}",
		}
	
	def execute_query(self, query, variables=None):
		"""Execute a GraphQL query and return data or raise exception"""
		payload = {"query": query}
		if variables:
			payload["variables"] = variables
		
		headers = self.get_headers()
		response = requests.post(
			url=self.url,
			json=payload,
			headers=headers,
			timeout=30
		)
		
		response.raise_for_status()
		return response.json()
	
	def get_account_by_phone(self, phone):
		"""Get account details by phone number"""
		query = """
			query accountDetailsByUserPhone($phone: Phone!) {
				accountDetailsByUserPhone(phone: $phone) {
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
		"""
		
		resp = self.execute_query(query, {"phone": phone})

		errors = resp.get('errors')
		if errors:
			if any(e.get('code') == 'NOT_FOUND' for e in errors):
				return None 
			else:
				raise GraphQLError(f"GraphQL errors: {errors}")
		
		return resp["data"]["accountDetailsByUserPhone"]
	
	def update_account_level(self, uid, level):
		"""Update account level"""
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
		
		input_data = {
			"uid": uid,
			"level": level
		}
		
		data = self.execute_query(mutation, {"input": input_data})
		return data.get("accountUpdateLevel", {})
	
	def send_broadcast_alert(self, title, body, tag="EMERGENCY"):
		"""Send broadcast alert to all users"""
		mutation = """
			mutation adminBroadcastSend($input: AdminBroadcastSendInput!) {
				adminBroadcastSend(input: $input) {
					success
					errors {
						message
					}
				}
			}
		"""
		
		input_data = {
			"title": title,
			"body": body,
			"tag": tag
		}
		
		resp = self.execute_query(mutation, {"input": input_data})
		
		errors = resp.get('errors')
		if errors:
			raise GraphQLError(f"GraphQL errors: {errors}")
		
		return resp["data"]["adminBroadcastSend"]