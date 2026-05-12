# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import uuid
import time
import json
import base64


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

		# For 8x8.vc JaaS, the URL format is: https://8x8.vc/{app_id}/{room_name}
		# For self-hosted or meet.jit.si: https://{domain}/{room_name}
		if domain == "8x8.vc" and app_id:
			self.jitsi_url = f"https://{domain}/{app_id}/{self.jitsi_room}"
		else:
			self.jitsi_url = f"https://{domain}/{self.jitsi_room}"

		# Generate the embed HTML
		self.jitsi_embed = self._generate_embed_html(settings)

		# Calculate end date
		if self.meeting_date and self.duration:
			self.end_date = frappe.utils.add_to_date(self.meeting_date, minutes=self.duration)
		
		# Check for reschedule/cancellation notifications
		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc:
				if old_doc.meeting_date != self.meeting_date:
					# Rescheduled — pass the old date for comparison
					self._notify_reschedule(old_doc)
				elif old_doc.status != self.status and self.status == "Cancelled":
					self._notify_cancellation()

		# Auto-update status if past end date
		self.update_status()

	def _validate_duration(self):
		"""Issue #5: Enforce default duration limits from Huddle Settings."""
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
					indicator="orange"
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
		# Create initial Frappe Event
		self.sync_frappe_event()
		settings = frappe.get_doc("Huddle Settings")
		if settings.send_email_invite and self.participants:
			self._send_email_invites(settings)

	def on_update(self):
		"""Keep Frappe Event synced with this Huddle Meeting."""
		if not self.is_new():
			self.sync_frappe_event()

	def sync_frappe_event(self):
		"""Create or update a standard Frappe Event so it appears in the system calendar."""
		if getattr(self, "flags", {}).get("from_event"):
			return # Avoid circular sync

		event_name = frappe.db.get_value("Event", {"reference_doctype": "Huddle Meeting", "reference_docname": self.name}, "name")
		
		# Clean up if cancelled
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
		event.ends_on = self.end_date or frappe.utils.add_to_date(self.meeting_date, minutes=self.duration or 60)
		# Issue #6: Link to the Frappe join page, NOT directly to Jitsi
		join_url = f"/huddle/join?meeting={self.name}"
		event.description = f"Video Meeting. <a href='{join_url}'>Join Huddle</a>"
		event.event_type = "Private"
		event.status = "Open"
		event.color = "#0ea5a0"
		
		# Set flag to avoid circular logic
		event.flags.from_huddle = True
		if not event_name:
			event.insert(ignore_permissions=True)
		
		# Safely sync participants
		existing = {p.reference_docname for p in event.get("event_participants", []) if p.reference_doctype == "User"}
		
		dirty = False
		for p in getattr(self, "participants", []):
			if p.user and p.user not in existing:
				event.append("event_participants", {
					"reference_doctype": "User",
					"reference_docname": p.user
				})
				dirty = True
				
		if dirty or not event_name:
			event.save(ignore_permissions=True)

	def _generate_room_name(self):
		"""Generate a unique room name from the meeting title."""
		clean_title = frappe.scrub(self.title).replace("_", "-")
		room_uuid = uuid.uuid4().hex
		return f"{clean_title}-{room_uuid}"

	def _generate_embed_html(self, settings):
		"""Generate the Jitsi iframe embed HTML."""
		domain = settings.jitsi_domain or "meet.jit.si"
		app_id = settings.app_id or ""

		if domain == "8x8.vc" and app_id:
			iframe_src = f"https://{domain}/{app_id}/{self.jitsi_room}"
		else:
			iframe_src = f"https://{domain}/{self.jitsi_room}"

		# JWT is NOT embedded here — it's generated fresh at join time (Issue #4)
		# Add config params
		config_params = []
		if self.title:
			config_params.append(f"config.subject=%22{frappe.utils.quote(self.title)}%22")
		
		# Issue #2: Enable lobby mode for unauthorized participant protection
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
		"""Issue #4: Generate a fresh JWT token on demand.
		
		Tokens are generated at join-time with expiry = meeting_duration + 30min buffer.
		This avoids the 2-hour stale token problem entirely.
		"""
		app_secret = settings.get_password("app_secret") if settings.app_secret else None
		if not app_secret:
			return None

		# Check if the stored secret is itself a pre-signed JWT (has 3 dot-separated parts)
		parts = app_secret.split(".")
		if len(parts) == 3:
			return app_secret

		try:
			import jwt as pyjwt

			user = for_user or frappe.session.user
			now = int(time.time())
			
			# Calculate generous expiry: from NOW + meeting duration + 30 min buffer
			# This ensures the token is always fresh (generated at join time)
			duration_secs = (self.duration or 60) * 60
			buffer_secs = 30 * 60  # 30 minutes buffer (increased from 5)
			
			# Determine if user is moderator
			is_moderator = user in [self.owner, getattr(self, "created_by_user", "")]
			
			payload = {
				"aud": "jitsi",
				"iss": "chat",
				"iat": now,
				"exp": now + duration_secs + buffer_secs,  # From NOW, not meeting_start
				"nbf": now - 60,  # Allow 1 min clock skew
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
					"room": {
						"regex": False,
					}
				},
			}

			# Issue #2: If lobby/waiting room is enabled, set lobby config in JWT
			if settings.enable_waiting_room and is_moderator:
				payload["context"]["room"]["lobby"] = True

			# Determine algorithm from key format
			if "BEGIN RSA PRIVATE KEY" in app_secret or "BEGIN PRIVATE KEY" in app_secret:
				token = pyjwt.encode(payload, app_secret, algorithm="RS256",
					headers={"kid": settings.app_id})
			else:
				token = pyjwt.encode(payload, app_secret, algorithm="HS256")

			return token
		except Exception as e:
			frappe.log_error(f"JWT generation failed: {e}", "Huddle Meeting JWT Error")
			return None

	# Keep backward-compatible alias
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
				"Huddle Meeting Email Error"
			)
			return

		for participant in self.participants:
			if not participant.email:
				continue

			try:
				# Issue #6: Use Frappe join route, not direct Jitsi URL
				join_url = f"{frappe.utils.get_url()}/huddle/join?meeting={self.name}"
				
				# Render the email template with meeting context
				context = {
					"doc": self,
					"participant": participant,
					"meeting_url": join_url,
					"join_url": join_url,
					"host": frappe.utils.get_fullname(self.created_by_user or frappe.session.user),
				}

				subject = frappe.render_template(email_template.subject, context)
				message = frappe.render_template(
					email_template.response_ if hasattr(email_template, 'response_') else email_template.response,
					context
				)

				# generate ICS attachment for calendar integrations
				ics_content = self._generate_ics()
				attachments = [{
					"fname": f"{self.name}_invite.ics",
					"fcontent": ics_content.encode('utf-8')
				}]

				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
					attachments=attachments
				)

				# Update invite status
				participant.invite_status = "Pending"

			except Exception as e:
				frappe.log_error(
					f"Failed to send invite to {participant.email}: {e}",
					"Huddle Meeting Email Error"
				)

	def _generate_ics(self):
		"""Generate iCalendar text block for attachments."""
		from frappe_huddle.utils.calendar import generate_ics as gen_ics
		return gen_ics(self)

	def _notify_reschedule(self, old_doc):
		"""Issue #3: Notify participants about rescheduling with old vs new date comparison."""
		settings = frappe.get_doc("Huddle Settings")
		if not settings.send_email_invite:
			return

		old_date = old_doc.meeting_date
		new_date = self.meeting_date
		old_duration = old_doc.duration
		new_duration = self.duration

		# Try to use configured reschedule template first
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
						"host": frappe.utils.get_fullname(self.created_by_user or frappe.session.user),
					}
					subject = frappe.render_template(template.subject, context)
					message = frappe.render_template(
						template.response_ if hasattr(template, 'response_') else template.response,
						context
					)

					# Attach updated ICS
					ics_content = self._generate_ics()
					attachments = [{
						"fname": f"{self.name}_reschedule.ics",
						"fcontent": ics_content.encode('utf-8')
					}]

					frappe.sendmail(
						recipients=[participant.email],
						subject=subject,
						message=message,
						reference_doctype=self.doctype,
						reference_name=self.name,
						attachments=attachments
					)
				return
			except frappe.DoesNotExistError:
				pass  # Fall through to default template

		# Default inline reschedule template with old vs new comparison
		subject = f"Huddle Rescheduled: {self.title}"
		join_url = f"{frappe.utils.get_url()}/huddle/join?meeting={self.name}"
		
		message = f"""
			<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
				<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
					<div style="width: 40px; height: 40px; background: #0ea5a0; border-radius: 10px; display: flex; align-items: center; justify-content: center;">
						<span style="color: #fff; font-size: 20px;">📅</span>
					</div>
					<h2 style="color: #3498db; margin: 0; font-size: 22px;">Meeting Rescheduled</h2>
				</div>
				<p style="color: #334155; font-size: 15px;">The huddle <b>{self.title}</b> has been rescheduled.</p>
				
				<table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
					<tr>
						<td style="padding: 12px 16px; background: #fff1f1; border-radius: 8px 0 0 8px; width: 50%;">
							<span style="font-size: 11px; color: #e74c3c; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Previous Schedule</span>
							<p style="margin: 6px 0 2px; font-size: 15px; font-weight: 600; color: #334155; text-decoration: line-through;">{frappe.utils.global_date_format(old_date)}</p>
							<p style="margin: 0; font-size: 13px; color: #64748b; text-decoration: line-through;">{frappe.utils.format_time(frappe.utils.get_time(old_date))} · {old_duration} mins</p>
						</td>
						<td style="padding: 12px 16px; background: #ecfdf5; border-radius: 0 8px 8px 0; width: 50%;">
							<span style="font-size: 11px; color: #10b981; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">New Schedule</span>
							<p style="margin: 6px 0 2px; font-size: 15px; font-weight: 600; color: #334155;">{frappe.utils.global_date_format(new_date)}</p>
							<p style="margin: 0; font-size: 13px; color: #64748b;">{frappe.utils.format_time(frappe.utils.get_time(new_date))} · {self.duration} mins</p>
						</td>
					</tr>
				</table>

				<p style="margin-bottom: 25px; color: #64748b; font-size: 14px;">Please update your calendar accordingly.</p>
				<a href="{join_url}" style="background: #0ea5a0; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; font-size: 14px;">Join Updated Meeting</a>
			</div>
		"""

		for participant in self.participants:
			if participant.email:
				ics_content = self._generate_ics()
				attachments = [{
					"fname": f"{self.name}_reschedule.ics",
					"fcontent": ics_content.encode('utf-8')
				}]
				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
					attachments=attachments
				)

	def _notify_cancellation(self):
		"""Notify participants about cancellation with optional template support."""
		settings = frappe.get_doc("Huddle Settings")
		if not settings.send_email_invite:
			return

		# Try configured cancellation template
		if settings.cancellation_email_template:
			try:
				template = frappe.get_doc("Email Template", settings.cancellation_email_template)
				for participant in self.participants:
					if not participant.email:
						continue
					context = {
						"doc": self,
						"participant": participant,
						"host": frappe.utils.get_fullname(self.created_by_user or frappe.session.user),
					}
					subject = frappe.render_template(template.subject, context)
					message = frappe.render_template(
						template.response_ if hasattr(template, 'response_') else template.response,
						context
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

		# Default inline cancellation template
		subject = f"Huddle Cancelled: {self.title}"
		message = f"""
			<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
				<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
					<div style="width: 40px; height: 40px; background: #e74c3c; border-radius: 10px; display: flex; align-items: center; justify-content: center;">
						<span style="color: #fff; font-size: 20px;">✕</span>
					</div>
					<h2 style="color: #e74c3c; margin: 0; font-size: 22px;">Meeting Cancelled</h2>
				</div>
				<p style="color: #334155; font-size: 15px;">The huddle <b>{self.title}</b> scheduled for
					{frappe.utils.global_date_format(self.meeting_date)} at
					{frappe.utils.format_time(frappe.utils.get_time(self.meeting_date))} has been cancelled.</p>
				<p style="color: #64748b; font-size: 14px; margin-top: 16px;">We apologize for the inconvenience.</p>
			</div>
		"""

		for participant in self.participants:
			if participant.email:
				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name
				)


@frappe.whitelist()
def get_meeting_details(meeting_name):
    doc = frappe.get_doc("Huddle Meeting", meeting_name)
    doc.update_status()
    return doc.as_dict()
	
@frappe.whitelist()
def join_meeting(meeting_name):
	"""Issue #2 + #4: Generate a fresh join URL with participant validation and fresh JWT."""
	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	
	# ──── Issue #2: Strict participant validation ────
	current_user = frappe.session.user
	is_owner = current_user in [meeting.owner, getattr(meeting, "created_by_user", "")]
	
	is_participant = False
	for p in meeting.participants:
		if p.user == current_user:
			is_participant = True
			break
			
	if not is_owner and not is_participant and "System Manager" not in frappe.get_roles():
		frappe.throw(
			"You are not authorized to join this meeting. You must be added to the participants list.",
			title="Access Denied"
		)

	settings = frappe.get_doc("Huddle Settings")
	domain = settings.jitsi_domain or "meet.jit.si"
	app_id = settings.app_id or ""

	# Build base URL
	if domain == "8x8.vc" and app_id:
		join_url = f"https://{domain}/{app_id}/{meeting.jitsi_room}"
	else:
		join_url = f"https://{domain}/{meeting.jitsi_room}"

	# ──── Issue #4: Fresh JWT generated NOW, not from stored/stale token ────
	jwt_token = meeting._generate_jwt_token(settings, for_user=current_user)
	if jwt_token:
		join_url += f"?jwt={jwt_token}"

	# ──── Issue #2: Add lobby/waiting room config params ────
	config_params = []
	if settings.enable_waiting_room:
		config_params.append("config.prejoinConfig.enabled=true")
		if is_owner:
			config_params.append("config.lobby.autoKnock=false")

	if config_params:
		separator = "&" if "?" in join_url else "?"
		join_url += separator + "&".join(config_params)

	# Mark participant as joined
	if is_participant:
		for p in meeting.participants:
			if p.user == current_user:
				p.joined = 1
				p.joined_at = frappe.utils.now()
				break
				
	# If someone joins, and it is still "Scheduled", mark as "In Progress"
	if meeting.status == "Scheduled":
		meeting.status = "In Progress"
		
	meeting.save(ignore_permissions=True)

	return {"join_url": join_url}


@frappe.whitelist()
def join_meeting_page(meeting_name):
	"""Issue #6: Server-side endpoint for /huddle/join?meeting=<meeting-id>.
	Validates the user, generates a fresh JWT, and returns meeting data
	for the join page to render inside Frappe.
	"""
	if frappe.session.user == "Guest":
		frappe.throw("Please log in to join this meeting.", frappe.AuthenticationError)

	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	current_user = frappe.session.user
	
	# Participant validation
	is_owner = current_user in [meeting.owner, getattr(meeting, "created_by_user", "")]
	is_participant = any(p.user == current_user for p in meeting.participants)
	is_admin = "System Manager" in frappe.get_roles()

	if not is_owner and not is_participant and not is_admin:
		frappe.throw("You are not authorized to join this meeting.", frappe.PermissionError)

	settings = frappe.get_doc("Huddle Settings")
	domain = settings.jitsi_domain or "meet.jit.si"
	app_id = settings.app_id or ""

	# Build Jitsi URL with fresh JWT
	if domain == "8x8.vc" and app_id:
		jitsi_url = f"https://{domain}/{app_id}/{meeting.jitsi_room}"
	else:
		jitsi_url = f"https://{domain}/{meeting.jitsi_room}"

	jwt_token = meeting._generate_jwt_token(settings, for_user=current_user)
	if jwt_token:
		jitsi_url += f"?jwt={jwt_token}"

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
	meeting.save(ignore_permissions=True)
	return True


@frappe.whitelist()
def sync_all_statuses():
	"""Sync statuses for all active meetings based on current time.
	Used as a fallback for webhooks."""
	now = frappe.utils.now()

	# Get all meetings that are Scheduled or In Progress
	meetings = frappe.get_all(
		"Huddle Meeting", 
		filters={"status": ["in", ["Scheduled", "In Progress"]]},
		fields=["name"]
	)

	for m in meetings:
		doc = frappe.get_doc("Huddle Meeting", m.name)
		if doc.update_status():
			doc.db_set("status", doc.status, update_modified=False)

	# Cleanup stale presence logs
	cleanup_stale_presence()


def cleanup_stale_presence():
	"""Mark users as left if they haven't sent a heartbeat recently."""
	active_logs = frappe.get_all(
		"Huddle Attendance Log",
		filters={"leave_time": ("is", "not set")},
		fields=["name", "participant", "join_time"]
	)
	
	now_dt = frappe.utils.now_datetime()
	stale_threshold = frappe.utils.add_to_date(now_dt, seconds=-60)
	
	for log in active_logs:
		last_seen = frappe.cache().get_value(f"user_active:{log.participant}")
		if not last_seen or frappe.utils.get_datetime(last_seen) < stale_threshold:
			frappe.db.set_value("Huddle Attendance Log", log.name, "leave_time", now_dt)
			
			log_doc = frappe.get_doc("Huddle Attendance Log", log.name)
			if log_doc.join_time:
				duration = (now_dt - log_doc.join_time).total_seconds()
				frappe.db.set_value("Huddle Attendance Log", log.name, "duration", duration)


# ──── Issue #1: Meeting Reminder System ────

def send_meeting_reminders():
	"""Scheduler job: Send popup notifications and optional email reminders
	for meetings starting within the configured reminder window.
	
	Registered in hooks.py as a cron job running every minute.
	"""
	settings = frappe.get_doc("Huddle Settings")
	if not settings.enable_reminders:
		return

	reminder_mins = settings.reminder_minutes or 10
	now = frappe.utils.now_datetime()
	
	# Window: meetings starting between NOW and NOW + reminder_mins
	window_start = now
	window_end = frappe.utils.add_to_date(now, minutes=reminder_mins)

	upcoming = frappe.get_all(
		"Huddle Meeting",
		filters={
			"status": "Scheduled",
			"meeting_date": ["between", [str(window_start), str(window_end)]],
		},
		fields=["name", "title", "meeting_date", "duration", "created_by_user"]
	)

	for meeting_data in upcoming:
		# Avoid duplicate reminders — check cache key
		reminder_key = f"huddle_reminder_sent:{meeting_data.name}"
		if frappe.cache().get_value(reminder_key):
			continue

		meeting = frappe.get_doc("Huddle Meeting", meeting_data.name)
		participants = meeting.get("participants", [])
		
		# Collect all users to notify (participants + creator)
		notify_users = set()
		for p in participants:
			if p.user:
				notify_users.add(p.user)
		if meeting.created_by_user:
			notify_users.add(meeting.created_by_user)

		time_left = frappe.utils.time_diff_in_seconds(
			meeting.meeting_date, now
		)
		mins_left = max(1, int(time_left / 60))
		join_url = f"/huddle/join?meeting={meeting.name}"

		# Send Frappe System Notification (popup)
		for user in notify_users:
			try:
				notification = frappe.new_doc("Notification Log")
				notification.for_user = user
				notification.from_user = meeting.created_by_user or meeting.owner
				notification.type = "Alert"
				notification.subject = f"🔔 Huddle starting in {mins_left} min: {meeting.title}"
				notification.document_type = "Huddle Meeting"
				notification.document_name = meeting.name
				notification.email_content = f"""
					<p>Your meeting <b>{meeting.title}</b> starts in <b>{mins_left} minutes</b>.</p>
					<p><a href="{join_url}">Click here to join</a></p>
				"""
				notification.insert(ignore_permissions=True)
			except Exception as e:
				frappe.log_error(f"Reminder notification failed for {user}: {e}", "Huddle Reminder Error")

		# Send email reminder if configured
		if settings.send_reminder_email:
			_send_reminder_emails(meeting, settings, mins_left, join_url)

		# Mark reminder as sent (expires in 1 hour)
		frappe.cache().set_value(reminder_key, 1, expires_in_sec=3600)
	
	frappe.db.commit()


def _send_reminder_emails(meeting, settings, mins_left, join_url):
	"""Send email reminders for an upcoming meeting."""
	full_join_url = f"{frappe.utils.get_url()}{join_url}"
	
	# Try configured template
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
					template.response_ if hasattr(template, 'response_') else template.response,
					context
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

	# Default reminder email
	subject = f"⏰ Reminder: {meeting.title} starts in {mins_left} min"
	message = f"""
		<div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 16px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
			<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
				<div style="width: 40px; height: 40px; background: #f59e0b; border-radius: 10px; display: flex; align-items: center; justify-content: center;">
					<span style="color: #fff; font-size: 20px;">⏰</span>
				</div>
				<h2 style="color: #f59e0b; margin: 0; font-size: 22px;">Meeting Reminder</h2>
			</div>
			<p style="color: #334155; font-size: 15px;">Your huddle <b>{meeting.title}</b> starts in <b>{mins_left} minutes</b>.</p>
			<div style="background: #f9f9f9; padding: 16px; border-radius: 10px; margin: 20px 0;">
				<p style="margin: 4px 0; font-size: 14px; color: #334155;"><b>Date:</b> {frappe.utils.global_date_format(meeting.meeting_date)}</p>
				<p style="margin: 4px 0; font-size: 14px; color: #334155;"><b>Time:</b> {frappe.utils.format_time(frappe.utils.get_time(meeting.meeting_date))}</p>
				<p style="margin: 4px 0; font-size: 14px; color: #334155;"><b>Duration:</b> {meeting.duration} minutes</p>
			</div>
			<a href="{full_join_url}" style="background: #0ea5a0; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; display: inline-block; font-size: 14px;">Join Meeting Now</a>
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
		
	# Ensure there's an active attendance log
	existing_log = frappe.db.get_value(
		"Huddle Attendance Log",
		{"session_id": session_id, "leave_time": ("is", "not set")},
		"name"
	)
	
	if not existing_log:
		doc = frappe.get_doc({
			"doctype": "Huddle Attendance Log",
			"meeting": meeting_name,
			"participant": frappe.session.user,
			"join_time": frappe.utils.now_datetime(),
			"session_id": session_id
		})
		doc.insert(ignore_permissions=True)
	
	# Update heartbeat timestamp
	frappe.cache().set_value(f"user_active:{frappe.session.user}", frappe.utils.now_datetime())


@frappe.whitelist()
def get_events(doctype, start, end, filters=None):
	"""Custom get_events for calendar to include participants and rich tooltip data."""
	from frappe.desk.reportview import get_filters_cond
	
	conditions = get_filters_cond(doctype, filters, [])
	
	meetings = frappe.db.sql(f"""
		SELECT 
			name, title, meeting_date, end_date, duration, status
		FROM 
			`tabHuddle Meeting`
		WHERE 
			(meeting_date BETWEEN %s AND %s 
			 OR COALESCE(end_date, DATE_ADD(meeting_date, INTERVAL 60 MINUTE)) BETWEEN %s AND %s)
			{conditions}
	""", (start, end, start, end), as_dict=True)
	
	now = frappe.utils.get_datetime(frappe.utils.now())
	
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
				frappe.db.set_value("Huddle Meeting", m.name, "status", m.status, update_modified=False)

		participants = frappe.db.get_all("Huddle Participant", 
			filters={"parent": m.name}, 
			fields=["full_name"]
		)
		participant_names = ", ".join([p.full_name for p in participants if p.full_name])
		
		m.start = m.meeting_date
		m.end = m.end_date or frappe.utils.add_to_date(m.meeting_date, minutes=m.duration or 60)
		m.participant_list = participant_names
		m.all_day = 0
		
	return meetings

def sync_to_huddle_meeting(doc, method):
	"""Reverse sync from Event to Huddle Meeting."""
	if doc.reference_doctype == "Huddle Meeting" and doc.reference_docname:
		if getattr(doc.flags, "from_huddle", False):
			return
		
		meeting = frappe.get_doc("Huddle Meeting", doc.reference_docname)
		meeting.flags.from_event = True
		meeting.title = doc.subject
		meeting.meeting_date = doc.starts_on
		
		if doc.ends_on and doc.starts_on:
			diff = frappe.utils.time_diff_in_seconds(doc.ends_on, doc.starts_on)
			meeting.duration = int(diff / 60)
		
		existing_users = [p.user for p in meeting.get("participants", []) if p.user]
		for event_part in doc.get("event_participants", []):
			if event_part.reference_doctype == "User" and event_part.reference_docname not in existing_users:
				meeting.append("participants", {
					"user": event_part.reference_docname,
					"email": event_part.reference_docname,
					"full_name": frappe.db.get_value("User", event_part.reference_docname, "full_name")
				})
		
		meeting.save(ignore_permissions=True)
