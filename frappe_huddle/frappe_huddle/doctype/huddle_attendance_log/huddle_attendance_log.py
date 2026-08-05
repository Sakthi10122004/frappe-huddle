# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, time_diff_in_seconds


class HuddleAttendanceLog(Document):
	def validate(self):
		self._compute_duration()
		self._compute_effective_duration()
		self._determine_status()

	def _compute_duration(self):
		"""Compute total wall-clock duration from join to leave."""
		if self.join_time and self.leave_time:
			self.duration = time_diff_in_seconds(self.leave_time, self.join_time)

	def _compute_effective_duration(self):
		"""Compute effective presence = total duration - disconnect gaps."""
		if getattr(self, "duration", None):
			gaps = getattr(self, "disconnect_gaps", 0) or 0
			self.effective_duration = max(0, self.duration - gaps)

	def _determine_status(self):
		"""Auto-determine attendance status based on timing data."""
		if not self.join_time:
			self.status = "Absent"
			return

		if not self.leave_time:
			# Meeting may still be in progress
			self.status = "Present"
			return

		meeting_start = frappe.db.get_value("Huddle Meeting", self.meeting, "started_at")
		meeting_end = frappe.db.get_value("Huddle Meeting", self.meeting, "ended_at")

		if not meeting_start or not meeting_end:
			self.status = "Present"
			return

		# Late if joined more than 5 minutes after meeting started
		if time_diff_in_seconds(self.join_time, meeting_start) > 300:
			self.status = "Late"
		elif getattr(self, "effective_duration", None) and getattr(self, "duration", None):
			# Partial if effective presence is less than 70% of wall-clock time
			ratio = self.effective_duration / self.duration if self.duration > 0 else 1
			self.status = "Partial" if ratio < 0.7 else "Present"
		else:
			self.status = "Present"


def create_attendance_log(meeting, participant, session=None):
	"""Create an attendance log entry when a user joins a meeting."""
	doc = frappe.get_doc({
		"doctype": "Huddle Attendance Log",
		"meeting": meeting,
		"participant": participant,
		"session": session,
		"join_time": now_datetime(),
		"status": "Present",
	})
	doc.insert(ignore_permissions=True)
	return doc.name


def finalize_attendance_log(meeting, participant, session=None, disconnect_reason=None):
	"""Finalize attendance log when a user leaves a meeting."""
	filters = {
		"meeting": meeting,
		"participant": participant,
		"leave_time": ["is", "not set"],
	}
	if session:
		filters["session"] = session

	log_name = frappe.db.get_value("Huddle Attendance Log", filters, "name")
	if not log_name:
		return None

	log = frappe.get_doc("Huddle Attendance Log", log_name)
	log.leave_time = now_datetime()
	
	from frappe.utils import time_diff_in_seconds
	log.duration = time_diff_in_seconds(log.leave_time, log.join_time)
	log.is_complete = 1
	if disconnect_reason:
		log.disconnect_reason = disconnect_reason
	else:
		log.disconnect_reason = "Normal"
		
	log.save(ignore_permissions=True)
	
	_update_participant_total_duration(meeting, participant)
	return log.name

def _update_participant_total_duration(meeting, participant):
	from frappe.utils import flt
	logs = frappe.get_all("Huddle Attendance Log", filters={"meeting": meeting, "participant": participant}, fields=["duration"])
	total = sum([flt(l.duration) for l in logs])
	
	participant_name = frappe.db.get_value("Huddle Participant", {"parent": meeting, "user": participant}, "name")
	if participant_name:
		frappe.db.set_value("Huddle Participant", participant_name, "total_duration", total)
