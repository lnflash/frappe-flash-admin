import requests
import frappe
import jwt
import time
from typing import Any


class GraphQLError(Exception):
	"""GraphQL-specific error"""
	pass


# Module-level session for connection pooling
_session = None


def _get_session():
	"""Get or create a shared requests session for connection pooling"""
	global _session
	if _session is None:
		_session = requests.Session()
	return _session


class GraphQLClient:
	"""GraphQL client for admin API operations with JWT authentication"""

	def __init__(self):
		self.url = frappe.conf.get("flash_admin_api_url")
		self.api_key = frappe.conf.get("admin_api_key")
		self._session = _get_session()

		if not self.url:
			raise ValueError("flash_admin_api_url is not configured in site_config.json")
		if not self.api_key:
			raise ValueError("admin_api_key is not configured in site_config.json")

	def _create_jwt_token(self) -> str:
		"""Create JWT token with user context and expiration"""
		user = frappe.session.user
		user_roles = frappe.get_roles(user) if user else []
		now = int(time.time())
		payload = {
			"userId": user,
			"roles": user_roles,
			"iat": now,
			"exp": now + 3600,
			"iss": "frappe-admin-panel"
		}
		return jwt.encode(payload, self.api_key, algorithm='HS256')

	def _get_headers(self) -> dict:
		"""Get headers with JWT authentication context"""
		return {
			"Content-Type": "application/json",
			"Authorization": f"Bearer {self._create_jwt_token()}",
		}

	def _check_errors(self, response: dict, allow_not_found: bool = False) -> None:
		"""Check for GraphQL errors and raise exception if found"""
		errors = response.get('errors')
		if not errors:
			return
		if allow_not_found and any(e.get('code') == 'NOT_FOUND' for e in errors):
			return
		raise GraphQLError(f"GraphQL errors: {errors}")

	def execute_query(self, query: str, variables: dict = None) -> dict:
		"""Execute a GraphQL query and return the response"""
		payload = {"query": query}
		if variables:
			payload["variables"] = variables

		response = self._session.post(
			url=self.url,
			json=payload,
			headers=self._get_headers(),
			timeout=30
		)
		response.raise_for_status()
		return response.json()

	def execute_and_extract(self, query: str, variables: dict, data_key: str, allow_not_found: bool = False) -> Any:
		"""Execute query, check errors, and extract data by key"""
		resp = self.execute_query(query, variables)
		self._check_errors(resp, allow_not_found)
		if allow_not_found and resp.get('errors'):
			return None
		return resp.get("data", {}).get(data_key)
	
	# GraphQL query constants
	ACCOUNT_BY_PHONE_QUERY = """
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

	UPDATE_LEVEL_MUTATION = """
		mutation AccountUpdateLevel($input: AccountUpdateLevelInput!) {
			accountUpdateLevel(input: $input) {
				accountDetails {
					id
					level
					status
					username
					owner {
						phone
						email {
							address
						}
					}
				}
				errors {
					message
					code
					path
				}
			}
		}
	"""

	BROADCAST_ALERT_MUTATION = """
		mutation adminBroadcastSend($input: AdminBroadcastSendInput!) {
			adminBroadcastSend(input: $input) {
				success
				errors {
					message
				}
			}
		}
	"""

	ID_DOCUMENT_URL_QUERY = """
		query IdDocumentReadUrl($fileKey: String!) {
			idDocumentReadUrl(fileKey: $fileKey) {
				readUrl
				errors {
					message
				}
			}
		}
	"""

	def get_account_by_phone(self, phone: str) -> dict | None:
		"""Get account details by phone number"""
		return self.execute_and_extract(
			self.ACCOUNT_BY_PHONE_QUERY,
			{"phone": phone},
			"accountDetailsByUserPhone",
			allow_not_found=True
		)
	
	def update_account_level(self, uid: str, level: str) -> dict:
		"""Update account level"""
		return self.execute_and_extract(
			self.UPDATE_LEVEL_MUTATION,
			{"input": {"uid": uid, "level": level}},
			"accountUpdateLevel"
		) or {}
	
	def send_broadcast_alert(self, title: str, body: str, tag: str = "EMERGENCY") -> dict:
		"""Send broadcast alert to all users"""
		return self.execute_and_extract(
			self.BROADCAST_ALERT_MUTATION,
			{"input": {"title": title, "body": body, "tag": tag}},
			"adminBroadcastSend"
		)

	def get_id_document_read_url(self, file_key: str) -> dict:
		"""Get pre-signed URL for ID document from Digital Ocean Spaces"""
		return self.execute_and_extract(
			self.ID_DOCUMENT_URL_QUERY,
			{"fileKey": file_key},
			"idDocumentReadUrl"
		)