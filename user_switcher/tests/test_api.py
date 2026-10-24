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
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)):
			self.assertFalse(api._can_switch("Guest"))
			self.assertTrue(api._can_switch("Administrator"))

	def test_system_manager_cannot_list_administrator(self):
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)):
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
			frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)
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


class TestSwitchHardening(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.conf = patch.object(
			frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)
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
		with patch.object(frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)):
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
			patch.object(frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)),
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
			patch.object(frappe.local, "conf", frappe._dict(developer_mode=1, user_switcher_enabled=1)),
			patch.object(api, "delete_session") as delete,
		):
			api.end_orphaned_session()
		delete.assert_not_called()

	def test_normal_session_is_untouched(self):
		with patch.object(api, "delete_session") as delete:
			api.end_orphaned_session()
		delete.assert_not_called()

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
