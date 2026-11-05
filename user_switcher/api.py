# * user_switcher/api.py

import re

import frappe
from frappe import _
from frappe.sessions import delete_session
from frappe.utils import cint, validate_email_address

ALLOWED_ROLES = {"System Manager"}
AUTOMATIC_ROLES = ["All", "Guest", "Administrator", "Desk User"]
# Desk route views whose second part is a doctype (frappe.get_route())
DOCTYPE_VIEWS = ("List", "Form", "Report", "Tree", "Image", "Kanban", "Calendar", "Gantt", "Dashboard", "Map")
# ? DefaultValue PARENT HOLDING EACH USER'S ROLES FROM BEFORE THE SWITCHER FIRST CHANGED THEM
ROLE_SNAPSHOTS = "__user_switcher_roles"
# Test users carry this in their bio (see create_test_user)
TEST_USER_MARK = "%User Switcher%"


def _real_user() -> str:
	"""The user who actually logged in, even while switched into someone else."""
	data = getattr(frappe.session, "data", None)
	if data is None and hasattr(frappe.session, "get"):
		data = frappe.session.get("data")
	impersonator = (data or {}).get("impersonated_by") if isinstance(data, dict) else None
	session_user = getattr(frappe.session, "user", None)
	if not session_user and hasattr(frappe.session, "get"):
		session_user = frappe.session.get("user")
	return impersonator or session_user or "Guest"


def _is_enabled() -> bool:
	# ? NEEDS BOTH SETTINGS: developer_mode ALONE IS OFTEN ON BY HABIT (OR BY MISTAKE ON A LIVE SITE)
	return bool(frappe.conf.developer_mode and frappe.conf.get("user_switcher_enabled"))


def _escape_like(txt: str) -> str:
	"""Escape `\\`, `%` and `_` so user text matches literally inside a LIKE filter."""
	if not isinstance(txt, str):
		txt = str(txt or "")
	return txt.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _str_list(value) -> list[str]:
	"""Parse a list (or its JSON, or one plain string) into stripped, non-empty strings."""
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except Exception:
			pass
	if isinstance(value, str):
		value = [value]
	if not isinstance(value, (list, tuple, set)):
		return []
	return [str(v).strip() for v in value if isinstance(v, str | int) and str(v).strip()]


def _match_rank(text: str, query: str) -> int:
	"""Frappe-style search rank: 0 = no match, lower = better.

	Typed words may match the starts of words in any order ("inv sal" -> Sales Invoice), the
	letters may spell the initials ("si" -> Sales Invoice), and a plain substring still matches.
	"""
	q = str(query or "").strip().casefold()
	if not q:
		return 1
	t = str(text or "").casefold()
	words = [w for w in re.split(r"[\s._\-/]+", t) if w]
	parts = q.split()
	if t == q:
		return 1
	if t.startswith(q):
		return 2
	if len(parts) == 1 and len(q) > 1 and "".join(w[0] for w in words).startswith(q):
		return 3
	if all(any(w.startswith(p) for w in words) for p in parts):
		return 4
	if q in t:
		return 5
	return 0


def _blocked_targets(real_user: str) -> list[str]:
	"""Users `real_user` may not switch into.

	Administrator is blocked for everyone else. Other System Managers are blocked unless
	`real_user` created them and they have no password yet (i.e. they are still test users).
	"""
	canonical_real = frappe.db.get_value("User", (real_user or "").strip(), "name") or real_user
	real_user = canonical_real
	if real_user == "Administrator":
		return []

	managers = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": "System Manager"},
		pluck="parent",
		ignore_permissions=True,
	)
	managers = [m for m in managers if m.casefold() != real_user.casefold()]
	if not managers:
		return ["Administrator"]

	owned = frappe.get_all(
		"User", filters={"name": ["in", managers], "owner": real_user}, pluck="name", ignore_permissions=True
	)
	# ? __Auth IS NOT A DOCTYPE, SO frappe.get_all CANNOT READ IT
	with_password = frappe.db.sql_list(
		"select name from __Auth where doctype = 'User' and fieldname = 'password' and name in %s",
		(tuple(owned) or ("",),),
	)
	allowed = set(owned) - set(with_password)
	return ["Administrator", *(m for m in managers if m not in allowed)]


def _can_switch(real_user: str | None = None) -> bool:
	if not _is_enabled():
		return False
	real_user = real_user or _real_user()
	if not real_user or real_user == "Guest":
		return False
	user_info = frappe.db.get_value("User", (real_user or "").strip(), ["name", "enabled"], as_dict=True)
	if not user_info or not user_info.enabled or user_info.name == "Guest":
		return False
	if user_info.name == "Administrator":
		return True
	return bool(ALLOWED_ROLES & set(frappe.get_roles(user_info.name)))


def _deny(message: str, action: str, target: str | None = None) -> None:
	"""Log a refused request, then raise PermissionError.

	Args:
		message: Translated text shown to the caller.
		action: Short name of what was attempted, e.g. "switch" or "manage_roles".
		target: The user the request was aimed at, if any.

	Raises:
		frappe.PermissionError: Always.
	"""
	frappe.logger("user_switcher").warning(
		"denied %s: session_user=%s real_user=%s target=%s ip=%s",
		action,
		frappe.session.user,
		_real_user(),
		target,
		getattr(frappe.local, "request_ip", None),
	)
	frappe.throw(message, frappe.PermissionError)


def end_orphaned_session() -> None:
	"""`before_request` hook: end an impersonated session once its real user may no longer switch.

	Without this, disabling the System Manager, removing their role or turning the switcher off
	would leave the impersonated session running as the target user until it expires.

	Raises:
		frappe.SessionExpired: The session was ended; the browser goes back to the login page.
	"""
	data = getattr(frappe.session, "data", None)
	if data is None and hasattr(frappe.session, "get"):
		data = frappe.session.get("data")
	impersonator = (data or {}).get("impersonated_by") if isinstance(data, dict) else None
	if not impersonator or _can_switch(impersonator):
		return
	frappe.logger("user_switcher").warning(
		"ended orphaned session: session_user=%s impersonated_by=%s", frappe.session.user, impersonator
	)
	delete_session(frappe.session.sid, reason="User Switcher: the real user may no longer switch")
	# The error handler rolls the request back, which would undo the delete
	frappe.db.commit()
	raise frappe.SessionExpired


@frappe.whitelist()
def get_context(
	txt: str | None = None,
	user_type: str | None = None,
	limit: int | str = 30,
	cached: list | str | None = None,
	role: list | str | None = None,
	role_match: str = "any",
):
	"""Return switcher state and a filtered user list.

	Args:
		txt: Optional text matched against user id and full name.
		user_type: Optional "System User" or "Website User" filter.
		limit: Max users returned (capped at 100); 0 returns only the `allowed` flag.
		cached: Optional user ids the browser has pinned or remembered; those that were deleted
			or disabled come back in `stale` so the UI can forget them.
		role: Optional role, or list (or JSON list) of roles, to filter by.
		role_match: "all" returns users holding every role in `role`; anything else, any of them.

	Returns:
		`{"allowed": False}` for unauthorised users (never throws), else the switcher state.
	"""
	real_user = _real_user()
	if not _can_switch(real_user):
		return {"allowed": False}

	try:
		limit = int(limit)
	except ValueError, TypeError:
		limit = 30
	limit = max(0, min(limit, 100))
	if not limit:
		return {"allowed": True}

	users = _find_users(real_user, txt, user_type, limit, _str_list(role), role_match == "all")

	return {
		"allowed": True,
		"real_user": _user_info(real_user),
		"current_user": _user_info(frappe.session.user),
		"is_switched": real_user != frappe.session.user,
		"users": users,
		"stale": _stale_users(cached),
	}


def _stale_users(cached: list | str | None) -> list[str]:
	if isinstance(cached, str):
		try:
			cached = frappe.parse_json(cached)
		except Exception:
			cached = []
	if not isinstance(cached, (list, tuple, set)):
		return []
	names = [n.strip() for n in cached if isinstance(n, str) and n.strip()][:200]
	if not names:
		return []
	alive = set(
		frappe.get_all(
			"User", filters={"name": ["in", names], "enabled": 1}, pluck="name", ignore_permissions=True
		)
	)
	seen = set()
	stale = []
	for n in names:
		if n not in alive and n not in seen:
			seen.add(n)
			stale.append(n)
	return stale


def _users_with_roles(roles: list[str], match_all: bool) -> list[str]:
	"""Users holding any (or, with `match_all`, every) role in `roles`."""
	# ponytail: loads every holder of these roles; fine up to a few thousand users
	rows = frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "role": ["in", roles]},
		fields=["parent", "role"],
		ignore_permissions=True,
	)
	held = {}
	for row in rows:
		held.setdefault(row.parent, set()).add(row.role)
	need = len(set(roles)) if match_all else 1
	return [user for user, user_roles in held.items() if len(user_roles) >= need]


def _find_users(
	real_user: str,
	txt: str | None,
	user_type: str | None,
	limit: int,
	roles: list[str] | None = None,
	match_all: bool = False,
) -> list[dict]:
	exclude_users = {"Guest"}
	if getattr(frappe.session, "user", None):
		exclude_users.add(frappe.session.user)
	exclude_users.update(_blocked_targets(real_user))

	filters = [["enabled", "=", 1], ["name", "not in", list(exclude_users)]]

	if user_type in ("System User", "Website User"):
		filters.append(["user_type", "=", user_type])
	if roles:
		filters.append(["name", "in", _users_with_roles(roles, match_all) or [""]])

	or_filters = None
	clean_txt = str(txt or "").strip()
	if clean_txt:
		like = f"%{_escape_like(clean_txt)}%"
		or_filters = {"name": ["like", like], "full_name": ["like", like]}

	users = frappe.get_all(
		"User",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "user_image", "user_type"],
		order_by="last_active desc",
		limit=limit,
		ignore_permissions=True,
	)
	_attach_roles(users)
	return users


def _user_info(user: str) -> dict:
	info = frappe.db.get_value(
		"User", (user or "").strip(), ["name", "full_name", "user_image", "user_type"], as_dict=True
	)
	return info or {"name": user}


def _attach_roles(users: list[dict]) -> None:
	"""Add each user's roles (minus the automatic ones), so the UI can hint at who is who."""
	if not users:
		return
	rows = frappe.get_all(
		"Has Role",
		filters={
			"parenttype": "User",
			"parent": ["in", [u.name for u in users]],
			"role": ["not in", AUTOMATIC_ROLES],
		},
		fields=["parent", "role"],
		order_by="role asc",
		ignore_permissions=True,
	)
	roles_by_user = {}
	for row in rows:
		roles_by_user.setdefault(row.parent, []).append(row.role)
	for u in users:
		u["roles"] = roles_by_user.get(u.name, [])


def log_switch(real_user: str, target_user: str) -> None:
	"""Record a completed switch in a read-only User Switch Log.

	Args:
		real_user: The user who actually logged in.
		target_user: The user the session now belongs to.
	"""
	doc = frappe.get_doc(
		{
			"doctype": "User Switch Log",
			"real_user": real_user,
			"target_user": target_user,
			"action": "Switch" if target_user != real_user else "Switch Back",
			"ip_address": getattr(frappe.local, "request_ip", None),
		}
	)
	doc.flags.from_switcher = True
	# ? SWITCHER IS ALREADY GATED BY _can_switch; THE TARGET USER MAY HAVE NO PERMISSION ON THIS DOCTYPE
	doc.insert(ignore_permissions=True)


def _roles_allow(doctype: str, name: str, user: str) -> bool:
	"""Whether `user` has one of the roles a Report/Page lists (no roles listed = open to all)."""
	allowed = frappe.get_all(
		"Has Role", filters={"parenttype": doctype, "parent": name}, pluck="role", ignore_permissions=True
	)
	return not allowed or bool(set(allowed) & set(frappe.get_roles(user)))


def _can_open_route(route: list | str | None, user: str) -> bool:
	"""Whether `user` may open the desk `route` (the parts of frappe.get_route()).

	Args:
		route: Route parts, e.g. `["Form", "Sales Invoice", "SINV-0001"]`, or their JSON. Empty means desk home.
		user: The user to check for.

	Returns:
		False when the user has no desk access or lacks read (create, for a new form) on the route's
		doctype, document, report or page; True for routes it can't judge, such as workspaces.
	"""
	parts = _str_list(route)
	if not parts:
		return True
	if frappe.db.get_value("User", user, "user_type") != "System User":
		return False
	view, rest = parts[0], parts[1:]
	try:
		if view in DOCTYPE_VIEWS and rest:
			doctype = rest[0]
			if view == "Form" and len(rest) > 1:
				if rest[1].startswith("new-"):
					return frappe.has_permission(doctype, "create", user=user)
				return frappe.has_permission(doctype, "read", doc=rest[1], user=user)
			return frappe.has_permission(doctype, "read", user=user)
		if view == "query-report" and rest:
			return _roles_allow("Report", rest[0], user)
		if frappe.db.exists("Page", view):
			return _roles_allow("Page", view, user)
	except Exception:
		# A missing doctype/document counts as "can't open" rather than failing the switch
		return False
	return True


@frappe.whitelist(methods=["POST"])
def switch_to_user(target_user: str, route: list | str | None = None):
	"""Start a new session as `target_user` and log it.

	Args:
		target_user: Id of an enabled User to switch into.
		route: Optional desk route the browser is on (see `_can_open_route`).

	Returns:
		`{"current_user": target_user, "can_stay": bool}`; `can_stay` tells the browser whether
		to reload the same page or start over from the desk home.

	Raises:
		frappe.PermissionError: Caller may not switch, or the target is blocked (see `_blocked_targets`).
		frappe.ValidationError: Target is Guest, missing or disabled.
	"""
	real_user = _real_user()
	if not _can_switch(real_user):
		_deny(_("Not permitted to switch users"), "switch", target_user)

	canonical_real = frappe.db.get_value("User", (real_user or "").strip(), "name") or real_user
	real_user = canonical_real

	canonical_target = frappe.db.get_value("User", str(target_user or "").strip(), "name")
	if (
		not canonical_target
		or canonical_target == "Guest"
		or not frappe.db.get_value("User", canonical_target, "enabled")
	):
		frappe.throw(_("Cannot switch to this user"))
	target_user = canonical_target

	blocked = {b.casefold() for b in _blocked_targets(real_user)}
	if target_user.casefold() != real_user.casefold() and target_user.casefold() in blocked:
		_deny(_("You are not permitted to switch into this user"), "switch", target_user)

	if target_user == frappe.session.user:
		return {"current_user": target_user, "can_stay": True}

	can_stay = _can_open_route(route, target_user)

	# ? LOG FIRST SO A FAILED AUDIT WRITE BLOCKS THE SWITCH INSTEAD OF LEAVING IT UNRECORDED
	log_switch(real_user, target_user)

	old_sid = frappe.session.sid
	session_obj = getattr(frappe.local, "session_obj", None)
	session_data = getattr(getattr(session_obj, "data", None), "data", None)
	session_end = getattr(session_data, "session_end", None) if session_data else None
	audit_user = getattr(session_data, "audit_user", None) if session_data else None
	login_manager = frappe.local.login_manager

	# login_as() creates a brand new session and sets the sid cookie, so the switch
	# survives the reload (frappe.set_user() only affects the current request).
	login_manager.login_as(target_user, session_end=session_end, audit_user=audit_user)

	if target_user != real_user and hasattr(frappe.local.session_obj, "set_impersonated"):
		# Keeps the "impersonating" banner in desk, tags Version logs, and lets us switch back.
		frappe.local.session_obj.set_impersonated(real_user)

	delete_session(old_sid, reason="Switched user via User Switcher")

	return {"current_user": target_user, "can_stay": can_stay}


@frappe.whitelist(methods=["POST"])
def switch_back(route: list | str | None = None):
	"""Return to the user who originally logged in (see `switch_to_user` for `route`)."""
	return switch_to_user(_real_user(), route)


@frappe.whitelist()
def get_assignable_roles():
	"""Roles offered when creating a test user. `desk_access` decides System vs Website user."""
	if not _can_switch():
		_deny(_("Not permitted"), "list_roles")
	return frappe.get_all(
		"Role",
		filters={"disabled": 0, "name": ["not in", AUTOMATIC_ROLES]},
		fields=["name", "desk_access"],
		order_by="name asc",
		ignore_permissions=True,
	)


@frappe.whitelist()
def get_role_profiles() -> list[dict]:
	"""Role Profiles with their assignable roles, for one-click role sets on the test-user form.

	Returns:
		`[{"name": profile, "roles": [role, ...]}, ...]`, profiles without any assignable role left out.
	"""
	if not _can_switch():
		_deny(_("Not permitted"), "list_role_profiles")
	active_roles = set(
		frappe.get_all("Role", filters={"disabled": 0}, pluck="name", ignore_permissions=True)
	) - set(AUTOMATIC_ROLES)
	rows = frappe.get_all(
		"Has Role",
		filters={"parenttype": "Role Profile", "role": ["in", list(active_roles) or [""]]},
		fields=["parent", "role"],
		order_by="parent asc, idx asc",
		ignore_permissions=True,
	)
	profiles = {}
	for row in rows:
		profiles.setdefault(row.parent, []).append(row.role)
	return [{"name": name, "roles": roles} for name, roles in profiles.items()]


@frappe.whitelist(methods=["POST"])
def create_test_user(
	full_name: str, email: str, roles: list | str | None = None, switch: int | str | bool = 1
):
	"""Create an enabled test user with the given roles, optionally switching into it.

	Args:
		full_name: Display name; split on the first space into first/last name.
		email: Unique email, used as the User id.
		roles: List (or JSON string) of role names; automatic and disabled roles are dropped.
		switch: Truthy to switch into the new user right after creation.

	Returns:
		Dict with the new user's `name`, `full_name`, `user_type` and `roles`.

	Raises:
		frappe.PermissionError: Caller may not switch users.
		frappe.DuplicateEntryError: A user with this email already exists.
	"""
	real_user = _real_user()
	if not _can_switch(real_user):
		_deny(_("Not permitted to create test users"), "create_test_user", email)

	canonical_real = frappe.db.get_value("User", (real_user or "").strip(), "name") or real_user
	real_user = canonical_real

	full_name = str(full_name or "").strip()
	email = str(email or "").strip().lower()
	if not full_name:
		frappe.throw(_("Name is required"))
	if not email:
		frappe.throw(_("Email is required"))
	validate_email_address(email, throw=True)
	if frappe.db.exists("User", email):
		frappe.throw(_("User {0} already exists").format(email), frappe.DuplicateEntryError)

	cleaned_roles = _str_list(roles)
	valid_roles = set(
		frappe.get_all("Role", filters={"name": ["in", cleaned_roles or [""]], "disabled": 0}, pluck="name")
	) - set(AUTOMATIC_ROLES)

	first_name, _sep, last_name = full_name.partition(" ")
	user = frappe.new_doc("User")
	user.update(
		{
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": 1,
			"send_welcome_email": 0,
			"bio": _("Test user created with User Switcher by {0}").format(real_user),
		}
	)
	for role in sorted(valid_roles):
		user.append("roles", {"role": role})
	user.flags.no_welcome_mail = True
	# The switcher is already restricted to System Managers, who can create users anyway
	user.insert(ignore_permissions=True)
	# ? WHILE SWITCHED, THE INSERT OWNER IS THE IMPERSONATED USER; _blocked_targets NEEDS THE REAL ONE
	frappe.db.set_value("User", user.name, "owner", real_user, update_modified=False)

	if cint(switch):
		switch_to_user(user.name)

	return {
		"name": user.name,
		"full_name": user.full_name,
		"user_type": user.user_type,
		"roles": sorted(valid_roles),
	}


def _check_role_target(user: str) -> str:
	"""Raise unless the caller may edit `user`'s roles; returns the real (logged-in) user."""
	real_user = _real_user()
	if not _can_switch(real_user):
		_deny(_("Not permitted to manage roles"), "manage_roles", user)
	canonical_real = frappe.db.get_value("User", (real_user or "").strip(), "name") or real_user
	real_user = canonical_real

	canonical_user = frappe.db.get_value("User", str(user or "").strip(), "name")
	if not canonical_user or canonical_user in ("Administrator", "Guest"):
		frappe.throw(_("Cannot manage roles of this user"))
	user = canonical_user

	blocked = {b.casefold() for b in _blocked_targets(real_user)}
	session_user = (frappe.session.user or "").casefold()
	if user.casefold() not in (real_user.casefold(), session_user) and user.casefold() in blocked:
		_deny(_("You are not permitted to manage roles of this user"), "manage_roles", user)
	return real_user


@frappe.whitelist()
def get_user_roles(user: str) -> list[str]:
	"""Roles currently assigned to `user`, minus the automatic ones."""
	_check_role_target(user)
	canonical_user = frappe.db.get_value("User", str(user or "").strip(), "name") or user
	return frappe.get_all(
		"Has Role",
		filters={"parenttype": "User", "parent": canonical_user, "role": ["not in", AUTOMATIC_ROLES]},
		pluck="role",
		order_by="role asc",
		ignore_permissions=True,
	)


@frappe.whitelist(methods=["POST"])
def set_user_roles(user: str, roles: list | str | None = None):
	"""Make `user`'s assignable roles exactly `roles`; roles outside that set are left alone.

	Args:
		user: Id of the User to change (the signed-in user, or any user the caller may switch into).
		roles: List (or JSON string) of role names that user should end up with.

	Returns:
		Dict with the user's `name`, `user_type` and final `roles`.

	Raises:
		frappe.PermissionError: Caller may not switch users, or the target is blocked.
		frappe.ValidationError: Target is Administrator/Guest/missing, or the caller would drop their own System Manager.
	"""
	real_user = _check_role_target(user)
	canonical_user = frappe.db.get_value("User", str(user or "").strip(), "name") or user

	assignable = set(frappe.get_all("Role", filters={"disabled": 0}, pluck="name")) - set(AUTOMATIC_ROLES)
	wanted = set(_str_list(roles)) & assignable

	doc = frappe.get_doc("User", canonical_user)
	current = {d.role for d in doc.roles} & assignable
	if canonical_user.casefold() == real_user.casefold() and "System Manager" in current - wanted:
		frappe.throw(_("You cannot remove System Manager from your own account here"))

	original = _role_snapshot(doc.name)
	if original is None and wanted != current:
		frappe.db.set_default(doc.name, frappe.as_json(sorted(current)), parent=ROLE_SNAPSHOTS)

	doc.append_roles(*sorted(wanted - current))
	doc.set("roles", [d for d in doc.roles if d.role not in current - wanted])
	# ? THE SWITCHER IS ALREADY GATED BY _can_switch; WHILE SWITCHED THE SESSION USER MAY NOT BE ABLE TO WRITE USERS
	doc.flags.ignore_permissions = True
	doc.save()

	# Back to where it started: nothing left to undo
	if original is not None and set(original) & assignable == wanted:
		frappe.defaults.clear_default(key=doc.name, parent=ROLE_SNAPSHOTS)

	return {"name": doc.name, "user_type": doc.user_type, "roles": sorted(wanted)}


def _role_snapshot(user: str) -> list[str] | None:
	"""The roles `user` had before the switcher first changed them, or None if it never did."""
	value = frappe.db.get_default(user, parent=ROLE_SNAPSHOTS)
	return frappe.parse_json(value) if value else None


@frappe.whitelist()
def get_role_snapshot(user: str) -> list[str] | None:
	"""Roles `user` had before the switcher first changed them, or None if unchanged.

	Raises:
		frappe.PermissionError: Caller may not manage this user's roles.
	"""
	_check_role_target(user)
	return _role_snapshot(frappe.db.get_value("User", str(user).strip(), "name"))


@frappe.whitelist(methods=["POST"])
def restore_user_roles(user: str):
	"""Put `user`'s roles back to what they were before the switcher first changed them.

	Returns:
		The result of `set_user_roles`.

	Raises:
		frappe.PermissionError: Caller may not manage this user's roles.
		frappe.ValidationError: No saved original roles for this user.
	"""
	_check_role_target(user)
	original = _role_snapshot(frappe.db.get_value("User", str(user).strip(), "name"))
	if original is None:
		frappe.throw(_("No original roles saved for {0}").format(user))
	return set_user_roles(user, original)


# ---------- doctype access (role permissions) ----------

# Level-0 rights offered in the switcher, in display order. Field-level (permlevel > 0) and
# "only if creator" rules stay in Role Permission Manager.
ACCESS_RIGHTS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"print",
	"email",
	"report",
	"import",
	"export",
	"share",
)
# Frappe refuses a rule with none of these set ("No basic permissions set")
BASIC_RIGHTS = ("select", "read", "write", "create", "submit", "cancel")
# Same list Role Permission Manager hides
BLOCKED_DOCTYPES = ("DocType", "Patch Log", "Module Def")


def _check_access_doctype(doctype: str):
	"""Raise unless the caller may change `doctype`'s role permissions; returns its meta."""
	if not _can_switch():
		_deny(_("Not permitted to manage doctype access"), "manage_access", doctype)
	doctype = str(doctype or "").strip()
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found").format(doctype or ""))
	meta = frappe.get_meta(doctype)
	if meta.istable or doctype in BLOCKED_DOCTYPES:
		frappe.throw(_("Permissions of {0} can't be changed here").format(doctype))
	return meta


def _access_rights(meta) -> list[str]:
	"""Rights that make sense for this doctype; Frappe rejects the others on save."""
	skip = set()
	if not meta.is_submittable:
		skip |= {"submit", "cancel", "amend"}
	if not meta.allow_import:
		skip.add("import")
	if meta.issingle:
		skip |= {"create", "delete", "report", "import", "export"}
	return [r for r in ACCESS_RIGHTS if r not in skip]


def _level_zero_rules(doctype: str) -> list[dict]:
	"""The doctype's effective level-0 rules: Custom DocPerm once customised, else the standard DocPerm."""
	fields = ["role", "if_owner", *ACCESS_RIGHTS]
	filters = {"parent": doctype, "permlevel": 0}
	return frappe.get_all(
		"Custom DocPerm", filters=filters, fields=fields, ignore_permissions=True
	) or frappe.get_all("DocPerm", filters=filters, fields=fields, ignore_permissions=True)


@frappe.whitelist()
def search_doctypes(txt: str | None = None) -> list[dict]:
	"""DocTypes whose access can be managed, matching `txt` the way Frappe's search bar does.

	Returns:
		Up to 12 `{"name", "module"}` dicts, best match first (see `_match_rank`), then shortest name.
	"""
	if not _can_switch():
		_deny(_("Not permitted"), "search_doctypes")
	rows = frappe.get_all(
		"DocType",
		filters=[["istable", "=", 0], ["name", "not in", BLOCKED_DOCTYPES]],
		fields=["name", "module"],
		order_by="name asc",
		ignore_permissions=True,
	)
	# "inv sal" or "si" can't be expressed as one LIKE, so rank every doctype here (a site has ~1-2k)
	ranked = [(_match_rank(row.name, txt), row) for row in rows]
	ranked = [(rank, row) for rank, row in ranked if rank]
	ranked.sort(key=lambda x: (x[0], len(x[1].name), x[1].name))
	return [row for _rank, row in ranked[:12]]


@frappe.whitelist()
def get_doctype_access(doctype: str) -> dict:
	"""Who can do what on `doctype`, and which of those roles the signed-in user has.

	Returns:
		Dict with `doctype`, `rights` (applicable rights in display order), `roles` (one row per
		role with a level-0 rule: `role`, `perms`, `user_has`, `locked`), `user`, `user_roles`,
		`only_if_creator` (roles whose rule applies only to their own documents), `customized`
		and `assignable_roles` (roles that can be given access).
	"""
	doctype = str(doctype or "").strip()
	meta = _check_access_doctype(doctype)
	rights = _access_rights(meta)
	user = frappe.session.user
	user_roles = set(frappe.get_roles(user))

	rows = {}
	only_if_creator = set()
	for rule in _level_zero_rules(doctype):
		if rule.if_owner:
			only_if_creator.add(rule.role)
			continue
		if rule.role not in rows:
			rows[rule.role] = {r: cint(rule.get(r)) for r in rights}
		else:
			for r in rights:
				rows[rule.role][r] = max(rows[rule.role][r], cint(rule.get(r)))

	roles = [
		{
			"role": role,
			"perms": perms,
			"user_has": role in user_roles,
			# Rules for automatic roles reach every user (or every website visitor), so leave them to Role Permission Manager
			"locked": role in AUTOMATIC_ROLES,
		}
		for role, perms in rows.items()
	]
	roles.sort(key=lambda r: (not r["user_has"], r["locked"], r["role"].casefold()))

	return {
		"doctype": doctype,
		"rights": rights,
		"roles": roles,
		"user": user,
		"user_roles": sorted(user_roles - set(AUTOMATIC_ROLES)),
		"only_if_creator": sorted(only_if_creator),
		"customized": bool(frappe.db.exists("Custom DocPerm", {"parent": doctype})),
		"assignable_roles": frappe.get_all(
			"Role",
			filters={"disabled": 0, "name": ["not in", AUTOMATIC_ROLES]},
			pluck="name",
			order_by="name asc",
			ignore_permissions=True,
		),
	}


@frappe.whitelist(methods=["POST"])
def set_doctype_access(doctype: str, changes: dict | str | None = None):
	"""Apply level-0 permission changes to `doctype`, the way Role Permission Manager saves them.

	Args:
		doctype: The DocType to change.
		changes: `{role: {right: 0 | 1}}` (or its JSON). Only the rights listed are touched. A role
			left with no basic right (read, write, create, ...) loses its rule.

	Returns:
		The updated access, as `get_doctype_access` returns it.

	Raises:
		frappe.PermissionError: Caller may not switch users.
		frappe.ValidationError: Unknown or automatic role, or a combination Frappe rejects (e.g. Cancel without Submit).
	"""
	from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
	from frappe.permissions import setup_custom_perms

	doctype = str(doctype or "").strip()
	meta = _check_access_doctype(doctype)
	rights = set(_access_rights(meta))
	if not changes:
		changes = {}
	if isinstance(changes, str):
		try:
			changes = frappe.parse_json(changes)
		except Exception:
			frappe.throw(_("Invalid changes payload"))
	if not isinstance(changes, dict):
		frappe.throw(_("Invalid changes payload"))

	assignable = set(
		frappe.get_all("Role", filters={"disabled": 0}, pluck="name", ignore_permissions=True)
	) - set(AUTOMATIC_ROLES)

	sanitized_changes = {}
	for role, values in changes.items():
		if role not in assignable:
			frappe.throw(_("Role {0} can't be given access here").format(role))
		if not isinstance(values, dict):
			continue
		vals = {r: cint(v) for r, v in values.items() if r in rights}
		if vals:
			sanitized_changes[role] = vals

	if not sanitized_changes:
		return get_doctype_access(doctype)

	setup_custom_perms(doctype)
	for role, values in sanitized_changes.items():
		name = frappe.db.get_value(
			"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
		)
		if name:
			rule = frappe.get_doc("Custom DocPerm", name)
		else:
			rule = frappe.new_doc("Custom DocPerm")
			rule.update(
				{
					"parent": doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
				}
			)
			# The doctype defaults turn on read and export; start from nothing instead
			rule.update({r: 0 for r in ACCESS_RIGHTS})
		rule.update(values)

		if not any(rule.get(r) for r in BASIC_RIGHTS):
			if not rule.is_new():
				frappe.delete_doc("Custom DocPerm", rule.name, ignore_permissions=True, force=True)
			continue

		if rule.cancel and not rule.submit:
			frappe.throw(_("Cannot set Cancel without Submit for role {0}").format(role))
		if (rule.submit or rule.cancel or rule.amend) and not rule.write:
			frappe.throw(_("Cannot set Submit, Cancel, Amend without Write for role {0}").format(role))
		if rule.amend and not rule.cancel:
			frappe.throw(_("Cannot set Amend without Cancel for role {0}").format(role))
		if rule.get("import") and not rule.create:
			frappe.throw(_("Cannot set Import without Create for role {0}").format(role))

		rule.save(ignore_permissions=True)

		frappe.logger("user_switcher").info(
			"doctype access: real_user=%s doctype=%s role=%s set=%s", _real_user(), doctype, role, values
		)

	if not frappe.db.exists("Custom DocPerm", {"parent": doctype}):
		# With no custom rules left Frappe would silently fall back to the standard ones
		frappe.throw(_("{0} must keep at least one permission rule").format(doctype))

	if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "permlevel": 0, "read": 1}):
		frappe.throw(_("At least one permission rule must have Read permission for {0}").format(doctype))

	validate_permissions_for_doctype(doctype)
	return get_doctype_access(doctype)


# ---------- test users and changed roles (clean up) ----------


def _test_users(real_user: str, names: list[str] | None = None) -> list[dict]:
	"""Test users the caller may clean up: made by the switcher, not blocked, not the caller."""
	filters = [
		["bio", "like", TEST_USER_MARK],
		["name", "not in", [*_blocked_targets(real_user), real_user, "Administrator", "Guest"]],
	]
	if names is not None:
		filters.append(["name", "in", names or [""]])
	return frappe.get_all(
		"User",
		filters=filters,
		fields=[
			"name",
			"full_name",
			"user_image",
			"user_type",
			"enabled",
			"owner",
			"creation",
			"last_active",
		],
		order_by="creation desc",
		limit=200,
		ignore_permissions=True,
	)


@frappe.whitelist()
def get_cleanup() -> dict:
	"""Test users made with the switcher, and users whose roles the switcher changed.

	Returns:
		`{"test_users": [...], "changed_roles": [{"name", "full_name", "original", "current"}, ...]}`.
		`test_users` rows also carry `roles`; both lists are capped at 200.

	Raises:
		frappe.PermissionError: Caller may not switch users.
	"""
	real_user = _real_user()
	if not _can_switch(real_user):
		_deny(_("Not permitted"), "cleanup")
	real_user = frappe.db.get_value("User", real_user, "name") or real_user

	test_users = _test_users(real_user)
	_attach_roles(test_users)

	snapshots = frappe.get_all(
		"DefaultValue",
		filters={"parent": ROLE_SNAPSHOTS},
		fields=["defkey", "defvalue"],
		limit=200,
		ignore_permissions=True,
	)
	users = {
		u.name: u
		for u in frappe.get_all(
			"User",
			filters={"name": ["in", [s.defkey for s in snapshots] or [""]]},
			fields=["name", "full_name", "user_image"],
			ignore_permissions=True,
		)
	}
	_attach_roles(list(users.values()))
	changed = [
		{
			"name": s.defkey,
			"full_name": users[s.defkey].full_name,
			"user_image": users[s.defkey].user_image,
			"original": frappe.parse_json(s.defvalue),
			"current": users[s.defkey].roles,
		}
		for s in snapshots
		if s.defkey in users
	]
	return {"test_users": test_users, "changed_roles": changed}


@frappe.whitelist(methods=["POST"])
def remove_test_users(users: list | str, action: str = "delete") -> dict:
	"""Delete, disable or enable test users made with the switcher.

	Args:
		users: User ids (or their JSON). Ids that are not the caller's removable test users are skipped.
		action: "enable" or "disable" only flips `enabled`; "delete" deletes, and disables users whose
			records are still linked from other documents (Frappe refuses to delete those).

	Returns:
		`{"deleted": [...], "disabled": [...], "enabled": [...], "skipped": [...]}`.

	Raises:
		frappe.PermissionError: Caller may not switch users.
	"""
	real_user = _real_user()
	if not _can_switch(real_user):
		_deny(_("Not permitted"), "remove_test_users")
	real_user = frappe.db.get_value("User", real_user, "name") or real_user

	names = _str_list(users)
	removable = {u.name for u in _test_users(real_user, names)} - {frappe.session.user}
	out = {"deleted": [], "disabled": [], "enabled": [], "skipped": [n for n in names if n not in removable]}

	def set_enabled(name, on):
		user = frappe.get_doc("User", name)
		user.enabled = int(on)
		# ? CLEAN-UP IS GATED BY _can_switch; WHILE SWITCHED THE SESSION USER MAY NOT BE ABLE TO WRITE USERS
		user.flags.ignore_permissions = True
		user.save()
		out["enabled" if on else "disabled"].append(name)

	def disable(name):
		set_enabled(name, False)

	for name in sorted(removable):
		if action != "delete":
			set_enabled(name, action == "enable")
			continue
		frappe.db.savepoint("us_remove_user")
		try:
			frappe.delete_doc("User", name, ignore_permissions=True)
			out["deleted"].append(name)
			frappe.defaults.clear_default(key=name, parent=ROLE_SNAPSHOTS)
		except frappe.LinkExistsError:
			frappe.db.rollback(save_point="us_remove_user")
			disable(name)

	frappe.logger("user_switcher").info("removed test users: real_user=%s result=%s", real_user, out)
	return out


# ---------- why can't they open it? ----------


@frappe.whitelist()
def explain_access(doctype: str, docname: str | None = None, ptype: str = "read") -> dict:
	"""Explain whether the user you are viewing as may `ptype` a doctype (or one document), and why.

	Args:
		doctype: The DocType to check.
		docname: Optional document name; adds User Permission, sharing and owner checks.
		ptype: One of `ACCESS_RIGHTS`; anything else is treated as "read".

	Returns:
		Dict with `user`, `doctype`, `docname`, `ptype`, `allowed`, `role_ok` (a role grants it),
		`owner_only` (granted only on documents they created), `user_permission_ok` (User Permissions
		let them see this document), `controller_ok` (the doctype's own `has_permission` code allows
		it), `restrictions` (`[{"allow", "values"}]` of their User Permissions) and `log` (Frappe's own
		step-by-step permission log).

	Raises:
		frappe.PermissionError: Caller may not switch users.
		frappe.DoesNotExistError: The doctype or document does not exist.
	"""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions
	from frappe.permissions import (
		_pop_debug_log,
		get_role_permissions,
		has_controller_permissions,
		has_user_permission,
	)

	if not _can_switch():
		_deny(_("Not permitted"), "explain_access", doctype)
	doctype = str(doctype or "").strip()
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found").format(doctype), frappe.DoesNotExistError)
	ptype = ptype if ptype in ACCESS_RIGHTS else "read"
	user = frappe.session.user

	doc = None
	if docname:
		if not frappe.db.exists(doctype, docname):
			frappe.throw(_("{0} {1} not found").format(_(doctype), docname), frappe.DoesNotExistError)
		doc = frappe.get_doc(doctype, docname)

	_pop_debug_log()
	allowed = frappe.has_permission(doctype, ptype, doc=doc, user=user, debug=True)
	log = _pop_debug_log()

	role_perms = get_role_permissions(frappe.get_meta(doctype), user=user)
	restrictions = [
		{"allow": allow, "values": sorted({row.get("doc") for row in rows})}
		for allow, rows in sorted(get_user_permissions(user).items())
	]
	return {
		"user": user,
		"doctype": doctype,
		"docname": docname,
		"ptype": ptype,
		"allowed": bool(allowed),
		"role_ok": bool(role_perms.get(ptype)),
		"owner_only": bool(role_perms.get("if_owner", {}).get(ptype)),
		"user_permission_ok": has_user_permission(doc, user, ptype=ptype) if doc else True,
		"controller_ok": has_controller_permissions(doc, ptype, user=user) if doc else True,
		"restrictions": restrictions,
		"log": log,
	}


# ---------- user permissions (limit a user to some records) ----------


def _check_link_doctype(doctype: str):
	"""Raise unless `doctype` can hold User Permission values; returns its meta."""
	doctype = str(doctype or "").strip()
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found").format(doctype))
	meta = frappe.get_meta(doctype)
	if meta.istable or meta.issingle:
		frappe.throw(_("{0} can't be used in a User Permission").format(doctype))
	return meta


@frappe.whitelist()
def get_user_permission_list(user: str) -> list[dict]:
	"""User Permissions of `user`, as `[{"name", "allow", "for_value", "is_default", "applicable_for", ...}]`.

	Raises:
		frappe.PermissionError: Caller may not manage this user.
	"""
	_check_role_target(user)
	return frappe.get_all(
		"User Permission",
		filters={"user": frappe.db.get_value("User", str(user).strip(), "name")},
		fields=["name", "allow", "for_value", "is_default", "apply_to_all_doctypes", "applicable_for"],
		order_by="allow asc, for_value asc",
		ignore_permissions=True,
	)


@frappe.whitelist(methods=["POST"])
def add_user_permission(user: str, allow: str, for_value: str, is_default: int | str = 0) -> list[dict]:
	"""Limit `user` to `for_value` of `allow` on every doctype (a User Permission).

	Returns:
		The user's User Permissions, as `get_user_permission_list` returns them.

	Raises:
		frappe.PermissionError: Caller may not manage this user.
		frappe.ValidationError: Unknown doctype/value, or the same permission already exists.
	"""
	_check_role_target(user)
	user = frappe.db.get_value("User", str(user).strip(), "name")
	allow = _check_link_doctype(allow).name
	for_value = str(for_value or "").strip()
	if not for_value or not frappe.db.exists(allow, for_value):
		frappe.throw(_("{0} {1} not found").format(_(allow), for_value))

	doc = frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": for_value,
			"apply_to_all_doctypes": 1,
			"is_default": cint(is_default),
		}
	)
	# ? GATED BY _can_switch; WHILE SWITCHED THE SESSION USER MAY NOT BE ABLE TO WRITE USER PERMISSIONS
	doc.insert(ignore_permissions=True)
	frappe.logger("user_switcher").info(
		"user permission added: real_user=%s user=%s %s=%s", _real_user(), user, allow, for_value
	)
	return get_user_permission_list(user)


@frappe.whitelist(methods=["POST"])
def remove_user_permission(name: str) -> list[dict]:
	"""Delete one User Permission.

	Returns:
		The remaining User Permissions of its user.

	Raises:
		frappe.PermissionError: Caller may not manage that user.
	"""
	user = frappe.db.get_value("User Permission", str(name or "").strip(), "user")
	if not user:
		frappe.throw(_("User Permission {0} not found").format(name))
	_check_role_target(user)
	frappe.delete_doc("User Permission", name, ignore_permissions=True)
	frappe.logger("user_switcher").info("user permission removed: real_user=%s name=%s", _real_user(), name)
	return get_user_permission_list(user)


@frappe.whitelist()
def search_link_values(doctype: str, txt: str | None = None) -> list[dict]:
	"""Records of `doctype` matching `txt`, for picking a User Permission value.

	Returns:
		Up to 12 `{"value", "label"}` dicts; `label` is the title field when the doctype has one.

	Raises:
		frappe.PermissionError: Caller may not switch users.
	"""
	if not _can_switch():
		_deny(_("Not permitted"), "search_link_values", doctype)
	meta = _check_link_doctype(doctype)
	title = meta.title_field if meta.title_field and meta.title_field != "name" else None
	fields = ["name", *([title] if title else [])]
	or_filters = None
	clean = str(txt or "").strip()
	if clean:
		like = f"%{_escape_like(clean)}%"
		or_filters = {f: ["like", like] for f in fields}
	# ? THE VIEWED USER MAY NOT READ THIS DOCTYPE; PICKING THE VALUE TO GRANT IS THE POINT
	rows = frappe.get_all(
		meta.name,
		or_filters=or_filters,
		fields=fields,
		order_by="modified desc",
		limit=12,
		ignore_permissions=True,
	)
	return [{"value": r.name, "label": r.get(title) if title else None} for r in rows]
