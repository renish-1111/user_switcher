# * user_switcher/user_switcher/report/user_switch_log_report/user_switch_log_report.py
import frappe
from frappe import _


def execute(filters: dict | None = None) -> tuple[list[dict], list[dict]]:
	"""Return columns and rows of User Switch Logs, filtered by date, users and action.

	Args:
		filters: Optional `from_date`, `to_date`, `real_user`, `target_user`, `action`, `ip_address`.

	Returns:
		Tuple of (columns, rows), newest first.
	"""
	return get_columns(), get_data(frappe._dict(filters or {}))


def get_columns() -> list[dict]:
	"""Return the report column definitions."""
	return [
		{"label": _("Time"), "fieldname": "creation", "fieldtype": "Datetime", "width": 170},
		{
			"label": _("Real User"),
			"fieldname": "real_user",
			"fieldtype": "Link",
			"options": "User",
			"width": 220,
		},
		{
			"label": _("Target User"),
			"fieldname": "target_user",
			"fieldtype": "Link",
			"options": "User",
			"width": 220,
		},
		{"label": _("Action"), "fieldname": "action", "fieldtype": "Data", "width": 110},
		{"label": _("IP Address"), "fieldname": "ip_address", "fieldtype": "Data", "width": 130},
		{
			"label": _("Log"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "User Switch Log",
			"width": 120,
		},
	]


def get_data(filters: frappe._dict) -> list[dict]:
	"""Fetch logs matching `filters`, newest first, capped at 5000 rows."""
	conditions = {
		k: filters[k] for k in ("real_user", "target_user", "action", "ip_address") if filters.get(k)
	}
	if filters.from_date and filters.to_date:
		conditions["creation"] = ["between", [filters.from_date, f"{filters.to_date} 23:59:59"]]
	elif filters.from_date:
		conditions["creation"] = [">=", filters.from_date]
	elif filters.to_date:
		conditions["creation"] = ["<=", f"{filters.to_date} 23:59:59"]

	return frappe.get_all(
		"User Switch Log",
		filters=conditions,
		fields=["creation", "real_user", "target_user", "action", "ip_address", "name"],
		order_by="creation desc",
		limit=5000,
	)
