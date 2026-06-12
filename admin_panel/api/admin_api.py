import functools
import re
import requests as requests_lib
import frappe
from .graphql_client import GraphQLClient, GraphQLError


def handle_api_errors(func):
	"""Decorator to handle common API errors consistently"""
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		try:
			return func(*args, **kwargs)
		except frappe.PermissionError:
			frappe.local.response["http_status_code"] = 403
			return {"error": "Permission denied"}
		except Exception as e:
			frappe.log_error(f"Admin API Error: {e}")
			frappe.local.response["http_status_code"] = 500
			return {"error": str(e)}

	return wrapper


# ── SVG Chart Helpers ─────────────────────────────────────────────


def _generate_bar_chart_svg(labels, values, color="#2563eb", max_bars=14):
    """Generate a simple inline SVG bar chart."""
    if not labels or not values or len(labels) != len(values):
        return ""

    max_val = max(values) or 1
    n = len(values)
    bar_w = max(24, min(48, 300 // n))
    gap = max(4, min(12, 20 // n))
    y_axis_w = 30
    x_axis_h = 20
    pad_top = 8
    pad_bottom = x_axis_h + 4
    pad_left = y_axis_w + 4
    pad_right = 8
    chart_w = pad_left + n * (bar_w + gap) + pad_right
    chart_h = 160
    plot_top = pad_top
    plot_bottom = chart_h - pad_bottom
    plot_h = plot_bottom - plot_top

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {chart_w} {chart_h}" '
        f'style="width:100%;height:160px;display:block">'
    ]

    # Horizontal gridlines
    for i in range(5):
        y = plot_top + (plot_h / 5) * i
        yv = round(max_val - (max_val / 5) * i)
        parts.append(
            f'<line x1="{pad_left}" y1="{y}" x2="{chart_w - pad_right}" y2="{y}" '
            f'stroke="#f3f4f6" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_left - 4}" y="{y + 3}" text-anchor="end" '
            f'font-size="9" fill="#9ca3af">{yv}</text>'
        )

    # Bars + labels
    for i, (label, val) in enumerate(zip(labels, values)):
        x = pad_left + i * (bar_w + gap)
        h = (val / max_val) * plot_h if max_val > 0 else 0
        y = plot_bottom - h
        # Bar
        parts.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{max(h, 1)}" '
            f'fill="{color}" rx="2" opacity="0.85"/>'
        )
        # Value label on bar
        if val > 0:
            parts.append(
                f'<text x="{x + bar_w / 2}" y="{y - 4}" text-anchor="middle" '
                f'font-size="10" fill="{color}" font-weight="600">{val}</text>'
            )
        # Date label
        parts.append(
            f'<text x="{x + bar_w / 2}" y="{chart_h - 3}" text-anchor="middle" '
            f'font-size="8" fill="#9ca3af">{label}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ── Dashboard Stats ──────────────────────────────────────────────


def get_dashboard_stats():
    """Get summary stats for the admin dashboard."""
    pending = frappe.db.count("Account Upgrade Request", {"status": "Pending"})
    approved = frappe.db.count("Account Upgrade Request", {"status": "Approved"})
    rejected = frappe.db.count("Account Upgrade Request", {"status": "Rejected"})

    today = frappe.utils.nowdate()
    approved_today = frappe.db.count("Account Upgrade Request", {
        "status": "Approved",
        "modified": [">=", today],
    })

    all_records = frappe.get_all(
        "Account Upgrade Request",
        fields=["name", "username", "full_name", "phone_number", "email",
                "requested_level", "current_level", "status", "creation"],
        order_by="creation desc",
        limit_page_length=500,
    )

    # ── Bridge chart data ──
    # Daily counts for the last 7 days
    from datetime import timedelta

    today_dt = frappe.utils.getdate(today)
    labels = []
    for i in range(6, -1, -1):
        d = today_dt - timedelta(days=i)
        labels.append(d)

    bridge_volume_values = []
    bridge_failure_values = []
    for day in labels:
        day_start = day.strftime("%Y-%m-%d")
        day_end = (day + timedelta(days=1)).strftime("%Y-%m-%d")

        # Volume count
        vol = frappe.db.sql("""
            SELECT COUNT(*) as cnt FROM `tabBridge Transfer Request`
            WHERE creation >= %s AND creation < %s
        """, values=[day_start, day_end], as_dict=True)
        bridge_volume_values.append(vol[0]["cnt"] if vol else 0)

        # Failure count
        fail = frappe.db.sql("""
            SELECT COUNT(*) as cnt FROM `tabBridge Transfer Request`
            WHERE creation >= %s AND creation < %s
            AND IFNULL(failure_reason, '') != ''
        """, values=[day_start, day_end], as_dict=True)
        bridge_failure_values.append(fail[0]["cnt"] if fail else 0)

    # Format labels for JS display
    date_labels = [frappe.utils.format_date(d.strftime("%Y-%m-%d"), "MMM d") for d in labels]

    return {
        "upgrade_requests": {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approved_today": approved_today,
        },
        "recent_requests": all_records[:8],
        "all_requests": all_records,
        "total_requests": pending + approved + rejected,
        "bridge_charts": {
            "volume": {
                "title": "Bridge Volume",
                "labels": date_labels,
                "datasets": [{"name": "Volume", "values": bridge_volume_values}],
                "svg": _generate_bar_chart_svg(date_labels, bridge_volume_values, "#2563eb"),
            },
            "failures": {
                "title": "Bridge Audit Failures",
                "labels": date_labels,
                "datasets": [{"name": "Failures", "values": bridge_failure_values}],
                "svg": _generate_bar_chart_svg(date_labels, bridge_failure_values, "#dc2626"),
            },
        },
    }


# ── Cashout Requests API ──────────────────────────────────────────


CASHOUT_STATUS_DISPLAY_MAP = {
    "Pending": "Pending",
    "Draft": "Pending",
    "In Progress": "In Progress",
    "Completed": "Paid",
    "Canceled": "Canceled",
}


def _enrich_cashout(cashout_doc) -> dict:
    """Enrich a Cashout doctype record with Customer and Bank Account fields."""
    row = dict(cashout_doc)

    # Resolve Customer display fields
    customer_info = {}
    if row.get("customer"):
        customer_info = frappe.db.get_value(
            "Customer",
            row["customer"],
            ["customer_name", "mobile_no", "email_id"],
            as_dict=True,
        ) or {}
    row["username"] = row.get("customer", "")
    row["full_name"] = customer_info.get("customer_name", "")
    row["phone_number"] = customer_info.get("mobile_no", "")
    row["email"] = customer_info.get("email_id", "")

    # Resolve Bank Account display fields
    bank_info = {}
    if row.get("bank_account"):
        bank_info = frappe.db.get_value(
            "Bank Account",
            row["bank_account"],
            ["bank", "bank_account_no", "account_type", "account_name"],
            as_dict=True,
        ) or {}
    # Mask account number for display
    raw_no = (bank_info.get("bank_account_no") or "")
    row["bank_name"] = bank_info.get("bank", "")
    row["account_number"] = f"****{raw_no[-4:]}" if len(raw_no) >= 4 else raw_no
    row["account_type"] = bank_info.get("account_type", "")
    row["bank_label"] = bank_info.get("account_name", "")

    # Map fields to match JS expectations
    row["send"] = row.get("user_pays")
    row["account_type"] = row.get("account_type", "")
    row["customer_note"] = row.get("notes", "")
    row["date"] = row.get("creation", "")[:10] if row.get("creation") else ""

    # Convert status to display status
    raw_status = row.get("status", "Pending")
    row["display_status"] = CASHOUT_STATUS_DISPLAY_MAP.get(raw_status, "Pending")

    return row


@frappe.whitelist(allow_guest=True)
@handle_api_errors
def get_cashout_requests():
    """Fetch Cashout records enriched with Customer & Bank Account data."""
    page = int(frappe.request.args.get("page", 1))
    page_size = int(frappe.request.args.get("page_size", 20))
    status_filter = frappe.request.args.get("status", "")
    search_query = frappe.request.args.get("search", "").strip().lower()

    filters = {}
    if status_filter:
        if status_filter == "Pending":
            filters["status"] = ["in", ["Pending", "Draft"]]
        elif status_filter == "Paid":
            filters["status"] = "Completed"
        elif status_filter == "In Progress":
            filters["status"] = "In Progress"
        elif status_filter == "Canceled":
            filters["status"] = "Canceled"

    # Base query
    all_records = frappe.get_all(
        "Cashout",
        filters=filters,
        fields=[
            "name", "customer", "bank_account", "amount", "currency",
            "status", "user_pays", "notes", "creation", "modified",
        ],
        order_by="creation desc",
        limit_page_length=1000,
    )

    # Enrich with customer & bank info
    enriched = [_enrich_cashout(r) for r in all_records]

    # Client-side search filter
    if search_query:
        filtered = []
        digits_only = re.sub(r"\D", "", search_query)
        for r in enriched:
            haystack = (
                f"{r.get('full_name', '')} {r.get('phone_number', '')} "
                f"{r.get('username', '')} {r.get('email', '')} "
                f"{r.get('customer', '')}"
            ).lower()
            # Also search by phone digits only
            r_digits = re.sub(r"\D", "", r.get("phone_number", ""))
            if search_query in haystack or (digits_only and digits_only in r_digits):
                filtered.append(r)
        enriched = filtered

    total = len(enriched)
    start = (page - 1) * page_size
    end = start + page_size
    page_records = enriched[start:end]

    return {
        "records": page_records,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": -(-total // page_size),  # ceiling
    }


@frappe.whitelist(allow_guest=True)
@handle_api_errors
def record_cashout_payment(name):
    """Mark a Cashout record as Completed."""
    doc = frappe.get_doc("Cashout", name)
    doc.status = "Completed"
    doc.save()
    frappe.db.commit()
    return {"status": "ok", "name": name}
