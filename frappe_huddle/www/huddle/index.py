import frappe
from frappe import _


def get_context(context):
	context.meetings = get_meetings()
	context.can_configure = "System Manager" in frappe.get_roles()

	if context.can_configure:
		# FIX: fetch settings but NEVER pass app_secret to the template
		settings = frappe.get_doc("Huddle Settings")
		context.huddle_settings = frappe._dict(
			jitsi_domain=settings.jitsi_domain or "",
			app_id=settings.app_id or "",
			# app_secret intentionally omitted — never render a Password field into HTML
			default_duration=settings.default_duration or 60,
			enable_waiting_room=settings.enable_waiting_room,
			enable_recording=settings.enable_recording,
			send_email_invite=settings.send_email_invite,
			email_template=settings.email_template or "",
		)
		context.team_members = get_team_members()

	context.no_cache = 1


def get_meetings(limit=50):
	"""
	FIX: batch all DB lookups to eliminate the N+1 query problem.
	Previously: 3 queries per meeting (owner user, user image, participants).
	Now: 3 queries total regardless of how many meetings.
	Also adds a limit to prevent unbounded page size.
	"""
	meetings = frappe.get_all(
		"Huddle Meeting",
		fields=["name", "title", "status", "meeting_date", "duration", "jitsi_url", "owner"],
		order_by="meeting_date desc",
		filters={"status": ["!=", "Cancelled"]},
		limit=limit,
	)

	if not meetings:
		return meetings

	# Batch-fetch all owners in one query
	owner_names = list({m.owner for m in meetings})
	users = frappe.get_all(
		"User",
		filters={"name": ["in", owner_names]},
		fields=["name", "full_name", "user_image"],
	)
	user_map = {u.name: u for u in users}

	# Batch-fetch all participants in one query
	meeting_names = [m.name for m in meetings]
	all_participants = frappe.get_all(
		"Huddle Participant",
		filters={"parent": ["in", meeting_names]},
		fields=["parent", "full_name", "email", "user", "joined"],
	)

	# Build participant user images in one query
	participant_user_names = list({p.user for p in all_participants if p.user})
	participant_user_map = {}
	if participant_user_names:
		p_users = frappe.get_all(
			"User",
			filters={"name": ["in", participant_user_names]},
			fields=["name", "user_image"],
		)
		participant_user_map = {u.name: u.user_image for u in p_users}

	# Group participants by meeting
	participants_by_meeting = {}
	for p in all_participants:
		if p.user:
			p.user_image = participant_user_map.get(p.user)
		participants_by_meeting.setdefault(p.parent, []).append(p)

	# Assemble final result
	for meeting in meetings:
		owner = user_map.get(meeting.owner, frappe._dict())
		meeting.user_fullname = owner.get("full_name") or meeting.owner
		meeting.user_image = owner.get("user_image")
		meeting.participants = participants_by_meeting.get(meeting.name, [])

	return meetings


def get_team_members():
	return frappe.get_all(
		"User",
		fields=["name", "full_name", "user_image", "email", "enabled"],
		filters={"user_type": "System User", "enabled": 1},
		limit=100,
	)


@frappe.whitelist()
def save_settings(settings):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not authorized"), frappe.PermissionError)

	import json

	data = json.loads(settings)

	doc = frappe.get_doc("Huddle Settings")

	# FIX: never accept app_secret from the browser — if the field is not in the
	# submitted payload (or is the placeholder), skip updating it
	allowed_fields = {
		"jitsi_domain",
		"app_id",
		"default_duration",
		"enable_waiting_room",
		"enable_recording",
		"send_email_invite",
		"email_template",
	}

	for key, value in data.items():
		if key in allowed_fields:
			doc.set(key, value)

	# app_secret updated separately only if explicitly provided and non-empty
	if data.get("app_secret") and data["app_secret"] != "••••••••":
		doc.app_secret = data["app_secret"]

	doc.save()
	return {"status": "ok"}


@frappe.whitelist()
def add_team_member(email, full_name):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not authorized"), frappe.PermissionError)

	if frappe.db.exists("User", email):
		frappe.throw(_("User already exists"))

	user = frappe.new_doc("User")
	user.email = email
	user.first_name = full_name
	user.send_welcome_email = 0
	user.enabled = 1
	user.user_type = "System User"
	user.insert(ignore_permissions=True)
	return {"status": "ok"}


@frappe.whitelist()
def update_team_member(user_name, full_name, enabled=1):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not authorized"), frappe.PermissionError)

	if not frappe.db.exists("User", user_name):
		frappe.throw(_("User not found"))

	user = frappe.get_doc("User", user_name)
	user.first_name = full_name
	user.enabled = int(enabled)
	user.save(ignore_permissions=True)
	return {"status": "ok"}


@frappe.whitelist()
def remove_team_member(user_name):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not authorized"), frappe.PermissionError)

	if frappe.session.user == user_name:
		frappe.throw(_("You cannot remove yourself"))

	user = frappe.get_doc("User", user_name)
	user.enabled = 0
	user.save(ignore_permissions=True)
	return {"status": "ok"}


@frappe.whitelist()
def create_meeting(title, meeting_date, duration=60, participants=None):
	if not frappe.session.user or frappe.session.user == "Guest":
		frappe.throw(_("Please login to create meetings"), frappe.PermissionError)

	import json

	if participants and isinstance(participants, str):
		participants = json.loads(participants)

	meeting = frappe.new_doc("Huddle Meeting")
	meeting.title = title
	meeting.meeting_date = meeting_date
	meeting.duration = duration
	meeting.status = "Scheduled"

	if participants:
		for p in participants:
			email = p.get("email")
			if not email:
				continue

			# FIX: resolve email → User name before adding as a Link field
			# This prevents silent failures when the email doesn't match a User
			user_name = frappe.db.get_value("User", {"email": email}, "name")
			if not user_name:
				frappe.msgprint(
					f"User with email {email} not found — skipping.",
					indicator="orange",
					alert=True,
				)
				continue

			# FIX: deduplicate participants
			already_added = any(row.get("user") == user_name for row in meeting.participants)
			if already_added:
				continue

			meeting.append(
				"participants",
				{
					"user": user_name,
					"full_name": p.get("full_name")
					or frappe.db.get_value("User", user_name, "full_name"),
					"email": email,
				},
			)

	meeting.insert(ignore_permissions=True)
	return {"status": "ok", "name": meeting.name, "url": meeting.jitsi_url}


@frappe.whitelist()
def cancel_meeting(meeting_name):
	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	if meeting.owner != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("Not authorized to cancel this meeting"), frappe.PermissionError)

	meeting.status = "Cancelled"
	meeting.save(ignore_permissions=True)
	return {"status": "ok"}


@frappe.whitelist(allow_guest=True)
def jitsi_webhook():
	"""Webhook endpoint for Jitsi to send participant events."""
	expected_secret = frappe.db.get_single_value("Huddle Settings", "webhook_secret")

	# FIX: reject all requests when no secret is configured (prevents open endpoint)
	if not expected_secret:
		frappe.logger().warning("Huddle webhook called but webhook_secret is not configured")
		return {"status": "not_configured"}

	if frappe.request.headers.get("Authorization") != expected_secret:
		return {"status": "unauthorized"}

	data = frappe.request.get_json() if frappe.request else None
	if not data:
		return {"status": "ignored"}

	event_type = data.get("eventType")
	room_name = data.get("room_name") or data.get("roomName")

	if not room_name:
		return {"status": "ignored"}

	meeting_name = frappe.db.get_value("Huddle Meeting", {"jitsi_room": room_name})
	if not meeting_name:
		return {"status": "not_found"}

	meeting = frappe.get_doc("Huddle Meeting", meeting_name)

	if event_type == "PARTICIPANT_JOINED":
		email = data.get("email") or (data.get("user") or {}).get("email")
		if email:
			participant_user = frappe.db.get_value("User", {"email": email}, "name")
			if participant_user:
				# FIX: verify the user is actually a participant in this meeting
				# before writing any attendance record
				is_authorized = participant_user in [meeting.owner, meeting.created_by_user] or any(
					p.user == participant_user for p in meeting.participants
				)
				if not is_authorized:
					frappe.logger().warning(
						f"Webhook: {participant_user} joined {meeting_name} but is not a participant"
					)
					# Still allow status update but don't write attendance log
				else:
					session_id = data.get("sessionId") or data.get("session_id") or "webhook_session"
					if not frappe.db.exists(
						"Huddle Attendance Log",
						{
							"meeting": meeting_name,
							"participant": participant_user,
							"session_id": session_id,
							"leave_time": ("is", "not set"),
						},
					):
						log = frappe.get_doc(
							{
								"doctype": "Huddle Attendance Log",
								"meeting": meeting_name,
								"participant": participant_user,
								"join_time": frappe.utils.now_datetime(),
								"session_id": session_id,
							}
						)
						log.insert(ignore_permissions=True)

		if meeting.status == "Scheduled":
			meeting.db_set("status", "In Progress", update_modified=False)

	elif event_type == "PARTICIPANT_LEFT":
		email = data.get("email") or (data.get("user") or {}).get("email")
		if email:
			participant_user = frappe.db.get_value("User", {"email": email}, "name")
			if participant_user:
				session_id = (
					data.get("sessionId") or data.get("session_id") or "webhook_session"
				)
				active_log = frappe.db.get_value(
					"Huddle Attendance Log",
					{
						"meeting": meeting_name,
						"participant": participant_user,
						"session_id": session_id,
						"leave_time": ("is", "not set"),
					},
					"name",
				)
				if active_log:
					now_dt = frappe.utils.now_datetime()
					frappe.db.set_value(
						"Huddle Attendance Log", active_log, "leave_time", now_dt
					)
					log_doc = frappe.get_doc("Huddle Attendance Log", active_log)
					# FIX: guard for None join_time
					if log_doc.join_time:
						duration = (now_dt - log_doc.join_time).total_seconds()
						frappe.db.set_value(
							"Huddle Attendance Log", active_log, "duration", duration
						)

	elif event_type == "ROOM_DESTROYED":
		if meeting.status != "Cancelled":
			meeting.db_set("status", "Completed", update_modified=False)

	return {"status": "ok"}
