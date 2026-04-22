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
					# Rescheduled
					self._notify_status_change("Rescheduled")
				elif old_doc.status != self.status and self.status == "Cancelled":
					# Cancelled
					self._notify_status_change("Cancelled")

		# Auto-update status if past end date
		self.update_status()

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
		settings = frappe.get_doc("Huddle Settings")
		if settings.send_email_invite and self.participants:
			self._send_email_invites(settings)

	def _generate_room_name(self):
		"""Generate a unique room name from the meeting title."""
		# Create a clean room name: title-based + short UUID for uniqueness
		clean_title = frappe.scrub(self.title).replace("_", "-")
		short_id = uuid.uuid4().hex[:8]
		return f"{clean_title}-{short_id}"

	def _generate_embed_html(self, settings):
		"""Generate the Jitsi iframe embed HTML."""
		domain = settings.jitsi_domain or "meet.jit.si"
		app_id = settings.app_id or ""

		# Build the Jitsi Meet URL for iframe
		if domain == "8x8.vc" and app_id:
			iframe_src = f"https://{domain}/{app_id}/{self.jitsi_room}"
		else:
			iframe_src = f"https://{domain}/{self.jitsi_room}"

		# Add JWT token if available
		jwt_token = self._get_jwt_token(settings)
		if jwt_token:
			iframe_src += f"?jwt={jwt_token}"

		# Add config params
		config_params = []
		if self.title:
			config_params.append(f"config.subject=%22{frappe.utils.quote(self.title)}%22")
		if settings.enable_waiting_room:
			config_params.append("config.enableLobbyChat=true")

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

	def _get_jwt_token(self, settings):
		"""Get or generate a JWT token for Jitsi authentication."""
		app_secret = settings.get_password("app_secret") if settings.app_secret else None
		if not app_secret:
			return None

		# Check if the stored secret is itself a pre-signed JWT (has 3 dot-separated parts)
		parts = app_secret.split(".")
		if len(parts) == 3:
			# It's a pre-signed JWT token — use it directly
			return app_secret

		# Otherwise, treat it as a signing key and generate a new JWT
		try:
			import jwt as pyjwt

			now = int(time.time())
			payload = {
				"aud": "jitsi",
				"iss": "chat",
				"iat": now,
				"exp": now + (self.duration or 60) * 60,  # Token expires after meeting duration
				"nbf": now - 5,
				"sub": settings.app_id or "*",
				"room": self.jitsi_room or "*",
				"context": {
					"user": {
						"name": frappe.utils.get_fullname(frappe.session.user),
						"email": frappe.session.user,
						"moderator": True,
					},
					"features": {
						"recording": bool(settings.enable_recording),
						"livestreaming": False,
						"transcription": False,
					},
				},
			}

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
				# Render the email template with meeting context
				context = {
					"doc": self,
					"participant": participant,
					"meeting_url": self.jitsi_url,
					"host": frappe.utils.get_fullname(self.created_by_user or frappe.session.user),
				}

				subject = frappe.render_template(email_template.subject, context)
				message = frappe.render_template(
					email_template.response_ if hasattr(email_template, 'response_') else email_template.response,
					context
				)

				frappe.sendmail(
					recipients=[participant.email],
					subject=subject,
					message=message,
					reference_doctype=self.doctype,
					reference_name=self.name,
				)

				# Update invite status
				participant.invite_status = "Pending"

			except Exception as e:
				frappe.log_error(
					f"Failed to send invite to {participant.email}: {e}",
					"Huddle Meeting Email Error"
				)

	def _notify_status_change(self, change_type):
		"""Notify participants about rescheduling or cancellation."""
		settings = frappe.get_doc("Huddle Settings")
		if not settings.send_email_invite:
			return

		subject = f"Huddle {change_type}: {self.title}"
		
		# Define status pill color based on change_type
		status_color = "#3498db" if change_type == "Rescheduled" else "#e74c3c"
		
		if change_type == "Rescheduled":
			message = f"""
				<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
					<h2 style="color: {status_color}; margin-top: 0;">Meeting Rescheduled</h2>
					<p>The huddle <b>{self.title}</b> has been rescheduled to a new time.</p>
					<div style="background: #f9f9f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
						<p style="margin: 5px 0;"><b>New Date:</b> {frappe.utils.global_date_format(self.meeting_date)}</p>
						<p style="margin: 5px 0;"><b>New Time:</b> {frappe.utils.get_time(self.meeting_date)}</p>
					</div>
					<p style="margin-bottom: 25px;">Please update your calendar accordingly.</p>
					<a href="{self.jitsi_url}" style="background: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Join Updated Meeting</a>
				</div>
			"""
		else:
			message = f"""
				<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #eee; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
					<h2 style="color: {status_color}; margin-top: 0;">Meeting Cancelled</h2>
					<p>The huddle <b>{self.title}</b> scheduled for {frappe.utils.global_date_format(self.meeting_date)} at {frappe.utils.get_time(self.meeting_date)} has been cancelled.</p>
					<p>We apologize for the inconvenience.</p>
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
	"""Generate a join URL for the current user for a specific meeting."""
	meeting = frappe.get_doc("Huddle Meeting", meeting_name)
	settings = frappe.get_doc("Huddle Settings")

	domain = settings.jitsi_domain or "meet.jit.si"
	app_id = settings.app_id or ""

	# Build base URL
	if domain == "8x8.vc" and app_id:
		join_url = f"https://{domain}/{app_id}/{meeting.jitsi_room}"
	else:
		join_url = f"https://{domain}/{meeting.jitsi_room}"

	# Add JWT if available
	jwt_token = meeting._get_jwt_token(settings)
	if jwt_token:
		join_url += f"?jwt={jwt_token}"

	# Mark participant as joined
	for p in meeting.participants:
		if p.user and p.user == frappe.session.user:
			p.joined = 1
			p.joined_at = frappe.utils.now()
			
			# If someone joins, and it is still "Scheduled", mark as "In Progress"
			if meeting.status == "Scheduled":
				meeting.status = "In Progress"
				
			meeting.save(ignore_permissions=True)
			break

	return {"join_url": join_url}

	return {"join_url": join_url}


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
	"""Sync statuses for all active meetings based on current time."""
	now = frappe.utils.now()
	
	# Update Scheduled/In Progress to Completed if past end_date
	# We use a single query for efficiency
	frappe.db.sql("""
		UPDATE `tabHuddle Meeting`
		SET status = 'Completed'
		WHERE status NOT IN ('Completed', 'Cancelled')
		AND COALESCE(end_date, DATE_ADD(meeting_date, INTERVAL 60 MINUTE)) < %s
	""", (now,))
	
	# Update Scheduled to In Progress if it's currently happening
	frappe.db.sql("""
		UPDATE `tabHuddle Meeting`
		SET status = 'In Progress'
		WHERE status = 'Scheduled'
		AND meeting_date <= %s
		AND COALESCE(end_date, DATE_ADD(meeting_date, INTERVAL 60 MINUTE)) >= %s
	""", (now, now))
	
	return True


@frappe.whitelist()
def get_events(doctype, start, end, filters=None):
	"""Custom get_events for calendar to include participants and rich tooltip data."""
	from frappe.desk.reportview import get_filters_cond
	
	conditions = get_filters_cond(doctype, filters, [])
	
	# Fetch meetings that start or end within the range
	# We use a more robust query that handles NULL end_date by calculating it on the fly in the filter
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
		# Update status on the fly based on current time
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

		# Fetch participants for each meeting
		participants = frappe.db.get_all("Huddle Participant", 
			filters={"parent": m.name}, 
			fields=["full_name"]
		)
		participant_names = ", ".join([p.full_name for p in participants if p.full_name])
		
		# Map for calendar view
		m.start = m.meeting_date
		m.end = m.end_date or frappe.utils.add_to_date(m.meeting_date, minutes=m.duration or 60)
		m.participant_list = participant_names
		m.all_day = 0
		
	return meetings
