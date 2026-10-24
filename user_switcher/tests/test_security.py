# * user_switcher/tests/test_security.py
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from user_switcher import api


class TestSecurityAndPrivilegeEscalation(IntegrationTestCase):
	"""Tests to detect security loopholes, permission bypasses, and privilege escalation."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# Ensure test manager exists with password
		if not frappe.db.exists("User", "us_victim_sm@example.com"):
			frappe.get_doc({
				"doctype": "User",
				"email": "us_victim_sm@example.com",
				"first_name": "Victim",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}]
			}).insert()
		frappe.utils.password.update_password("us_victim_sm@example.com", "SecretPass123!")

		# Ensure attacker manager exists
		if not frappe.db.exists("User", "us_attacker_sm@example.com"):
			frappe.get_doc({
				"doctype": "User",
				"email": "us_attacker_sm@example.com",
				"first_name": "Attacker",
				"send_welcome_email": 0,
				"roles": [{"role": "System Manager"}]
			}).insert()
		frappe.utils.password.update_password("us_attacker_sm@example.com", "AttackerPass123!")

		# Ensure standard non-admin user exists
		if not frappe.db.exists("User", "us_standard_user@example.com"):
			frappe.get_doc({
				"doctype": "User",
				"email": "us_standard_user@example.com",
				"first_name": "Standard",
				"send_welcome_email": 0,
				"roles": [{"role": "Desk User"}]
			}).insert()
		frappe.utils.password.update_password("us_standard_user@example.com", "StandardPass123!")

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for email in ("us_victim_sm@example.com", "us_attacker_sm@example.com", "us_standard_user@example.com"):
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True)
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.conf = patch.object(frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1))
		self.conf.start()
		self.addCleanup(self.conf.stop)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_non_system_manager_cannot_call_switch_to_user(self):
		frappe.set_user("us_standard_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			api.switch_to_user("Administrator")

	def test_non_system_manager_cannot_create_test_user(self):
		frappe.set_user("us_standard_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			api.create_test_user("Hacker", "hacker@example.com", roles=["System Manager"], switch=0)

	def test_non_system_manager_cannot_set_user_roles(self):
		frappe.set_user("us_standard_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			api.set_user_roles("us_standard_user@example.com", ["System Manager"])

	def test_non_system_manager_cannot_manage_doctype_access(self):
		frappe.set_user("us_standard_user@example.com")
		with self.assertRaises(frappe.PermissionError):
			api.get_doctype_access("ToDo")
		with self.assertRaises(frappe.PermissionError):
			api.set_doctype_access("ToDo", {"Desk User": {"write": 1}})

	def test_case_bypass_administrator_switch(self):
		"""System Manager trying to switch to 'administrator' via casing or whitespace tricks must be blocked."""
		frappe.set_user("us_attacker_sm@example.com")
		with patch.object(frappe.local, "login_manager", MagicMock(), create=True), \
			 patch.object(frappe.local, "session_obj", MagicMock(), create=True):
			for payload in ["administrator", "ADMINISTRATOR", "Administrator ", " administrator"]:
				with self.assertRaises(frappe.PermissionError, msg=f"Payload {payload} bypassed blocked target check!"):
					api.switch_to_user(payload)

	def test_case_bypass_other_system_manager_switch(self):
		"""System Manager trying to switch to another System Manager via case variation must be blocked."""
		frappe.set_user("us_attacker_sm@example.com")
		with patch.object(frappe.local, "login_manager", MagicMock(), create=True), \
			 patch.object(frappe.local, "session_obj", MagicMock(), create=True):
			for payload in [
				"US_VICTIM_SM@EXAMPLE.COM",
				"us_victim_sm@example.com ",
				" us_victim_sm@example.com",
			]:
				with self.assertRaises(frappe.PermissionError, msg=f"Payload {payload} bypassed victim SM block!"):
					api.switch_to_user(payload)

	def test_case_bypass_administrator_set_user_roles(self):
		"""System Manager trying to manage roles of Administrator via case/whitespace trick must be rejected."""
		frappe.set_user("us_attacker_sm@example.com")
		for payload in ["administrator", "ADMINISTRATOR", "Administrator ", " administrator"]:
			with self.assertRaises((frappe.ValidationError, frappe.PermissionError), msg=f"Managed Administrator roles via {payload}!"):
				api.set_user_roles(payload, ["Desk User"])

	def test_case_bypass_victim_manager_set_user_roles(self):
		"""System Manager trying to manage roles of another Manager via case trick must be blocked."""
		frappe.set_user("us_attacker_sm@example.com")
		for payload in ["US_VICTIM_SM@EXAMPLE.COM", "us_victim_sm@example.com ", " us_victim_sm@example.com"]:
			with self.assertRaises(frappe.PermissionError, msg=f"Managed victim manager roles via {payload}!"):
				api.set_user_roles(payload, ["Desk User"])


class TestCrashAndFuzzing(IntegrationTestCase):
	"""Tests for unhandled 500 errors when passing invalid/malformed types to whitelisted endpoints."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.conf = patch.object(frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1))
		self.conf.start()
		self.addCleanup(self.conf.stop)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_get_context_with_malformed_inputs(self):
		"""get_context should gracefully handle invalid types from API without raising 500."""
		# txt as whitespace
		res = api.get_context(txt="   ")
		self.assertTrue(res["allowed"])

		# limit as string representation of number or invalid string
		res = api.get_context(limit="50")
		self.assertTrue(res["allowed"])

		# negative or invalid limits
		res = api.get_context(limit="-10")
		self.assertTrue(res["allowed"])
		res = api.get_context(limit="not_a_number")
		self.assertTrue(res["allowed"])

		# cached as invalid json string
		res = api.get_context(cached="{not_valid_json")
		self.assertTrue(res["allowed"])
		self.assertEqual(res["stale"], [])

		# cached as int should raise FrappeTypeError (not unhandled 500)
		with self.assertRaises(frappe.exceptions.FrappeTypeError):
			api.get_context(cached=12345)

	def test_search_doctypes_with_malformed_inputs(self):
		"""search_doctypes should gracefully handle non-string txt without crashing."""
		res = api.search_doctypes(txt=None)
		self.assertIsInstance(res, list)

		res = api.search_doctypes(txt="")
		self.assertIsInstance(res, list)

		res = api.search_doctypes(txt="   ")
		self.assertIsInstance(res, list)

	def test_set_user_roles_with_malformed_inputs(self):
		"""set_user_roles should gracefully handle various formats and reject bad types."""
		user = "us_standard_user@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({
				"doctype": "User", "email": user, "first_name": "Standard", "send_welcome_email": 0
			}).insert()

		# Single string role (non-JSON)
		res = api.set_user_roles(user, roles="Website Manager")
		self.assertIn("Website Manager", res["roles"])

		# Roles with whitespace
		res = api.set_user_roles(user, roles=["  Website Manager  "])
		self.assertIn("Website Manager", res["roles"])

		# Invalid JSON string gracefully handled as single role or empty
		res = api.set_user_roles(user, roles="{invalid_json")
		self.assertIsInstance(res["roles"], list)

		# Malformed roles type (int) should raise FrappeTypeError (not unhandled 500)
		with self.assertRaises(frappe.exceptions.FrappeTypeError):
			api.set_user_roles(user, roles=12345)

	def test_set_doctype_access_with_malformed_inputs(self):
		"""set_doctype_access should gracefully handle malformed changes payloads."""
		# Non-dict JSON payload
		with self.assertRaises(frappe.ValidationError):
			api.set_doctype_access("ToDo", changes="[1, 2, 3]")

		# Broken JSON string
		with self.assertRaises(frappe.ValidationError):
			api.set_doctype_access("ToDo", changes="{unparseable json")

		# Empty changes should safely return access without modifying anything
		res = api.set_doctype_access("ToDo", changes={})
		self.assertEqual(res["doctype"], "ToDo")

		res = api.set_doctype_access("ToDo", changes=None)
		self.assertEqual(res["doctype"], "ToDo")


class TestDoctypeAccessEdgeCases(IntegrationTestCase):
	"""Tests for DocType access edge cases, Single doctypes, and validation."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.conf = patch.object(frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1))
		self.conf.start()
		self.addCleanup(self.conf.stop)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_nonexistent_doctype_access(self):
		with self.assertRaises(frappe.ValidationError):
			api.get_doctype_access("DefinitelyNonExistentDocType123")
		with self.assertRaises(frappe.ValidationError):
			api.set_doctype_access("DefinitelyNonExistentDocType123", {})

	def test_single_doctype_access(self):
		"""Single DocType handling (e.g. System Settings)."""
		res = api.get_doctype_access("System Settings")
		self.assertIn("read", res["rights"])
		self.assertNotIn("create", res["rights"])
		self.assertNotIn("delete", res["rights"])

	def test_permission_dependency_validation(self):
		"""Test all permission dependencies: Cancel needs Submit, Submit needs Write, Amend needs Cancel, Import needs Create."""
		doctype = "Purchase Receipt"
		had_custom = bool(frappe.db.exists("Custom DocPerm", {"parent": doctype}))
		try:
			# Cancel without Submit
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(doctype, {"Stock Manager": {"submit": 0, "cancel": 1}})

			# Submit without Write
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(doctype, {"Stock Manager": {"write": 0, "submit": 1}})

			# Amend without Cancel
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(doctype, {"Stock Manager": {"cancel": 0, "amend": 1}})

			# Import without Create
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(doctype, {"Stock Manager": {"create": 0, "import": 1}})
		finally:
			if not had_custom:
				frappe.permissions.reset_perms(doctype)

	def test_must_keep_read_permission(self):
		"""Dropping read permission from all rules must be rejected."""
		doctype = "Bill of Entry"
		had_custom = bool(frappe.db.exists("Custom DocPerm", {"parent": doctype}))
		try:
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(
					doctype,
					{
						"Accounts Manager": {"read": 0, "write": 1},
						"Accounts User": {"read": 0, "write": 1},
						"Auditor": {"read": 0},
						"Purchase User": {"read": 0},
					},
				)
		finally:
			if not had_custom:
				frappe.permissions.reset_perms(doctype)

	def test_must_keep_at_least_one_rule(self):
		"""Removing all basic permissions from all rules on a doctype must be rejected."""
		doctype = "Bill of Entry"
		had_custom = bool(frappe.db.exists("Custom DocPerm", {"parent": doctype}))
		try:
			with self.assertRaises(frappe.ValidationError):
				api.set_doctype_access(
					doctype,
					{
						"Accounts Manager": {"read": 0, "write": 0, "create": 0, "submit": 0, "cancel": 0},
						"Accounts User": {"read": 0, "write": 0, "create": 0, "submit": 0, "cancel": 0},
						"Auditor": {"read": 0, "write": 0, "create": 0, "submit": 0, "cancel": 0},
						"Purchase User": {"read": 0, "write": 0, "create": 0, "submit": 0, "cancel": 0},
					},
				)
		finally:
			if not had_custom:
				frappe.permissions.reset_perms(doctype)


class TestCreateTestUserEdgeCases(IntegrationTestCase):
	"""Tests for create_test_user behavior and hardening."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.conf = patch.object(frappe.local, "conf", frappe._dict(frappe.local.conf, developer_mode=1, user_switcher_enabled=1))
		self.conf.start()
		self.addCleanup(self.conf.stop)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_create_user_with_single_role_string(self):
		"""Passing a single role as a plain string instead of list/JSON should work."""
		email = "us_single_role_test@example.com"
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True)

		user = api.create_test_user("Single Role", email, roles="Website Manager", switch=0)
		self.assertEqual(user["name"], email)
		self.assertIn("Website Manager", user["roles"])

		frappe.delete_doc("User", email, force=True)

	def test_create_user_with_boolean_or_string_switch(self):
		"""Passing switch as 'false', '0', or False should not raise ValueError."""
		email = "us_switch_fuzz_test@example.com"
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True)

		# switch="false"
		user = api.create_test_user("Switch Test", email, roles=[], switch="false")
		self.assertEqual(user["name"], email)
		frappe.delete_doc("User", email, force=True)

		# switch="0"
		user = api.create_test_user("Switch Test", email, roles=[], switch="0")
		self.assertEqual(user["name"], email)
		frappe.delete_doc("User", email, force=True)

		# switch=False
		user = api.create_test_user("Switch Test", email, roles=[], switch=False)
		self.assertEqual(user["name"], email)
		frappe.delete_doc("User", email, force=True)

	def test_create_user_empty_name(self):
		with self.assertRaises(frappe.ValidationError):
			api.create_test_user("   ", "empty_name@example.com", roles=[], switch=0)

	def test_create_user_empty_or_invalid_email(self):
		with self.assertRaises(frappe.ValidationError):
			api.create_test_user("Valid Name", "   ", roles=[], switch=0)
		with self.assertRaises(frappe.InvalidEmailAddressError):
			api.create_test_user("Valid Name", "not_an_email", roles=[], switch=0)

	def test_create_user_duplicate_email(self):
		email = "us_dup_test@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": "Dup", "send_welcome_email": 0
			}).insert()
		try:
			with self.assertRaises(frappe.DuplicateEntryError):
				api.create_test_user("Duplicate User", email, roles=[], switch=0)
		finally:
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True)
