import frappe

from admin_panel.admin_panel.doctype.allowed_country.seed import seed_allowed_countries


def after_migrate():
	ensure_roles()
	sync_pages()
	delete_legacy_pages()
	seed_allowed_countries()


def ensure_roles():
	"""Create custom roles referenced by RBAC (admin_panel.api.auth) if missing.

	The Account Upgrade Request permissions and the require_admin decorator
	reference "Flash Admin"; without the Role record it cannot be assigned.
	"""
	for role_name in ("Flash Admin",):
		if not frappe.db.exists("Role", role_name):
			role = frappe.new_doc("Role")
			role.role_name = role_name
			role.desk_access = 1
			role.flags.ignore_permissions = True
			role.insert()
	frappe.db.commit()


def sync_pages():
	pages = [
		{
			"name": "alert-users",
			"title": "Alert Users",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "account-management",
			"title": "Account Management",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "account-hub",
			"title": "Account Hub",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "admin-dashboard",
			"title": "Dashboard",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "transfer-requests",
			"title": "Transfer Requests",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
		{
			"name": "wallet-census",
			"title": "Wallet Census",
			"module": "Admin Panel",
			"standard": "Yes",
			"roles": [],
		},
	]

	for page_data in pages:
		name = page_data["name"]
		if frappe.db.exists("Page", name):
			doc = frappe.get_doc("Page", name)
			doc.update(page_data)
		else:
			doc = frappe.new_doc("Page")
			doc.update(page_data)

		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True
		doc.save()

	frappe.db.commit()


def delete_legacy_pages():
	if frappe.db.exists("Page", "cashout-requests"):
		frappe.delete_doc("Page", "cashout-requests", ignore_permissions=True, force=True)
		frappe.db.commit()
