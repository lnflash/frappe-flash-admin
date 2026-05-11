import frappe


def get_dashboard_data(data):
    """Return number cards for the Allowed Country list view."""
    return {
        "fieldname": "name",
        "transactions": [],
        "reports": [],
        "number_cards": [
            {
                "label": "Total Countries",
                "type": "count",
                "function": "Count",
                "filters": [],
                "doctype": "Allowed Country",
            },
            {
                "label": "Flash Allowed",
                "type": "count",
                "function": "Count",
                "filters": [["Allowed Country", "flash_allowed", "=", 1]],
                "doctype": "Allowed Country",
            },
            {
                "label": "Flash Restricted",
                "type": "count",
                "function": "Count",
                "filters": [["Allowed Country", "flash_allowed", "=", 0]],
                "doctype": "Allowed Country",
            },
            {
                "label": "Not High Risk",
                "type": "count",
                "function": "Count",
                "filters": [["Allowed Country", "bridge_risk_tier", "=", "Not High Risk"]],
                "doctype": "Allowed Country",
            },
            {
                "label": "Restricted Tier",
                "type": "count",
                "function": "Count",
                "filters": [["Allowed Country", "bridge_risk_tier", "=", "Restricted"]],
                "doctype": "Allowed Country",
            },
        ],
    }
