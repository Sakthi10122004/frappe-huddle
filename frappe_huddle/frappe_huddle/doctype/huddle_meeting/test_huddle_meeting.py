# Copyright (c) 2026, Sakthi and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime


def make_meeting(**kwargs):
	"""Helper: create a minimal Huddle Meeting doc for tests."""
	defaults = {
		"doctype": "Huddle Meeting",
		"title": "Test Huddle",
		"meeting_date": str(add_to_date(now_datetime(), minutes=30)),
		"duration": 60,
		"status": "Scheduled",
	}
	defaults.update(kwargs)
	doc = frappe.get_doc(defaults)
	doc.insert(ignore_permissions=True)
	return doc


class TestHuddleMeeting(FrappeTestCase):
	# ── Status transitions ──────────────────────────────────────────────────

	def test_future_meeting_stays_scheduled(self):
		doc = make_meeting(meeting_date=str(add_to_date(now_datetime(), minutes=60)))
		doc.update_status()
		self.assertEqual(doc.status, "Scheduled")

	def test_started_meeting_becomes_in_progress(self):
		doc = make_meeting(meeting_date=str(add_to_date(now_datetime(), minutes=-5)))
		doc.update_status()
		self.assertEqual(doc.status, "In Progress")

	def test_past_meeting_becomes_completed(self):
		doc = make_meeting(
			meeting_date=str(add_to_date(now_datetime(), minutes=-120)),
			end_date=str(add_to_date(now_datetime(), minutes=-60)),
		)
		doc.update_status()
		self.assertEqual(doc.status, "Completed")

	def test_cancelled_meeting_status_never_changes(self):
		doc = make_meeting(
			status="Cancelled",
			meeting_date=str(add_to_date(now_datetime(), minutes=-120)),
		)
		changed = doc.update_status()
		self.assertFalse(changed)
		self.assertEqual(doc.status, "Cancelled")

	# ── Room name generation ────────────────────────────────────────────────

	def test_room_name_is_generated_on_insert(self):
		doc = make_meeting()
		self.assertIsNotNone(doc.jitsi_room)
		self.assertIn("test-huddle", doc.jitsi_room)

	def test_room_name_not_regenerated_on_update(self):
		doc = make_meeting()
		original_room = doc.jitsi_room
		doc.title = "Updated Title"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.jitsi_room, original_room)

	# ── join_meeting() authorization ────────────────────────────────────────

	def test_non_participant_cannot_join(self):
		"""A user not in the participants list must be denied."""
		doc = make_meeting()
		# Simulate a different user calling join_meeting
		frappe.set_user("Guest")
		try:
			from frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting import (
				join_meeting,
			)

			with self.assertRaises(frappe.exceptions.ValidationError):
				join_meeting(doc.name)
		finally:
			frappe.set_user("Administrator")

	# ── Duration validation ─────────────────────────────────────────────────

	def test_end_date_calculated_from_duration(self):
		doc = make_meeting(
			meeting_date=str(add_to_date(now_datetime(), minutes=60)), duration=30
		)
		self.assertIsNotNone(doc.end_date)
		# end_date should be meeting_date + 30 min
		diff = frappe.utils.time_diff_in_seconds(doc.end_date, doc.meeting_date)
		self.assertEqual(int(diff / 60), 30)

	# ── JWT token ───────────────────────────────────────────────────────────

	def test_jwt_not_generated_without_secret(self):
		"""If app_secret is blank, _generate_jwt_token returns None."""
		doc = make_meeting()
		settings = frappe._dict(app_secret=None, app_id="", enable_recording=0, enable_waiting_room=0)
		token = doc._generate_jwt_token(settings)
		self.assertIsNone(token)

	def test_jwt_generated_with_hs256_secret(self):
		"""A valid secret produces a 3-part JWT string."""
		try:
			import jwt as pyjwt
		except ImportError:
			self.skipTest("pyjwt not installed")

		doc = make_meeting()

		class FakeSettings:
			app_secret = "test-secret-key"
			app_id = "test-app"
			enable_recording = False
			enable_waiting_room = False

			def get_password(self, _):
				return self.app_secret

		token = doc._generate_jwt_token(FakeSettings())
		self.assertIsNotNone(token)
		self.assertEqual(len(token.split(".")), 3, "JWT should have 3 dot-separated parts")

	def test_jwt_secret_with_dots_is_still_signed(self):
		"""
		FIX regression test: a secret that contains dots (common in base64)
		must NOT be returned as-is — it must be signed properly.
		"""
		try:
			import jwt as pyjwt
		except ImportError:
			self.skipTest("pyjwt not installed")

		doc = make_meeting()
		dotted_secret = "abc.def.ghi"  # 3 parts — the old code returned this as-is

		class FakeSettings:
			app_secret = dotted_secret
			app_id = "test-app"
			enable_recording = False
			enable_waiting_room = False

			def get_password(self, _):
				return self.app_secret

		token = doc._generate_jwt_token(FakeSettings())
		# Must NOT equal the raw secret
		self.assertNotEqual(token, dotted_secret)
		# Must be a valid signed JWT (decodable with the secret)
		decoded = pyjwt.decode(token, dotted_secret, algorithms=["HS256"], audience="jitsi")
		self.assertEqual(decoded["room"], doc.jitsi_room)

	# ── Cleanup ─────────────────────────────────────────────────────────────

	def tearDown(self):
		frappe.db.rollback()
