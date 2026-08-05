# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class HuddleChatMessage(Document):
	def before_insert(self):
		self.sent_at = now_datetime()
		if not self.sender:
			self.sender = frappe.session.user

	def before_save(self):
		if self.is_deleted and not self.deleted_by:
			self.deleted_by = frappe.session.user

	def validate(self):
		self._validate_meeting_active()
		self._validate_message_content()

	def _validate_meeting_active(self):
		"""Only allow chat messages in live meetings."""
		meeting_status = frappe.db.get_value("Huddle Meeting", self.meeting, "status")
		if meeting_status not in ("Live", "Starting", "Ending"):
			frappe.throw(
				frappe._("Cannot send messages: meeting is not active."),
				title=frappe._("Meeting Not Active"),
			)

	def _validate_message_content(self):
		"""Ensure message is not empty or too long."""
		if not self.message or not self.message.strip():
			frappe.throw(frappe._("Message cannot be empty."))
		if len(self.message) > 5000:
			frappe.throw(frappe._("Message exceeds maximum length of 5000 characters."))
