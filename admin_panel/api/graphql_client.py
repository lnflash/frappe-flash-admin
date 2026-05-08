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
	# Reusable fragment for account detail fields
	ACCOUNT_DETAIL_FRAGMENT = """
	fragment AccountDetail on AuditedAccount {
		id
		uuid
		username
		npub
		level
		status
		title
		erpParty
		owner {
			id
			phone
			language
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
		merchants {
			id
			title
			latitude
			longitude
			validated
			username
			createdAt
		}
		createdAt
	}
	"""

	ACCOUNT_BY_PHONE_QUERY = """
		query accountDetailsByUserPhone($phone: Phone!) {
			accountDetailsByUserPhone(phone: $phone) {
				...AccountDetail
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	UPDATE_LEVEL_MUTATION = """
		mutation accountUpdateLevel($input: AccountUpdateLevelInput!) {
			accountUpdateLevel(input: $input) {
				errors {
					message
				}
				accountDetails {
					id
					username
					level
					status
					title
					owner {
						id
						language
						phone
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
					erpParty
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

	NOTIFICATION_TOPICS_QUERY = """
		query {
			notificationTopics
		}
	"""

	SEND_NOTIFICATION_MUTATION = """
		mutation SendNotification($input: SendNotificationInput!) {
			sendNotification(input: $input) {
				errors {
					message
				}
				success
			}
		}
	"""

	ACCOUNT_BY_USERNAME_QUERY = """
		query accountDetailsByUsername($username: Username!) {
			accountDetailsByUsername(username: $username) {
				...AccountDetail
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	ACCOUNT_BY_EMAIL_QUERY = """
		query accountDetailsByEmail($email: EmailAddress!) {
			accountDetailsByUserEmail(email: $email) {
				...AccountDetail
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	ACCOUNT_BY_ID_QUERY = """
		query accountDetailsByAccountId($accountId: ID!) {
			accountDetailsByAccountId(accountId: $accountId) {
				...AccountDetail
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	UPDATE_STATUS_MUTATION = """
		mutation accountUpdateStatus($input: AccountUpdateStatusInput!) {
			accountUpdateStatus(input: $input) {
				errors {
					message
				}
				accountDetails {
					...AccountDetail
				}
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	USER_UPDATE_PHONE_MUTATION = """
		mutation userUpdatePhone($input: UserUpdatePhoneInput!) {
			userUpdatePhone(input: $input) {
				errors {
					message
				}
				accountDetails {
					...AccountDetail
				}
			}
		}
	""" + ACCOUNT_DETAIL_FRAGMENT

	MERCHANT_MAP_VALIDATE_MUTATION = """
		mutation merchantMapValidate($input: MerchantMapValidateInput!) {
			merchantMapValidate(input: $input) {
				errors {
					message
				}
				merchant {
					id
					title
					latitude
					longitude
					validated
					username
				}
			}
		}
	"""

	MERCHANT_MAP_DELETE_MUTATION = """
		mutation merchantMapDelete($input: MerchantMapDeleteInput!) {
			merchantMapDelete(input: $input) {
				errors {
					message
				}
				merchant {
					id
					title
					latitude
					longitude
					validated
					username
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

	def update_account_level(self, uid: str, level: str, erp_party: str = None) -> dict:
		"""Update account level"""
		variables = {"input": {"uid": uid, "level": level}}
		if erp_party:
			variables["input"]["erpParty"] = erp_party
		return self.execute_and_extract(
			self.UPDATE_LEVEL_MUTATION,
			variables,
			"accountUpdateLevel"
		) or {}

	def get_id_document_read_url(self, file_key: str) -> dict:
		"""Get pre-signed URL for ID document from Digital Ocean Spaces"""
		return self.execute_and_extract(
			self.ID_DOCUMENT_URL_QUERY,
			{"fileKey": file_key},
			"idDocumentReadUrl"
		)

	def get_notification_topics(self) -> list:
		"""Fetch available notification topics from Flash API"""
		resp = self.execute_query(self.NOTIFICATION_TOPICS_QUERY)
		self._check_errors(resp)
		return resp.get("data", {}).get("notificationTopics", [])

	def send_alert(self, topic: str, title: str, body: str) -> dict:
		"""Send alert to Flash app users via topic"""
		return self.execute_and_extract(
			self.SEND_NOTIFICATION_MUTATION,
			{"input": {"topic": topic, "title": title, "body": body}},
			"sendNotification"
		)

	def get_account_by_username(self, username: str) -> dict | None:
		"""Get account details by username"""
		return self.execute_and_extract(
			self.ACCOUNT_BY_USERNAME_QUERY,
			{"username": username},
			"accountDetailsByUsername",
			allow_not_found=True
		)

	def get_account_by_email(self, email: str) -> dict | None:
		"""Get account details by email address"""
		return self.execute_and_extract(
			self.ACCOUNT_BY_EMAIL_QUERY,
			{"email": email},
			"accountDetailsByUserEmail",
			allow_not_found=True
		)

	def get_account_by_id(self, account_id: str) -> dict | None:
		"""Get account details by account ID"""
		return self.execute_and_extract(
			self.ACCOUNT_BY_ID_QUERY,
			{"accountId": account_id},
			"accountDetailsByAccountId",
			allow_not_found=True
		)

	def update_account_status(self, uid: str, status: str, comment: str = None) -> dict:
		"""Change account status via admin mutation"""
		variables = {"input": {"uid": uid, "status": status}}
		if comment:
			variables["input"]["comment"] = comment
		return self.execute_and_extract(
			self.UPDATE_STATUS_MUTATION,
			variables,
			"accountUpdateStatus"
		) or {}

	def update_user_phone(self, account_uuid: str, phone: str) -> dict:
		"""Update phone number for a user"""
		return self.execute_and_extract(
			self.USER_UPDATE_PHONE_MUTATION,
			{"input": {"accountUuid": account_uuid, "phone": phone}},
			"userUpdatePhone"
		) or {}

	def validate_merchant(self, merchant_id: str) -> dict:
		"""Approve a merchant map entry"""
		return self.execute_and_extract(
			self.MERCHANT_MAP_VALIDATE_MUTATION,
			{"input": {"id": merchant_id}},
			"merchantMapValidate"
		) or {}

	def delete_merchant(self, merchant_id: str) -> dict:
		"""Delete a merchant map entry"""
		return self.execute_and_extract(
			self.MERCHANT_MAP_DELETE_MUTATION,
			{"input": {"id": merchant_id}},
			"merchantMapDelete"
		) or {}
