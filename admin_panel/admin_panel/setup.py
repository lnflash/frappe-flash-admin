import frappe


def after_migrate():
	sync_pages()


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
