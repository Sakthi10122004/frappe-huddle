# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class HuddleRoomEvent(Document):
	def before_insert(self):
		if not self.timestamp:
			self.timestamp = now_datetime()
		if not self.triggered_by:
			self.triggered_by = frappe.session.user

	def validate(self):
		if not frappe.db.exists("Huddle Meeting", self.meeting):
			frappe.throw(frappe._("Meeting {0} does not exist.").format(self.meeting))


def log_room_event(meeting, event_type, source="System", session=None, triggered_by=None, target_user=None, metadata=None):
	"""Utility to create a room event log entry."""
	import json

	doc = frappe.get_doc({
		"doctype": "Huddle Room Event",
		"meeting": meeting,
		"event_type": event_type,
		"source": source,
		"session": session,
		"triggered_by": triggered_by or frappe.session.user,
		"target_user": target_user,
		"timestamp": now_datetime(),
		"metadata": json.dumps(metadata) if metadata else None,
	})
	doc.insert(ignore_permissions=True)
	return doc.name
