# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import uuid
import time


class HuddleMeeting(Document):
	def before_insert(self):
		"""Set defaults before first save."""
		if not self.created_by_user:
			self.created_by_user = frappe.session.user

	def onload(self):
		"""Update status when document is loaded if it's past its end date."""
		if self.update_status():
			self.db_set("status", self.status, update_modified=False)

	def validate(self):
		"""Run validations before save."""
		self._validate_duration()

	def before_save(self):
		"""Generate Jitsi room details before saving."""
		if not self.jitsi_room:
			self.jitsi_room = self._generate_room_name()

		settings = frappe.get_doc("Huddle Settings")
		domain = settings.jitsi_domain or "meet.jit.si"
		app_id = settings.app_id or ""

		if domain == "8x8.vc" and app_id:
			self.jitsi_url = f"https://{domain}/{app_id}/{self.jitsi_room}"
		else:
			self.jitsi_url = f"https://{domain}/{self.jitsi_room}"

		self.jitsi_embed = self._generate_embed_html(settings)

		if self.meeting_date and self.duration:
			self.end_date = frappe.utils.add_to_date(self.meeting_date, minutes=self.duration)

		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc:
				if old_doc.meeting_date != self.meeting_date:
					self._notify_reschedule(old_doc)
				elif old_doc.status != self.status and self.status == "Cancelled":
					self._notify_cancellation()

		self.update_status()

	def _validate_duration(self):
		"""Enforce duration limits from Huddle Settings."""
		settings = frappe.get_doc("Huddle Settings")

		if not settings.enforce_duration_limit:
			return

		max_duration = settings.max_duration_minutes or 120
		mode = settings.duration_enforcement_mode or "Warn"

		if self.duration and self.duration > max_duration:
			msg = f"Meeting duration ({self.duration} mins) exceeds the allowed maximum of {max_duration} mins."
			if mode == "Hard":
				frappe.throw(msg, title="Duration Limit Exceeded")
			else:
				frappe.msgprint(
					msg + " Consider shortening the meeting.",
					title="Duration Warning",
					indicator="orange",
				)

	def update_status(self):
		"""Update meeting status based on current time."""
		if self.status == "Cancelled":
			return False

		if not self.meeting_date:
			return False

		if not self.end_date and self.duration:
			self.end_date = frappe.utils.add_to_date(self.meeting_date, minutes=self.duration)

		now = frappe.utils.get_datetime(frappe.utils.now())
		start = frappe.utils.get_datetime(self.meeting_date)
		end = frappe.utils.get_datetime(self.end_date) if self.end_date else None

		new_status = self.status

		if end and now > end:
			new_status = "Completed"
		elif now >= start:
			new_status = "In Progress"
		else:
			new_status = "Scheduled"

		if new_status != self.status:
			self.status = new_status
			return True

		return False

	def after_insert(self):
		"""Send email invites after a new meeting is created."""
		# FIX: wrap calendar sync in try/except so it never blocks meeting creation
		try:
			self.sync_frappe_event()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Huddle: Frappe Event sync failed on insert")

		settings = frappe.get_doc("Huddle Settings")
		if settings.send_email_invite and self.participants:
			self._send_email_invites(settings)

	def on_update(self):
		"""Keep Frappe Event synced with this Huddle Meeting."""
		if not self.is_new():
			# FIX: wrap calendar sync in try/except so it never blocks meeting saves
			try:
				self.sync_frappe_event()
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Huddle: Frappe Event sync failed on update")

	def sync_frappe_event(self):
		"""Create or update a standard Frappe Event so it appears in the system calendar."""
		if getattr(self, "flags", {}).get("from_event"):
			return

		event_name = frappe.db.get_value(
			"Event",
			{"reference_doctype": "Huddle Meeting", "reference_docname": self.name},
			"name",
		)

		if getattr(self, "status", "") == "Cancelled":
			if event_name:
				frappe.delete_doc("Event", event_name, ignore_permissions=True)
			return

		event = frappe.get_doc("Event", event_name) if event_name else frappe.new_doc("Event")

		if not event_name:
			event.reference_doctype = "Huddle Meeting"
			event.reference_docname = self.name

		event.subject = self.title
		event.starts_on = self.meeting_date
		event.ends_on = self.end_date or frappe.utils.add_to_date(
			self.meeting_date, minutes=self.duration or 60
		)
		join_url = f"/huddle/join?meeting={self.name}"
		event.description = f"Video Meeting. <a href='{join_url}'>Join Huddle</a>"
		event.event_type = "Private"
		event.status = "Open"
		event.color = "#0ea5a0"
		event.flags.from_huddle = True

		if not event_name:
			event.insert(ignore_permissions=True)

		existing = {
			p.reference_docname
			for p in event.get("event_participants", [])
			if p.reference_doctype == "User"
		}

		dirty = False
		for p in getattr(self, "participants", []):
			if p.user and p.user not in existing:
				event.append(
					"event_participants",
					{"reference_doctype": "User", "reference_docname": p.user},
				)
				dirty = True

		if dirty or not event_name:
			event.save(ignore_permissions=True)

	def _generate_room_name(self):
		"""Generate a unique room name from the meeting title."""
		clean_title = frappe.scrub(self.title).replace("_", "-")
		room_uuid = uuid.uuid4().hex
		return f"{clean_title}-{room_uuid}"

	def _generate_embed_html(self, settings):
		"""Generate the Jitsi iframe embed HTML. JWT is NOT embedded — generated fresh at join time."""
		domain = settings.jitsi_domain or "meet.jit.si"
		app_id = settings.app_id or ""

		if domain == "8x8.vc" and app_id:
			iframe_src = f"https://{domain}/{app_id}/{self.jitsi_room}"
		else:
			iframe_src = f"https://{domain}/{self.jitsi_room}"

		config_params = []
		if self.title:
			config_params.append(f"config.subject=%22{frappe.utils.quote(self.title)}%22")

		if settings.enable_waiting_room:
			config_params.append("config.enableLobbyChat=true")
			config_params.append("config.lobby.autoKnock=true")
			config_params.append("config.prejoinConfig.enabled=true")

		separator = "&" if "?" in iframe_src else "?"
		if config_params:
			iframe_src += separator + "&".join(config_params)

		return f'''<div style="display:flex;justify-content:center;padding:10px 0;">
	<iframe
		src="{iframe_src}"
		style="border:0;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,0.12);"
		width="100%"
		height="600"
		allow="camera;microphone;fullscreen;display-capture;autoplay;clipboard-write"
		allowfullscreen>
	</iframe>
</div>'''

	def _generate_jwt_token(self, settings, for_user=None):
		"""Generate a fresh JWT token on demand.

		FIX: removed the broken "pre-signed token" shortcut that returned any
		secret containing dots (e.g. base64) as-is without signing.
		Tokens are always signed properly via pyjwt.
		"""
		app_secret = settings.get_password("app_secret") if settings.app_secret else None
		if not app_secret:
			return None

		try:
			import jwt as pyjwt

			user = for_user or frappe.session.user
			now = int(time.time())
			buffer_secs = 30 * 60
			is_moderator = user in [self.owner, getattr(self, "created_by_user", "")]

			# FIX: Problem 3 - Clock Skew
			# Increase nbf buffer to 5 minutes (300s) to handle Jitsi servers with ahead clocks
			nbf = now - 300

			# FIX: Problem 1 & 2 - Late Joiners and Email Invite Tokens
			# Instead of 'now + duration', we use the scheduled end time.
			# This ensures the token is valid for the entire meeting duration regardless of when generated.
			if self.end_date:
				end_date = frappe.utils.get_datetime(self.end_date)
			elif self.meeting_date and self.duration:
				end_date = frappe.utils.add_to_date(self.meeting_date, minutes=self.duration)
			else:
				# Fallback for instant meetings without duration
				end_date = frappe.utils.add_to_date(now, minutes=self.duration or 60)
			
			end_ts = int(frappe.utils.get_datetime(end_date).timestamp())
			
			# Token expires at scheduled end + buffer, or at least 30m from now
			# (in case the meeting is long past or being joined very late)
			exp = max(end_ts + buffer_secs, now + buffer_secs)

			payload = {
				"aud": "jitsi",
				"iss": "chat",
				"iat": now,
				"exp": exp,
				"nbf": nbf,
				"sub": settings.app_id or "*",
				"room": self.jitsi_room or "*",
				"context": {
					"user": {
						"name": frappe.utils.get_fullname(user),
						"email": user,
						"moderator": is_moderator,
						"affiliation": "owner" if is_moderator else "member",
					},
					"features": {
						"recording": bool(settings.enable_recording),
						"livestreaming": False,
						"transcription": False,
					},
					"room": {"regex": False},
				},
			}

			if settings.enable_waiting_room and is_moderator:
				payload["context"]["room"]["lobby"] = True

			if "BEGIN RSA PRIVATE KEY" in app_secret or "BEGIN PRIVATE KEY" in app_secret:
				token = pyjwt.encode(
					payload, app_secret, algorithm="RS256", headers={"kid": settings.app_id}
				)
			else:
				token = pyjwt.encode(payload, app_secret, algorithm="HS256")

			return token
		except Exception as e:
			frappe.log_error(f"JWT generation failed: {e}", "Huddle Meeting JWT Error")
			return None

	def _get_jwt_token(self, settings):
		return self._generate_jwt_token(settings)

	def _send_email_invites(self, settings):
		"""Send email invitations to all participants."""
		if not settings.email_template:
			return

		try:
			email_template = frappe.get_doc("Email Template", settings.email_template)
		except frappe.DoesNotExistError:
			frappe.log_error(
				f"Email Template '{settings.email_template}' not found",
				"Huddle Meeting Email Error",
			)
			return

		for participant in self.participants:
			if not participant.email:
				continue

			try:
				join_url = f"{frappe.utils.get_url()}/huddle/join?meeting={self.name}"

				context = {
					"doc": self,
					"participant": participant,
					"meeting_url": join_url,
					"join_url": join_url,
					"host": frappe.utils.get_fullname(
						self.created_by_user or frappe.session.user
					),
				}

				subject = frappe.render_template(email_template.subject, context)
				message = frappe.render_template(
					email_template.response_
					if hasattr(email_template, "response_")
					else email_template.response,
					context,
				)

				ics_content = self._generate_ics()
				attachments = [
					{"fname": f"{self.name}_invite.ics", "fcontent": ics_content.encode("utf-8")}
				]

				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
					attachments=attachments,
				)

				participant.invite_status = "Pending"

			except Exception as e:
				frappe.log_error(
					f"Failed to send invite to {participant.email}: {e}",
					"Huddle Meeting Email Error",
				)

	def _generate_ics(self):
		"""Generate iCalendar text block for attachments."""
		from frappe_huddle.utils.calendar import generate_ics as gen_ics

		return gen_ics(self)

	def _notify_reschedule(self, old_doc):
		"""Notify participants about rescheduling."""
		settings = frappe.get_doc("Huddle Settings")
		if not settings.send_email_invite:
			return

		old_date = old_doc.meeting_date
		new_date = self.meeting_date
		old_duration = old_doc.duration
		new_duration = self.duration

		if settings.reschedule_email_template:
			try:
				template = frappe.get_doc("Email Template", settings.reschedule_email_template)
				join_url = f"{frappe.utils.get_url()}/huddle/join?meeting={self.name}"

				for participant in self.participants:
					if not participant.email:
						continue
					context = {
						"doc": self,
						"participant": participant,
						"old_date": frappe.utils.global_date_format(old_date),
						"old_time": frappe.utils.format_time(frappe.utils.get_time(old_date)),
						"new_date": frappe.utils.global_date_format(new_date),
						"new_time": frappe.utils.format_time(frappe.utils.get_time(new_date)),
						"old_duration": old_duration,
						"new_duration": new_duration,
						"join_url": join_url,
						"meeting_url": join_url,
						"host": frappe.utils.get_fullname(
							self.created_by_user or frappe.session.user
						),
					}
					subject = frappe.render_template(template.subject, context)
					message = frappe.render_template(
						template.response_
						if hasattr(template, "response_")
						else template.response,
						context,
					)
					ics_content = self._generate_ics()
					attachments = [
						{
							"fname": f"{self.name}_reschedule.ics",
							"fcontent": ics_content.encode("utf-8"),
						}
					]
					frappe.sendmail(
						recipients=[participant.email],
						subject=subject,
						message=message,
						reference_doctype=self.doctype,
						reference_name=self.name,
						attachments=attachments,
					)
				return
			except frappe.DoesNotExistError:
				pass

		subject = f"Huddle Rescheduled: {self.title}"
		join_url = f"{frappe.utils.get_url()}/huddle/join?meeting={self.name}"

		message = f"""
			<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px;">
				<h2 style="color: #3498db; margin: 0 0 16px;">Meeting Rescheduled</h2>
				<p style="color: #334155;">The huddle <b>{self.title}</b> has been rescheduled.</p>
				<table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
					<tr>
						<td style="padding: 12px 16px; background: #fff1f1; border-radius: 8px 0 0 8px; width: 50%;">
							<span style="font-size: 11px; color: #e74c3c; font-weight: 700; text-transform: uppercase;">Previous</span>
							<p style="margin: 6px 0 2px; font-weight: 600; text-decoration: line-through;">{frappe.utils.global_date_format(old_date)}</p>
							<p style="margin: 0; font-size: 13px; text-decoration: line-through;">{frappe.utils.format_time(frappe.utils.get_time(old_date))} · {old_duration} mins</p>
						</td>
						<td style="padding: 12px 16px; background: #ecfdf5; border-radius: 0 8px 8px 0; width: 50%;">
							<span style="font-size: 11px; color: #10b981; font-weight: 700; text-transform: uppercase;">New</span>
							<p style="margin: 6px 0 2px; font-weight: 600;">{frappe.utils.global_date_format(new_date)}</p>
							<p style="margin: 0; font-size: 13px;">{frappe.utils.format_time(frappe.utils.get_time(new_date))} · {self.duration} mins</p>
						</td>
					</tr>
				</table>
				<a href="{join_url}" style="background: #0ea5a0; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">Join Updated Meeting</a>
			</div>
		"""

		for participant in self.participants:
			if participant.email:
				ics_content = self._generate_ics()
				attachments = [
					{
						"fname": f"{self.name}_reschedule.ics",
						"fcontent": ics_content.encode("utf-8"),
					}
				]
				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
					attachments=attachments,
				)

	def _notify_cancellation(self):
		"""Notify participants about cancellation."""
		settings = frappe.get_doc("Huddle Settings")
		if not settings.send_email_invite:
			return

		if settings.cancellation_email_template:
			try:
				template = frappe.get_doc("Email Template", settings.cancellation_email_template)
				for participant in self.participants:
					if not participant.email:
						continue
					context = {
						"doc": self,
						"participant": participant,
						"host": frappe.utils.get_fullname(
							self.created_by_user or frappe.session.user
						),
					}
					subject = frappe.render_template(template.subject, context)
					message = frappe.render_template(
						template.response_
						if hasattr(template, "response_")
						else template.response,
						context,
					)
					frappe.sendmail(
						recipients=[participant.email],
						subject=subject,
						message=message,
						reference_doctype=self.doctype,
						reference_name=self.name,
					)
				return
			except frappe.DoesNotExistError:
				pass

		subject = f"Huddle Cancelled: {self.title}"
		message = f"""
			<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px;">
				<h2 style="color: #e74c3c; margin: 0 0 16px;">Meeting Cancelled</h2>
				<p style="color: #334155;">The huddle <b>{self.title}</b> scheduled for
					{frappe.utils.global_date_format(self.meeting_date)} at
					{frappe.utils.format_time(frappe.utils.get_time(self.meeting_date))} has been cancelled.</p>
			</div>
		"""

		for participant in self.participants:
			if participant.email:
				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
				)


@frappe.whitelist()
def get_meeting_details(meeting_name):
	# FIX: consistent tab indentation + save status update to DB
	doc = frappe.get_doc("Huddle Meeting", meeting_name)
	if doc.update_status():
		doc.db_set("status", doc.status, update_modified=False)
	return doc.as_dict()


@frappe.whitelist()
def join_meeting(meeting_name):
	"""Generate a fresh join URL with participant validation and fresh JWT.
	FIX: use targeted db_set instead of full .save() to avoid triggering
	before_save hooks (email sends, calendar sync) on every join.
	"""
	meeting = frappe.get_doc("Huddle Meeting", meeting_name)

	current_user = frappe.session.user
	is_owner = current_user in [meeting.owner, getattr(meeting, "created_by_user", "")]

	is_participant = False
	participant_row_name = None
	for p in meeting.participants:
		if p.user == current_user:
			is_participant = True
			participant_row_name = p.name
			break

	if not is_owner and not is_participant and "System Manager" not in frappe.get_roles():
		frappe.throw(
			"You are not authorized to join this meeting. You must be added to the participants list.",
			title="Access Denied",
		)

	settings = frappe.get_doc("Huddle Settings")
	domain = settings.jitsi_domain or "meet.jit.si"
	app_id = settings.app_id or ""

	if domain == "8x8.vc" and app_id:
		join_url = f"https://{domain}/{app_id}/{meeting.jitsi_room}"
	else:
		join_url = f"https://{domain}/{meeting.jitsi_room}"

	jwt_token = meeting._generate_jwt_token(settings, for_user=current_user)
	# FIX: JWT passed as URL fragment (#) instead of query param (?jwt=...)
	# so it never appears in server access logs or browser history
	if jwt_token:
		join_url += f"#{jwt_token}"

	config_params = []
	if settings.enable_waiting_room:
		config_params.append("config.prejoinConfig.enabled=true")
		if is_owner:
			config_params.append("config.lobby.autoKnock=false")

	if config_params:
		join_url += "?" + "&".join(config_params)

	# FIX: use targeted db_set — avoids triggering before_save/on_update hooks
	if is_participant and participant_row_name:
		frappe.db.set_value(
			"Huddle Participant",
			participant_row_name,
			{"joined": 1, "joined_at": frappe.utils.now()},
		)

	if meeting.status == "Scheduled":
		meeting.db_set("status", "In Progress", update_modified=False)

	return {"join_url": join_url}


@frappe.whitelist()
def join_meeting_page(meeting_name):
	"""Server-side endpoint for /huddle/join?meeting=<meeting-id>."""
	if frappe.session.user == "Guest":
		frappe.throw("Please log in to join this meeting.", frappe.AuthenticationError)

	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	current_user = frappe.session.user

	is_owner = current_user in [meeting.owner, getattr(meeting, "created_by_user", "")]
	is_participant = any(p.user == current_user for p in meeting.participants)
	is_admin = "System Manager" in frappe.get_roles()

	if not is_owner and not is_participant and not is_admin:
		frappe.throw("You are not authorized to join this meeting.", frappe.PermissionError)

	settings = frappe.get_doc("Huddle Settings")
	domain = settings.jitsi_domain or "meet.jit.si"
	app_id = settings.app_id or ""

	if domain == "8x8.vc" and app_id:
		jitsi_url = f"https://{domain}/{app_id}/{meeting.jitsi_room}"
	else:
		jitsi_url = f"https://{domain}/{meeting.jitsi_room}"

	jwt_token = meeting._generate_jwt_token(settings, for_user=current_user)
	# FIX: token in fragment, not query string
	if jwt_token:
		jitsi_url += f"#{jwt_token}"

	return {
		"meeting_name": meeting.name,
		"title": meeting.title,
		"status": meeting.status,
		"meeting_date": str(meeting.meeting_date),
		"duration": meeting.duration,
		"jitsi_url": jitsi_url,
		"jitsi_domain": domain,
		"jitsi_room": meeting.jitsi_room,
		"jwt_token": jwt_token,
		"is_moderator": is_owner,
		"user_name": frappe.utils.get_fullname(current_user),
		"user_email": current_user,
	}


@frappe.whitelist()
def resend_invites(meeting_name):
	"""Manual trigger to resend invites for a meeting."""
	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	settings = frappe.get_doc("Huddle Settings")
	meeting._send_email_invites(settings)
	# FIX: use db_set instead of save() to avoid triggering all hooks again
	frappe.db.set_value("Huddle Meeting", meeting_name, "modified", frappe.utils.now())
	return True


@frappe.whitelist()
def sync_all_statuses():
	"""Sync statuses for all active meetings based on current time."""
	meetings = frappe.get_all(
		"Huddle Meeting",
		filters={"status": ["in", ["Scheduled", "In Progress"]]},
		fields=["name"],
	)

	for m in meetings:
		doc = frappe.get_doc("Huddle Meeting", m.name)
		if doc.update_status():
			doc.db_set("status", doc.status, update_modified=False)

	# FIX: removed frappe.db.commit() — scheduler wraps each job in its own transaction
	cleanup_stale_presence()


def cleanup_stale_presence():
	"""Mark users as left if they haven't sent a heartbeat recently."""
	active_logs = frappe.get_all(
		"Huddle Attendance Log",
		filters={"leave_time": ("is", "not set")},
		fields=["name", "participant", "join_time"],
	)

	now_dt = frappe.utils.now_datetime()
	stale_threshold = frappe.utils.add_to_date(now_dt, seconds=-60)

	for log in active_logs:
		last_seen = frappe.cache().get_value(f"user_active:{log.participant}")
		if not last_seen or frappe.utils.get_datetime(last_seen) < stale_threshold:
			frappe.db.set_value("Huddle Attendance Log", log.name, "leave_time", now_dt)

			log_doc = frappe.get_doc("Huddle Attendance Log", log.name)
			# FIX: guard for None join_time (same fix as in webhook handler)
			if log_doc.join_time:
				duration = (now_dt - log_doc.join_time).total_seconds()
				frappe.db.set_value("Huddle Attendance Log", log.name, "duration", duration)


def send_meeting_reminders():
	"""Scheduler job: Send popup notifications and email reminders."""
	settings = frappe.get_doc("Huddle Settings")
	if not settings.enable_reminders:
		return

	reminder_mins = settings.reminder_minutes or 10
	now = frappe.utils.now_datetime()

	window_start = now
	window_end = frappe.utils.add_to_date(now, minutes=reminder_mins)

	upcoming = frappe.get_all(
		"Huddle Meeting",
		filters={
			"status": "Scheduled",
			"meeting_date": ["between", [str(window_start), str(window_end)]],
		},
		fields=["name", "title", "meeting_date", "duration", "created_by_user"],
	)

	for meeting_data in upcoming:
		reminder_key = f"huddle_reminder_sent:{meeting_data.name}"
		if frappe.cache().get_value(reminder_key):
			continue

		meeting = frappe.get_doc("Huddle Meeting", meeting_data.name)
		participants = meeting.get("participants", [])

		notify_users = set()
		for p in participants:
			if p.user:
				notify_users.add(p.user)
		if meeting.created_by_user:
			notify_users.add(meeting.created_by_user)

		time_left = frappe.utils.time_diff_in_seconds(meeting.meeting_date, now)
		mins_left = max(1, int(time_left / 60))
		join_url = f"/huddle/join?meeting={meeting.name}"

		for user in notify_users:
			try:
				notification = frappe.new_doc("Notification Log")
				notification.for_user = user
				notification.from_user = meeting.created_by_user or meeting.owner
				notification.type = "Alert"
				notification.subject = f"Huddle starting in {mins_left} min: {meeting.title}"
				notification.document_type = "Huddle Meeting"
				notification.document_name = meeting.name
				notification.email_content = f"""
					<p>Your meeting <b>{meeting.title}</b> starts in <b>{mins_left} minutes</b>.</p>
					<p><a href="{join_url}">Click here to join</a></p>
				"""
				notification.insert(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(
					f"Reminder notification failed for {user}: {e}", "Huddle Reminder Error"
				)

		if settings.send_reminder_email:
			_send_reminder_emails(meeting, settings, mins_left, join_url)

		frappe.cache().set_value(reminder_key, 1, expires_in_sec=3600)
	# FIX: removed frappe.db.commit() — scheduler handles this


def _send_reminder_emails(meeting, settings, mins_left, join_url):
	"""Send email reminders for an upcoming meeting."""
	full_join_url = f"{frappe.utils.get_url()}{join_url}"

	if settings.reminder_email_template:
		try:
			template = frappe.get_doc("Email Template", settings.reminder_email_template)
			for p in meeting.participants:
				if not p.email:
					continue
				context = {
					"doc": meeting,
					"participant": p,
					"mins_left": mins_left,
					"join_url": full_join_url,
					"host": frappe.utils.get_fullname(meeting.created_by_user or meeting.owner),
				}
				subject = frappe.render_template(template.subject, context)
				message = frappe.render_template(
					template.response_
					if hasattr(template, "response_")
					else template.response,
					context,
				)
				frappe.sendmail(
					recipients=[p.email],
					subject=subject,
					message=message,
					reference_doctype="Huddle Meeting",
					reference_name=meeting.name,
				)
			return
		except frappe.DoesNotExistError:
			pass

	subject = f"Reminder: {meeting.title} starts in {mins_left} min"
	message = f"""
		<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px;">
			<h2 style="color: #f59e0b; margin: 0 0 16px;">Meeting Reminder</h2>
			<p style="color: #334155;">Your huddle <b>{meeting.title}</b> starts in <b>{mins_left} minutes</b>.</p>
			<div style="background: #f9f9f9; padding: 16px; border-radius: 10px; margin: 20px 0;">
				<p style="margin: 4px 0; font-size: 14px;"><b>Date:</b> {frappe.utils.global_date_format(meeting.meeting_date)}</p>
				<p style="margin: 4px 0; font-size: 14px;"><b>Duration:</b> {meeting.duration} minutes</p>
			</div>
			<a href="{full_join_url}" style="background: #0ea5a0; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block;">Join Meeting Now</a>
		</div>
	"""

	for p in meeting.participants:
		if p.email:
			frappe.sendmail(
				recipients=[p.email],
				subject=subject,
				message=message,
				reference_doctype="Huddle Meeting",
				reference_name=meeting.name,
			)


@frappe.whitelist()
def update_presence(meeting_name, session_id):
	"""Frontend heartbeat to keep attendance active."""
	if frappe.session.user == "Guest":
		return

	existing_log = frappe.db.get_value(
		"Huddle Attendance Log",
		{"session_id": session_id, "leave_time": ("is", "not set")},
		"name",
	)

	if not existing_log:
		doc = frappe.get_doc(
			{
				"doctype": "Huddle Attendance Log",
				"meeting": meeting_name,
				"participant": frappe.session.user,
				"join_time": frappe.utils.now_datetime(),
				"session_id": session_id,
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.cache().set_value(
		f"user_active:{frappe.session.user}", frappe.utils.now_datetime()
	)


@frappe.whitelist()
def get_events(doctype, start, end, filters=None):
	"""Custom get_events for calendar."""
	from frappe.desk.reportview import get_filters_cond

	conditions = get_filters_cond(doctype, filters, [])

	meetings = frappe.db.sql(
		f"""
		SELECT
			name, title, meeting_date, end_date, duration, status
		FROM
			`tabHuddle Meeting`
		WHERE
			(meeting_date BETWEEN %s AND %s
			 OR COALESCE(end_date, DATE_ADD(meeting_date, INTERVAL 60 MINUTE)) BETWEEN %s AND %s)
			{conditions}
	""",
		(start, end, start, end),
		as_dict=True,
	)

	now = frappe.utils.get_datetime(frappe.utils.now())

	# FIX: batch-fetch all participants for the visible meetings in one query
	meeting_names = [m.name for m in meetings]
	participants_raw = []
	if meeting_names:
		participants_raw = frappe.get_all(
			"Huddle Participant",
			filters={"parent": ["in", meeting_names]},
			fields=["parent", "full_name"],
		)
	participants_by_meeting = {}
	for p in participants_raw:
		participants_by_meeting.setdefault(p.parent, []).append(p.full_name)

	for m in meetings:
		m_start = frappe.utils.get_datetime(m.meeting_date)
		m_end = m.end_date or frappe.utils.add_to_date(m.meeting_date, minutes=m.duration or 60)
		m_end = frappe.utils.get_datetime(m_end)

		old_status = m.status
		if m.status != "Cancelled":
			if now > m_end:
				m.status = "Completed"
			elif now >= m_start:
				m.status = "In Progress"
			else:
				m.status = "Scheduled"

			if m.status != old_status:
				frappe.db.set_value(
					"Huddle Meeting", m.name, "status", m.status, update_modified=False
				)

		names = participants_by_meeting.get(m.name, [])
		m.participant_list = ", ".join(filter(None, names))
		m.start = m.meeting_date
		m.end = m.end_date or frappe.utils.add_to_date(m.meeting_date, minutes=m.duration or 60)
		m.all_day = 0

	return meetings


def sync_to_huddle_meeting(doc, method):
	"""Reverse sync from Event to Huddle Meeting."""
	if doc.reference_doctype == "Huddle Meeting" and doc.reference_docname:
		if getattr(doc.flags, "from_huddle", False):
			return

		try:
			meeting = frappe.get_doc("Huddle Meeting", doc.reference_docname)
			meeting.flags.from_event = True
			meeting.title = doc.subject
			meeting.meeting_date = doc.starts_on

			if doc.ends_on and doc.starts_on:
				diff = frappe.utils.time_diff_in_seconds(doc.ends_on, doc.starts_on)
				meeting.duration = int(diff / 60)

			existing_users = [p.user for p in meeting.get("participants", []) if p.user]
			for event_part in doc.get("event_participants", []):
				if (
					event_part.reference_doctype == "User"
					and event_part.reference_docname not in existing_users
				):
					meeting.append(
						"participants",
						{
							"user": event_part.reference_docname,
							"email": event_part.reference_docname,
							"full_name": frappe.db.get_value(
								"User", event_part.reference_docname, "full_name"
							),
						},
					)

			meeting.save(ignore_permissions=True)
		except Exception:
			# FIX: wrap in try/except so a bad Event save never corrupts a Huddle Meeting
			frappe.log_error(frappe.get_traceback(), "Huddle: reverse sync from Event failed")
