"""Read-only client for the IBEX Hub API.

Used by the wallet-census background job to page through every organization
account and read its live balance. Authentication is OAuth2 client-credentials
(NOT email/password): a token is fetched from the auth domain and sent to the
hub as a RAW ``Authorization`` header value (no ``Bearer`` prefix).

Verified against the ibex-client library and the Flash backend:
  * token endpoint  POST {auth_domain}/oauth/token  (grant_type=client_credentials)
  * hub base        {hub_url}
  * bulk list       GET  {hub_url}/v2/account?expand=true&page=N&limit=100
  * balances are dollars, present only when expand=true (absent => zero)
  * currencyId 3 => USD, 29 => USDT (BTC is not held in IBEX)

Config (site_config.json / frappe.conf):
  ibex_client_id, ibex_client_secret          (required)
  ibex_environment                             (optional, default "production")
  ibex_auth_domain, ibex_hub_url, ibex_audience(optional overrides)
"""

import time

import frappe
import requests

# Only the production environment is baked in with verified URLs. Any field can
# be overridden via config for sandbox / staging without a code change.
_PRODUCTION = {
	"auth_domain": "https://auth.hub.poweredbyibex.io",
	"hub_url": "https://ibexhub-api.poweredbyibex.io",
	"audience": "https://ibexhub.ibexmercado.com",
}

# Bulk-endpoint page size. Valid range is [10, 100]; 100 minimizes round-trips.
PAGE_LIMIT = 100

# Courtesy throttle between bulk reads. The read path is not rate-limited nearly
# as tightly as account creation, but we stay polite (~1 req/s).
REQUEST_INTERVAL_SECONDS = 1.0

_session = None


def _get_session() -> requests.Session:
	global _session
	if _session is None:
		_session = requests.Session()
	return _session


class IbexError(Exception):
	"""IBEX Hub API error."""


class IbexClient:
	"""Minimal read-only IBEX Hub client with client-credentials auth."""

	def __init__(self):
		env = frappe.conf.get("ibex_environment") or "production"
		defaults = _PRODUCTION if env == "production" else {}

		self.auth_domain = frappe.conf.get("ibex_auth_domain") or defaults.get("auth_domain")
		self.hub_url = frappe.conf.get("ibex_hub_url") or defaults.get("hub_url")
		self.audience = frappe.conf.get("ibex_audience") or defaults.get("audience")
		self.client_id = frappe.conf.get("ibex_client_id")
		self.client_secret = frappe.conf.get("ibex_client_secret")

		missing = [
			key
			for key, val in {
				"ibex_client_id": self.client_id,
				"ibex_client_secret": self.client_secret,
				"ibex_hub_url": self.hub_url,
				"ibex_auth_domain": self.auth_domain,
				"ibex_audience": self.audience,
			}.items()
			if not val
		]
		if missing:
			raise ValueError(f"IBEX config missing from site_config.json: {', '.join(missing)}")

		self._session = _get_session()
		self._token = None
		self._token_expires_at = 0.0

	def _fetch_token(self) -> str:
		"""Fetch a fresh client-credentials access token and cache it to its TTL."""
		resp = self._session.post(
			f"{self.auth_domain}/oauth/token",
			data={
				"grant_type": "client_credentials",
				"client_id": self.client_id,
				"client_secret": self.client_secret,
				"audience": self.audience,
			},
			headers={"Content-Type": "application/x-www-form-urlencoded"},
			timeout=30,
		)
		if not resp.ok:
			raise IbexError(f"IBEX token request failed: {resp.status_code} {resp.text[:200]}")
		body = resp.json()
		token = body.get("access_token")
		if not token:
			raise IbexError("IBEX token response missing access_token")
		# Refresh a minute early to avoid using a token that expires mid-request.
		self._token = token
		self._token_expires_at = time.time() + max(int(body.get("expires_in", 3600)) - 60, 0)
		return token

	def _get_token(self) -> str:
		if not self._token or time.time() >= self._token_expires_at:
			return self._fetch_token()
		return self._token

	def _get(self, path: str, params: dict) -> requests.Response:
		"""GET with a raw-token Authorization header; refetch + retry once on 401."""
		url = f"{self.hub_url}{path}"
		resp = self._session.get(url, params=params, headers={"Authorization": self._get_token()}, timeout=30)
		if resp.status_code == 401:
			self._fetch_token()
			resp = self._session.get(
				url, params=params, headers={"Authorization": self._get_token()}, timeout=30
			)
		if not resp.ok:
			raise IbexError(f"IBEX GET {path} failed: {resp.status_code} {resp.text[:200]}")
		return resp

	def list_accounts_page(self, page: int, limit: int = PAGE_LIMIT) -> list[dict]:
		"""Return one page of org accounts, balances included (dollars)."""
		resp = self._get("/v2/account", {"expand": "true", "page": page, "limit": limit})
		data = resp.json()
		if not isinstance(data, list):
			raise IbexError(f"IBEX /v2/account returned non-list: {type(data).__name__}")
		return data

	def iter_all_accounts(self, progress_cb=None):
		"""Yield every org account across all pages, pacing between requests.

		progress_cb(pages_done, accounts_seen) is called after each page so the
		caller can persist scan progress for the UI.
		"""
		page = 1
		seen = 0
		while True:
			batch = self.list_accounts_page(page, PAGE_LIMIT)
			if not batch:
				break
			for account in batch:
				seen += 1
				yield account
			if progress_cb:
				progress_cb(page, seen)
			if len(batch) < PAGE_LIMIT:
				break
			page += 1
			time.sleep(REQUEST_INTERVAL_SECONDS)
