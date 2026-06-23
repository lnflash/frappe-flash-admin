"""
Role-based access control for admin_panel API endpoints.

All whitelisted endpoints require authentication + specific roles.
This prevents any logged-in Frappe user from calling admin/financial operations.
"""

import functools

import frappe

# Roles that can access admin API endpoints
ADMIN_ROLES = ["System Manager", "Accounts Manager", "Flash Admin"]

# Stricter roles for financial mutations
FINANCIAL_ROLES = ["System Manager", "Accounts Manager"]


def require_roles(allowed_roles=None):
	"""Decorator: require the caller to have at least one of the allowed roles.

	Usage:
	    @frappe.whitelist()
	    @require_roles()  # uses ADMIN_ROLES by default
	    def my_endpoint(...):

	    @frappe.whitelist()
	    @require_roles(["System Manager"])
	    def sensitive_endpoint(...):
	"""
	if allowed_roles is None:
		allowed_roles = ADMIN_ROLES

	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kwargs):
			user = frappe.session.user
			if user == "Administrator":
				return func(*args, **kwargs)

			user_roles = set(frappe.get_roles(user))
			if not user_roles.intersection(allowed_roles):
				frappe.throw(
					f"User {user} does not have permission to perform this action. "
					f"Required roles: {', '.join(allowed_roles)}",
					frappe.PermissionError,
				)
			return func(*args, **kwargs)

		return wrapper

	return decorator


def require_admin():
	"""Shortcut for admin-level endpoints."""
	return require_roles(ADMIN_ROLES)


def require_financial():
	"""Shortcut for financial endpoints (cashout, journal entries)."""
	return require_roles(FINANCIAL_ROLES)


def audit_log(action, doc_type, doc_name, details=None):
	"""Write a best-effort audit entry (Frappe Comment) for admin mutations.

	Note: Comments are editable/deletable by System Managers, so this is a
	traceability aid, not a tamper-proof log. A dedicated append-only audit
	DocType is tracked as a follow-up.

	Args:
	    action: e.g. "approve_upgrade", "reject_upgrade", "update_status"
	    doc_type: Frappe DocType name
	    doc_name: Document name/ID
	    details: Optional dict with additional context
	"""
	try:
		log = frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": doc_type,
				"reference_name": str(doc_name),
				"content": (f"[{action}] by {frappe.session.user}" + (f" — {details}" if details else "")),
			}
		)
		log.insert(ignore_permissions=True)
	except Exception:
		# Audit logging is best-effort — don't block the operation
		frappe.logger().warning(f"Failed to write audit log for {action} on {doc_type} {doc_name}")
