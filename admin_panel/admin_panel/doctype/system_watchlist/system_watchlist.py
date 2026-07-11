# UI-managed treasury watchlist. Rows are ops accounts to observe on the
# System Accounts page; allow_transfers is a per-account opt-in (default
# off) that makes an account a valid transfer endpoint. Managed via the
# api/system_accounts watchlist endpoints (System Manager gated).

from frappe.model.document import Document


class SystemWatchlist(Document):
	pass
