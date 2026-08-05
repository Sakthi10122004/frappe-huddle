# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HuddleParticipant(Document):
	def validate(self):
		"""Prevent duplicate active participants for the same session in a meeting."""
		if self.is_new() and self.state == "Joined":
			filters = {
				"parent": self.parent,
				"parenttype": "Huddle Meeting",
				"parentfield": "participants",
				"user": self.user,
				"is_active": 1,
			}
			if self.session_id:
				filters["session_id"] = self.session_id

			existing = frappe.db.exists("Huddle Participant", filters)
			
			if existing:
				frappe.throw(
					frappe._("User {0} is already an active participant in this meeting with this session.").format(self.user),
					title=frappe._("Duplicate Participant"),
				)
