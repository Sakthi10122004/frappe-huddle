# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


class TestHuddleMeeting(FrappeTestCase):
	def setUp(self):
		# Clean up any leftover test data
		frappe.db.delete("Huddle Participant", {"parent": ["like", "HM-%"]})
		frappe.db.delete("Huddle Meeting", {"title": ["like", "Test %"]})

	def tearDown(self):
		frappe.db.delete("Huddle Participant", {"parent": ["like", "HM-%"]})
		frappe.db.delete("Huddle Meeting", {"title": ["like", "Test %"]})

	def get_future_meeting_date(self):
		return add_to_date(now_datetime(), days=1).strftime("%Y-%m-%d %H:%M:%S")

	# ── Room ID ──────────────────────────────────────────────────────────

	def test_room_id_auto_generated(self):
		"""room_id should be auto-generated when starting a meeting."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Auto Room",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		self.assertFalse(doc.room_id, "room_id should not exist on insert")
		
		doc.start_meeting()
		self.assertTrue(doc.room_id, "room_id should be auto-generated on start")

	def test_room_id_is_unique(self):
		"""Two started meetings should never have the same room_id."""
		doc1 = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Unique Room 1",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc1.insert(ignore_permissions=True)
		doc1.start_meeting()

		doc2 = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Unique Room 2",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc2.insert(ignore_permissions=True)
		doc2.start_meeting()
		self.assertNotEqual(doc1.room_id, doc2.room_id)

	# ── Status Transitions ───────────────────────────────────────────────

	def test_default_status_is_scheduled(self):
		"""New meetings should default to Scheduled."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Default Status",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.status, "Scheduled")

	def test_start_meeting(self):
		"""start_meeting() should set status=Live, is_active=1, started_at."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Start Meeting",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		doc.start_meeting()
		self.assertEqual(doc.status, "Live")
		self.assertEqual(doc.is_active, 1)
		self.assertIsNotNone(doc.started_at)

	def test_end_meeting(self):
		"""end_meeting() should set status=Ended, is_active=0, ended_at."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test End Meeting",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		doc.start_meeting()
		doc.end_meeting()
		self.assertEqual(doc.status, "Ended")
		self.assertEqual(doc.is_active, 0)
		self.assertIsNotNone(doc.ended_at)

	def test_cancel_meeting(self):
		"""cancel_meeting() should set status=Cancelled, is_active=0."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Cancel Meeting",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		doc.cancel_meeting()
		self.assertEqual(doc.status, "Cancelled")
		self.assertEqual(doc.is_active, 0)

	# ── Host Auto-set ────────────────────────────────────────────────────

	def test_host_auto_set(self):
		"""Host should auto-set to current user if not provided."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Host Autoset",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.host, frappe.session.user)

	# ── Naming ───────────────────────────────────────────────────────────

	def test_naming_format(self):
		"""Meeting names should follow the HM-#### format."""
		doc = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Naming",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name.startswith("HM-"), f"Name {doc.name} should start with HM-")

	# ── Join & Leave APIs ────────────────────────────────────────────────

	def test_join_meeting_with_session_id(self):
		"""A user can join a meeting, which creates a Huddle Session, and rejoin, which updates state."""
		from frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting import join_meeting, leave_meeting
		
		frappe.set_user("Administrator")
		meeting = frappe.get_doc({
			"doctype": "Huddle Meeting",
			"title": "Test Multiple Sessions",
			"host": "Administrator",
			"meeting_date": self.get_future_meeting_date(),
		})
		meeting.insert(ignore_permissions=True)
		meeting.start_meeting()

		# Join session A
		result1 = join_meeting(meeting.name)
		self.assertTrue(result1["success"])

		# Rejoin (same user)
		result2 = join_meeting(meeting.name)
		self.assertTrue(result2["success"])
		self.assertEqual(result1["participant"], result2["participant"])

		# Total active participants for Administrator should be 1
		active_count = frappe.db.count("Huddle Participant", {
			"parent": meeting.name,
			"user": "Administrator",
			"is_active": 1
		})
		self.assertEqual(active_count, 1)

		# Leave
		leave_meeting(meeting.name)
		
		# Participant should be inactive
		p_a = frappe.get_doc("Huddle Participant", result1["participant"])
		self.assertEqual(p_a.is_active, 0)
		self.assertEqual(p_a.state, "Left")
