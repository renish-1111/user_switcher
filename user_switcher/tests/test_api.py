# * user_switcher/tests/test_api.py
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from user_switcher import api


class TestUserSwitcherAccess(IntegrationTestCase):
	def test_escape_like(self):
		self.assertEqual(api._escape_like("a%b_c"), "a\\%b\\_c")

	def test_disabled_without_developer_mode(self):
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=0)):
			self.assertFalse(api._can_switch("Administrator"))

	def test_guest_never_allowed(self):
		with patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		):
			self.assertFalse(api._can_switch("Guest"))
			self.assertTrue(api._can_switch("Administrator"))

	def test_logged_out_probe_is_quietly_refused(self):
		frappe.set_user("Guest")
		try:
			with patch.object(
				frappe.local,
				"conf",
				frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1),
			):
				self.assertEqual(api.get_context(txt="a"), {"allowed": False})
		finally:
			frappe.set_user("Administrator")

	def test_system_manager_cannot_list_administrator(self):
		with patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		):
			names = [u.name for u in api._find_users("test@example.com", None, None, 100)]
		self.assertNotIn("Administrator", names)


class TestUserSwitchLog(IntegrationTestCase):
	def test_manual_create_blocked(self):
		doc = frappe.get_doc(
			{"doctype": "User Switch Log", "real_user": "Administrator", "target_user": "Guest"}
		)
		self.assertRaises(frappe.PermissionError, doc.insert)

	def test_log_switch_creates_readonly_record(self):
		api.log_switch("Administrator", "Guest")
		name = frappe.db.get_value("User Switch Log", {"target_user": "Guest"}, "name")
		doc = frappe.get_doc("User Switch Log", name)
		doc.action = "Switch Back"
		self.assertRaises(frappe.PermissionError, doc.save)

	def test_delete_blocked(self):
		api.log_switch("Administrator", "Guest")
		name = frappe.db.get_value("User Switch Log", {"target_user": "Guest"}, "name")
		self.assertRaises(frappe.PermissionError, frappe.delete_doc, "User Switch Log", name)


class TestBlockedTargets(IntegrationTestCase):
	def test_administrator_has_no_blocked_targets(self):
		self.assertEqual(api._blocked_targets("Administrator"), [])

	def test_system_manager_blocked_from_administrator_and_other_managers(self):
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "User",
				"email": "us_sm_a@example.com",
				"first_name": "A",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}],
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "User",
				"email": "us_sm_b@example.com",
				"first_name": "B",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}],
			}
		).insert()
		blocked = api._blocked_targets("us_sm_a@example.com")
		self.assertIn("Administrator", blocked)
		self.assertIn("us_sm_b@example.com", blocked)

		frappe.db.set_value("User", "us_sm_b@example.com", "owner", "us_sm_a@example.com")
		self.assertNotIn("us_sm_b@example.com", api._blocked_targets("us_sm_a@example.com"))

		frappe.utils.password.update_password("us_sm_b@example.com", "Str0ng!Pass#2026")
		self.assertIn("us_sm_b@example.com", api._blocked_targets("us_sm_a@example.com"))


class TestManageRoles(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		)
		self.conf.start()
		self.addCleanup(self.conf.stop)

	def _user(self, email, roles=()):
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "R",
					"send_welcome_email": 0,
					"roles": [{"role": r} for r in roles],
				}
			)
			.insert()
			.name
		)

	def test_find_users_by_role(self):
		one = self._user("us_role_filter@example.com", ["Newsletter Manager"])
		both = self._user("us_role_filter2@example.com", ["Newsletter Manager", "Website Manager"])

		def find(roles, match_all=False):
			return {u.name for u in api._find_users("Administrator", None, None, 100, roles, match_all)}

		self.assertTrue({one, both} <= find(["Newsletter Manager"]))
		self.assertNotIn(one, find(["Website Manager"]))
		self.assertTrue({one, both} <= find(["Newsletter Manager", "Website Manager"]))
		self.assertIn(both, find(["Newsletter Manager", "Website Manager"], match_all=True))
		self.assertNotIn(one, find(["Newsletter Manager", "Website Manager"], match_all=True))

	def test_role_snapshot_and_restore(self):
		user = self._user("us_roles_snap@example.com", ["Website Manager"])
		self.assertIsNone(api.get_role_snapshot(user))

		api.set_user_roles(user, ["Newsletter Manager"])
		api.set_user_roles(user, ["Newsletter Manager", "Website Manager"])
		# The first original is kept, not overwritten by later edits
		self.assertEqual(api.get_role_snapshot(user), ["Website Manager"])

		api.restore_user_roles(user)
		self.assertEqual(api.get_user_roles(user), ["Website Manager"])
		self.assertIsNone(api.get_role_snapshot(user))
		self.assertRaises(frappe.ValidationError, api.restore_user_roles, user)

	def test_user_permissions(self):
		user = self._user("us_uperm@example.com", ["Website Manager"])
		rows = api.add_user_permission(user, "Role", "Website Manager")
		self.assertEqual([(r.allow, r.for_value) for r in rows], [("Role", "Website Manager")])
		self.assertRaises(frappe.ValidationError, api.add_user_permission, user, "Role", "No Such Role")
		self.assertEqual(api.remove_user_permission(rows[0].name), [])

	def test_user_permission_doctype_suggestions(self):
		user = self._user("us_uperm_suggest@example.com", ["Website Manager"])
		api.add_user_permission(user, "Role", "Website Manager")
		suggested = [d.name for d in api.search_doctypes(for_user_permission=1)]
		# Doctypes already used in User Permissions come first, then the usual ones
		self.assertIn("Role", suggested)
		self.assertIn("Company", suggested)
		found = [d.name for d in api.search_doctypes("system settings", for_user_permission=1)]
		self.assertNotIn("System Settings", found)

	def test_search_link_values(self):
		values = [r["value"] for r in api.search_link_values("Role", "newsl")]
		self.assertIn("Newsletter Manager", values)
		self.assertRaises(frappe.ValidationError, api.search_link_values, "Has Role")

	def test_add_and_remove_roles(self):
		user = self._user("us_roles_t@example.com", ["Website Manager"])
		self.assertEqual(api.get_user_roles(user), ["Website Manager"])

		api.set_user_roles(user, ["Newsletter Manager"])
		self.assertEqual(api.get_user_roles(user), ["Newsletter Manager"])

		api.set_user_roles(user, '["Website Manager", "Newsletter Manager", "All"]')
		self.assertEqual(api.get_user_roles(user), ["Newsletter Manager", "Website Manager"])

	def test_administrator_and_guest_not_editable(self):
		for user in ("Administrator", "Guest"):
			self.assertRaises(frappe.ValidationError, api.set_user_roles, user, ["Website Manager"])

	def test_cannot_drop_own_system_manager(self):
		user = self._user("us_roles_sm@example.com", ["System Manager", "Website Manager"])
		with patch.object(api, "_real_user", return_value=user):
			self.assertRaises(frappe.ValidationError, api.set_user_roles, user, ["Website Manager"])
			api.set_user_roles(user, ["System Manager"])
		self.assertEqual(api.get_user_roles(user), ["System Manager"])


class TestTesterTools(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		)
		self.conf.start()
		self.addCleanup(self.conf.stop)

	def _test_user(self, email, roles=()):
		with patch.object(api, "switch_to_user"):
			return api.create_test_user("Tool Tester", email, list(roles), switch=0)["name"]

	def test_route_check(self):
		desk = self._test_user("us_route_desk@example.com", ["Website Manager"])
		portal = self._test_user("us_route_web@example.com")
		self.assertTrue(api._can_open_route(None, portal))
		self.assertFalse(api._can_open_route(["List", "ToDo"], portal))
		self.assertTrue(api._can_open_route('["List", "ToDo", "List"]', desk))
		self.assertFalse(api._can_open_route(["List", "Role"], desk))
		self.assertFalse(api._can_open_route(["Form", "ToDo", "no-such-todo"], desk))
		self.assertTrue(api._can_open_route(["Workspaces", "Home"], desk))

	def test_cleanup_lists_and_removes_test_users(self):
		keep = self._test_user("us_clean_keep@example.com", ["Website Manager"])
		gone = self._test_user("us_clean_gone@example.com", ["Website Manager"])
		names = {u.name for u in api.get_cleanup()["test_users"]}
		self.assertTrue({keep, gone} <= names)

		out = api.remove_test_users([gone, "Administrator"], "delete")
		self.assertEqual(out["deleted"], [gone])
		self.assertEqual(out["skipped"], ["Administrator"])
		self.assertFalse(frappe.db.exists("User", gone))

		out = api.remove_test_users([keep], "disable")
		self.assertEqual(out["disabled"], [keep])
		self.assertEqual(frappe.db.get_value("User", keep, "enabled"), 0)

		out = api.remove_test_users([keep], "enable")
		self.assertEqual(out["enabled"], [keep])
		self.assertEqual(frappe.db.get_value("User", keep, "enabled"), 1)

	def test_cleanup_lists_changed_roles(self):
		user = self._test_user("us_clean_roles@example.com", ["Website Manager"])
		api.set_user_roles(user, ["Newsletter Manager"])
		row = next(r for r in api.get_cleanup()["changed_roles"] if r["name"] == user)
		self.assertEqual((row["original"], row["current"]), (["Website Manager"], ["Newsletter Manager"]))

	def test_explain_access(self):
		user = self._test_user("us_explain@example.com", ["Website Manager"])
		todo = frappe.get_doc({"doctype": "ToDo", "description": "us explain"}).insert().name
		frappe.set_user(user)
		try:
			with patch.object(api, "_real_user", return_value="Administrator"):
				out = api.explain_access("Role")
				self.assertFalse(out["allowed"])
				self.assertFalse(out["role_ok"])
				self.assertTrue(out["log"])
				self.assertTrue(api.explain_access("ToDo")["allowed"])
				# A role allows ToDo, but ToDo's own has_permission only lets owners and assignees in
				out = api.explain_access("ToDo", todo)
				self.assertEqual((out["allowed"], out["role_ok"], out["controller_ok"]), (False, True, False))
		finally:
			frappe.set_user("Administrator")


class TestSwitchHardening(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		)
		self.conf.start()
		self.addCleanup(self.conf.stop)

	def test_negative_limit_is_clamped(self):
		self.assertEqual(api.get_context(limit=-5), {"allowed": True})

	def test_failed_audit_write_blocks_the_switch(self):
		target = (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": "us_audit_t@example.com",
					"first_name": "T",
					"send_welcome_email": 0,
				}
			)
			.insert()
			.name
		)
		login_manager = MagicMock()
		with (
			patch.object(frappe.local, "login_manager", login_manager, create=True),
			patch.object(frappe.local, "session_obj", MagicMock(), create=True),
			patch.object(api, "log_switch", side_effect=frappe.ValidationError("audit down")),
		):
			self.assertRaises(frappe.ValidationError, api.switch_to_user, target)
		login_manager.login_as.assert_not_called()

	def test_switch_keeps_the_old_session_for_now(self):
		target = (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": "us_grace_t@example.com",
					"first_name": "T",
					"send_welcome_email": 0,
				}
			)
			.insert()
			.name
		)
		old_session, new_session = MagicMock(), MagicMock()
		old_session.data.data = frappe._dict(
			{api.RETIRED_SESSIONS: {"sids": ["older"], "at": frappe.utils.now()}}
		)
		new_session.data.data = frappe._dict()
		new_session.sid = "new-sid"
		login_manager = MagicMock()
		login_manager.login_as.side_effect = lambda *a, **k: setattr(frappe.local, "session_obj", new_session)
		with (
			patch.object(frappe.local, "login_manager", login_manager, create=True),
			patch.object(frappe.local, "session_obj", old_session, create=True),
			patch.dict(frappe.session, {"sid": "old-sid"}),
			patch.object(api, "delete_session") as delete,
		):
			api.switch_to_user(target)
		delete.assert_not_called()
		self.assertEqual(new_session.data.data[api.RETIRED_SESSIONS]["sids"], ["older", "old-sid"])
		self.assertEqual(new_session.data.data.impersonated_by, "Administrator")
		new_session.update.assert_called_once_with(force=True)
		# The old session points at its replacement, so a late reply on it can't undo the switch
		self.assertEqual(old_session.data.data[api.REPLACED_BY], "new-sid")
		old_session.update.assert_called_once_with(force=True)


class TestAccessGates(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def _manager(self, email):
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "M",
					"send_welcome_email": 0,
					"roles": [{"role": "System Manager"}],
				}
			)
			.insert()
			.name
		)

	def _impersonated_by(self, user):
		"""Mark the current test session as impersonated by `user`, undone after the test."""
		previous = frappe.session.get("data")
		frappe.session["data"] = frappe._dict(impersonated_by=user)
		self.addCleanup(frappe.session.__setitem__, "data", previous)

	def test_developer_mode_alone_is_not_enough(self):
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=1)):
			self.assertFalse(api._can_switch("Administrator"))
		with patch.object(frappe.local, "conf", frappe._dict(user_switcher_enabled=1)):
			self.assertFalse(api._can_switch("Administrator"))

	def test_disabled_system_manager_cannot_switch(self):
		user = self._manager("us_gate_sm@example.com")
		with patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		):
			self.assertTrue(api._can_switch(user))
			frappe.db.set_value("User", user, "enabled", 0)
			frappe.clear_cache(user=user)
			self.assertFalse(api._can_switch(user))

	def test_orphaned_impersonated_session_is_ended(self):
		user = self._manager("us_orphan_sm@example.com")
		frappe.db.set_value("User", user, "enabled", 0)
		frappe.clear_cache(user=user)
		self._impersonated_by(user)
		with (
			patch.object(
				frappe.local,
				"conf",
				frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1),
			),
			patch.object(api, "delete_session") as delete,
			# the hook commits so the delete survives the error rollback; never let a test do that for real
			patch.object(frappe.db, "commit") as commit,
		):
			self.assertRaises(frappe.SessionExpired, api.end_orphaned_session)
		delete.assert_called_once()
		commit.assert_called_once()

	def test_valid_impersonated_session_is_kept(self):
		self._impersonated_by("Administrator")
		with (
			patch.object(
				frappe.local,
				"conf",
				frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1),
			),
			patch.object(api, "delete_session") as delete,
		):
			api.end_orphaned_session()
		delete.assert_not_called()

	def test_normal_session_is_untouched(self):
		with patch.object(api, "delete_session") as delete:
			api.end_orphaned_session()
			api.retire_previous_sessions()
		delete.assert_not_called()

	def _replaced(self, seconds_ago):
		"""Mark the current test session as having replaced two sessions `seconds_ago`."""
		previous = frappe.session.get("data")
		at = frappe.utils.add_to_date(frappe.utils.now(), seconds=-seconds_ago, as_string=True)
		frappe.session["data"] = frappe._dict({api.RETIRED_SESSIONS: {"sids": ["old-a", "old-b"], "at": at}})
		self.addCleanup(frappe.session.__setitem__, "data", previous)

	def test_late_request_on_replaced_session_gets_the_new_sid(self):
		previous = frappe.session.get("data")
		frappe.session["data"] = frappe._dict({api.REPLACED_BY: "new-sid"})
		self.addCleanup(frappe.session.__setitem__, "data", previous)
		cookies = MagicMock()
		with (
			patch.object(frappe.local, "cookie_manager", cookies, create=True),
			patch.object(api, "delete_session") as delete,
		):
			api.retire_previous_sessions()
		self.assertEqual(cookies.set_cookie.call_args.args, ("sid", "new-sid"))
		delete.assert_not_called()

	def test_replaced_sessions_survive_the_grace_period(self):
		# A request still in flight with the old sid must not get "session expired" (it would clear the cookie)
		self._replaced(2)
		with patch.object(api, "delete_session") as delete:
			api.retire_previous_sessions()
		delete.assert_not_called()

	def test_replaced_sessions_are_deleted_after_the_grace_period(self):
		self._replaced(30)
		with (
			patch.object(api, "delete_session") as delete,
			patch.object(frappe.local, "session_obj", MagicMock(), create=True),
			patch.object(frappe.db, "commit"),
		):
			api.retire_previous_sessions()
		self.assertEqual([c.args[0] for c in delete.call_args_list], ["old-a", "old-b"])
		self.assertNotIn(api.RETIRED_SESSIONS, frappe.session.data)

	def test_denied_request_is_logged(self):
		logger = MagicMock()
		with (
			patch.object(frappe.local, "conf", frappe._dict(developer_mode=0)),
			patch.object(frappe, "logger", return_value=logger),
		):
			self.assertRaises(frappe.PermissionError, api.switch_to_user, "someone@example.com")
		logger.warning.assert_called_once()
		self.assertEqual(logger.warning.call_args.args[1], "switch")


class TestDoctypeAccess(IntegrationTestCase):
	DOCTYPE = "ToDo"

	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.object(
			frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1)
		)
		self.conf.start()
		self.had_custom = bool(frappe.db.exists("Custom DocPerm", {"parent": self.DOCTYPE}))
		if not frappe.db.exists("Role", "US Access Tester"):
			frappe.get_doc({"doctype": "Role", "role_name": "US Access Tester", "desk_access": 1}).insert()

	def tearDown(self):
		self.conf.stop()
		if not self.had_custom:
			frappe.permissions.reset_perms(self.DOCTYPE)

	def rule(self, role):
		return frappe.db.get_value(
			"Custom DocPerm",
			{"parent": self.DOCTYPE, "role": role, "permlevel": 0, "if_owner": 0},
			["read", "write", "create"],
			as_dict=True,
		)

	def test_blocked_without_switcher(self):
		self.conf.stop()
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=0)):
			self.assertRaises(frappe.PermissionError, api.get_doctype_access, self.DOCTYPE)
		self.conf.start()

	def test_child_and_core_doctypes_refused(self):
		self.assertRaises(frappe.ValidationError, api.get_doctype_access, "Has Role")
		self.assertRaises(frappe.ValidationError, api.get_doctype_access, "DocType")

	def test_rights_follow_doctype(self):
		rights = api.get_doctype_access("ToDo")["rights"]
		self.assertIn("create", rights)
		self.assertNotIn("submit", rights)

	def test_grant_new_role_starts_from_nothing(self):
		api.set_doctype_access(self.DOCTYPE, {"US Access Tester": {"read": 1, "create": 1}})
		self.assertEqual(self.rule("US Access Tester"), {"read": 1, "write": 0, "create": 1})

	def test_removing_basic_rights_drops_rule(self):
		api.set_doctype_access(self.DOCTYPE, {"US Access Tester": {"read": 1}})
		api.set_doctype_access(self.DOCTYPE, {"US Access Tester": {"read": 0}})
		self.assertIsNone(self.rule("US Access Tester"))

	def test_automatic_roles_refused(self):
		self.assertRaises(frappe.ValidationError, api.set_doctype_access, self.DOCTYPE, {"All": {"read": 1}})

	def test_match_rank_like_frappe_search(self):
		self.assertTrue(api._match_rank("Sales Invoice", "inv sal"))
		self.assertTrue(api._match_rank("Sales Invoice", "si"))
		self.assertFalse(api._match_rank("Sales Invoice", "purchase"))
		self.assertLess(api._match_rank("Sales Invoice", "sales"), api._match_rank("Sales Invoice", "voice"))

	def test_search_puts_prefix_matches_first(self):
		names = [d["name"] for d in api.search_doctypes("rol")]
		self.assertEqual(names[0], "Role")
		self.assertNotIn("DocType", [d["name"] for d in api.search_doctypes("doctype")])

	def test_linked_doctypes_suggested_for_the_page(self):
		rows = api.search_doctypes(related_to="Purchase Order")
		names = [d["name"] for d in rows]
		self.assertEqual(names[0], "Purchase Order")
		# Own Link fields, then the child tables' (Item comes from the items table)
		self.assertTrue({"Supplier", "Company", "Item"} <= set(names))
		groups = {d["name"]: d["group"] for d in rows}
		self.assertEqual((groups["Purchase Order"], groups["Supplier"]), ("", "Purchase Order"))
		self.assertEqual(groups["Item"], "Items (child table)")
		# Mandatory links name the field: Item Code, not an optional Item link earlier in the table
		self.assertEqual(next(d["hint"] for d in rows if d["name"] == "Item"), "Item Code")
		self.assertFalse({"DocType", "Purchase Order Item"} & set(names))
		# Typing still searches every doctype
		self.assertEqual(api.search_doctypes("rol", related_to="Purchase Order")[0]["name"], "Role")

	def test_role_profiles_list_their_roles(self):
		if not frappe.db.exists("Role Profile", "US Access Profile"):
			frappe.get_doc(
				{
					"doctype": "Role Profile",
					"role_profile": "US Access Profile",
					"roles": [{"role": "US Access Tester"}, {"role": "All"}],
				}
			).insert()
		profile = next(p for p in api.get_role_profiles() if p["name"] == "US Access Profile")
		self.assertEqual(profile["roles"], ["US Access Tester"])

	def test_returns_user_roles(self):
		out = api.get_doctype_access(self.DOCTYPE)
		self.assertIn("System Manager", out["user_roles"])
		self.assertNotIn("All", out["user_roles"])
