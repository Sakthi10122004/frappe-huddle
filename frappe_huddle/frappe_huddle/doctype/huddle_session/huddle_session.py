# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

# pyrefly: ignore [missing-import]
import frappe
# pyrefly: ignore [missing-import]
from frappe.model.document import Document
# pyrefly: ignore [missing-import]
from frappe.utils import now_datetime


class HuddleSession(Document):
	def before_insert(self):
		if not self.session_token:
			self.session_token = frappe.generate_hash(length=20)
		if not self.connected_at:
			self.connected_at = now_datetime()

	def validate(self):
		self._validate_meeting_active()
		self._prevent_duplicate_active_session()

	def _validate_meeting_active(self):
		"""Ensure the meeting is still valid for new sessions."""
		if self.is_new():
			meeting_status = frappe.db.get_value("Huddle Meeting", self.meeting, "status")
			if meeting_status not in ("Live", "Starting"):
				frappe.throw(
					frappe._("Cannot create session: meeting is not live (status: {0}).").format(meeting_status),
					title=frappe._("Meeting Not Active"),
				)

	def _prevent_duplicate_active_session(self):
		"""Prevent duplicate active sessions for the same user in the same meeting."""
		if self.is_new() and self.is_active:
			existing = frappe.db.exists("Huddle Session", {
				"meeting": self.meeting,
				"participant": self.participant,
				"is_active": 1,
			})
			if existing:
				frappe.throw(
					frappe._("User {0} already has an active session in this meeting.").format(self.participant),
					title=frappe._("Duplicate Session"),
				)

	def close_session(self):
		"""Mark session as inactive and record disconnection time."""
		self.is_active = 0
		self.session_state = "Disconnected"
		self.disconnected_at = now_datetime()
		self.save(ignore_permissions=True)
