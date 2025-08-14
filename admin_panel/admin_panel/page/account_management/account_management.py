import frappe
from frappe import _

def get_context(context):
    """Set up the page context"""
    context.no_cache = 1
    
    # Check permissions
    if not frappe.has_permission("Customer", "read"):
        frappe.throw(_("Not permitted to access customer information"), 
                    frappe.PermissionError)
    
    return context