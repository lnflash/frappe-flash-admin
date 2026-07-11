# Append-only treasury audit trail. Rows are created exclusively by
# api/system_accounts.transfer_between_system_wallets (System Manager
# gated) — in_create hides the desk "New" button, and no role has
# write/create permission on purpose.

from frappe.model.document import Document


class SystemTransferLog(Document):
	pass
