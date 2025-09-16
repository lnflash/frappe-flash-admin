import frappe

def after_install():
    """Run after app installation"""

    # Create Accounts Manager role if it doesn't exist
    if not frappe.db.exists("Role", "Accounts Manager"):
        role_doc = frappe.get_doc({
            "doctype": "Role",
            "role_name": "Accounts Manager",
            "desk_access": 1,
            "disabled": 0
        })
        role_doc.insert(ignore_permissions=True)
        frappe.db.commit()

    # Import fixtures
    frappe.reload_doc("admin_panel", "page", "account_management", force=True)

    # Clear cache
    frappe.clear_cache()

    print("Admin Panel app installed successfully!")