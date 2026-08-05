"""
frappe_huddle/livekit_utils.py
LiveKit integration for Frappe Huddle.

Handles token generation and webhook verification.
"""

# pyrefly: ignore [missing-import]
import frappe
# pyrefly: ignore [missing-import]
from livekit import api


def _get_settings():
	return frappe.get_cached_doc("Huddle Settings")


def create_meeting_token(room_name, user_name, is_owner=False, exp_minutes=120, user_email=None):
	"""
	Generate a LiveKit access token for a participant.
	
	Args:
		room_name:   The LiveKit room name.
		user_name:   Display name shown in the call.
		is_owner:    If True, grants host/owner privileges.
		exp_minutes: Token lifetime in minutes (default 2 hours).
		user_email:  The user's email, used as their identity.

	Returns:
		str – the JWT token string.
	"""
	settings = _get_settings()
	api_key = settings.get_password("livekit_api_key")
	api_secret = settings.get_password("livekit_api_secret")

	if not api_key or not api_secret:
		frappe.throw(
			frappe._("LiveKit API Key or Secret is not configured. Go to Huddle Settings."),
			title=frappe._("LiveKit Not Configured")
		)

	# Set up the token
	token = api.AccessToken(api_key, api_secret)
	
	import uuid
	identity = user_email if user_email else f"{user_name.replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
	
	token.with_identity(identity)
	token.with_name(user_name)
	import datetime
	token.with_ttl(datetime.timedelta(minutes=exp_minutes))

	# Setup video grants
	grants = api.VideoGrants(
		room_join=True,
		room=room_name,
		can_publish=True,
		can_subscribe=True,
		can_publish_data=True,
	)

	if is_owner:
		grants.room_create = True
		grants.room_admin = True
		
		if settings.livekit_enable_recording:
			grants.room_record = True

	token.with_grants(grants)
	return token.to_jwt()


def delete_room(room_name):
	"""Delete a LiveKit room."""
	import asyncio
	settings = _get_settings()
	api_key = settings.get_password("livekit_api_key")
	api_secret = settings.get_password("livekit_api_secret")
	livekit_rest_url = settings.livekit_rest_url

	if not api_key or not api_secret or not livekit_rest_url:
		return

	async def _delete():
		from livekit.api import LiveKitAPI
		from livekit.protocol import room
		client = LiveKitAPI(livekit_rest_url, api_key, api_secret)
		try:
			await client.room.delete_room(room.DeleteRoomRequest(room=room_name))
		except Exception as e:
			frappe.log_error(f"LiveKit delete_room error: {e}", "LiveKit Error")
		finally:
			await client.aclose()
			
	asyncio.run(_delete())

def create_room(room_name, empty_timeout=300):
	"""Explicitly create a LiveKit room with specific timeout settings."""
	import asyncio
	settings = _get_settings()
	api_key = settings.get_password("livekit_api_key")
	api_secret = settings.get_password("livekit_api_secret")
	livekit_rest_url = settings.livekit_rest_url

	if not api_key or not api_secret or not livekit_rest_url:
		return

	async def _create():
		from livekit.api import LiveKitAPI
		from livekit.protocol import room
		client = LiveKitAPI(livekit_rest_url, api_key, api_secret)
		try:
			req = room.CreateRoomRequest(name=room_name, empty_timeout=int(empty_timeout))
			await client.room.create_room(req)
		except Exception as e:
			frappe.log_error(f"LiveKit create_room error: {e}", "LiveKit Error")
		finally:
			await client.aclose()
			
	asyncio.run(_create())

@frappe.whitelist(allow_guest=True)
def livekit_webhook():
	"""Webhook endpoint to receive events from LiveKit Cloud."""
	# pyrefly: ignore [missing-import]
	import frappe
	# pyrefly: ignore [missing-import]
	from livekit.api.access_token import TokenVerifier
	# pyrefly: ignore [missing-import]
	from livekit.api import WebhookReceiver
	# pyrefly: ignore [missing-import]
	from frappe_huddle.frappe_huddle.doctype.huddle_room_event.huddle_room_event import log_room_event
	# pyrefly: ignore [missing-import]
	from frappe.utils import now_datetime

	auth_token = frappe.request.headers.get("Authorization")
	body = frappe.request.get_data(as_text=True)

	if not auth_token:
		frappe.throw("Missing Authorization Header", frappe.AuthenticationError)

	settings = _get_settings()
	api_key = settings.get_password("livekit_api_key")
	api_secret = settings.get_password("livekit_webhook_secret") or settings.get_password("livekit_api_secret")

	if not api_key or not api_secret:
		frappe.throw("LiveKit API Secret not configured")

	verifier = TokenVerifier(api_key, api_secret)
	receiver = WebhookReceiver(verifier)
	
	try:
		event = receiver.receive(body, auth_token)
	except Exception as e:
		frappe.log_error(f"Webhook Verification Failed: {e}", "LiveKit Webhook")
		frappe.throw("Invalid Signature", frappe.AuthenticationError)
		return

	event_name = event.event
	
	if event_name == "participant_joined":
		user_email = event.participant.identity
		room_id = event.room.name
		
		meeting_name = frappe.db.get_value("Huddle Meeting", {"room_id": room_id}, "name")
		if meeting_name:
			frappe.db.set_value("Huddle Meeting", meeting_name, "participant_count", event.room.num_participants)
			participant_name = frappe.db.get_value("Huddle Participant", {
				"parent": meeting_name,
				"user": user_email,
				"is_active": 1
			}, "name")
			if participant_name:
				frappe.db.set_value("Huddle Participant", participant_name, "state", "Joined")
				
			active_session_name = frappe.db.get_value("Huddle Session", {"meeting": meeting_name, "participant": user_email, "is_active": 1}, "name")
			if active_session_name:
				frappe.db.set_value("Huddle Session", active_session_name, "livekit_participant_sid", event.participant.sid)
				frappe.db.set_value("Huddle Session", active_session_name, "session_state", "Active")
				
				from frappe_huddle.frappe_huddle.doctype.huddle_attendance_log.huddle_attendance_log import create_attendance_log
				create_attendance_log(meeting_name, user_email, session=active_session_name)
				
			log_room_event(meeting_name, "Joined", source="Webhook", session=active_session_name, triggered_by=user_email)
			
	elif event_name == "participant_left":
		user_email = event.participant.identity
		room_id = event.room.name
		meeting_name = frappe.db.get_value("Huddle Meeting", {"room_id": room_id}, "name")
		if meeting_name:
			frappe.db.set_value("Huddle Meeting", meeting_name, "participant_count", event.room.num_participants)
			participant_name = frappe.db.get_value("Huddle Participant", {
				"parent": meeting_name,
				"user": user_email,
				"is_active": 1
			}, "name")
			if participant_name:
				frappe.db.set_value("Huddle Participant", participant_name, "state", "Left")
				frappe.db.set_value("Huddle Participant", participant_name, "is_active", 0)
				frappe.db.set_value("Huddle Participant", participant_name, "left_at", now_datetime())
			
			active_session_name = frappe.db.get_value("Huddle Session", {"meeting": meeting_name, "participant": user_email, "is_active": 1}, "name")
			log_room_event(meeting_name, "Left", source="Webhook", session=active_session_name, triggered_by=user_email)
			
			# Clean up session and attendance log
			from frappe_huddle.frappe_huddle.doctype.huddle_attendance_log.huddle_attendance_log import finalize_attendance_log
			finalize_attendance_log(meeting_name, user_email, session=active_session_name)
			
			if active_session_name:
				session_doc = frappe.get_doc("Huddle Session", active_session_name)
				session_doc.close_session()

	elif event_name in ("track_muted", "track_unmuted"):
		user_email = event.participant.identity
		room_id = event.room.name
		meeting_name = frappe.db.get_value("Huddle Meeting", {"room_id": room_id}, "name")
		if meeting_name:
			action = "Muted" if event_name == "track_muted" else "Unmuted"
			active_session_name = frappe.db.get_value("Huddle Session", {"meeting": meeting_name, "participant": user_email, "is_active": 1}, "name")
			log_room_event(meeting_name, action, source="Webhook", session=active_session_name, triggered_by=user_email)

	elif event_name == "egress_ended":
		if event.egress_info and event.egress_info.room_name:
			meeting_name = frappe.db.get_value("Huddle Meeting", {"room_id": event.egress_info.room_name}, "name")
			if meeting_name:
				if len(event.egress_info.file_results) > 0:
					recording_url = event.egress_info.file_results[0].location or event.egress_info.file_results[0].filename
					if recording_url:
						frappe.db.set_value("Huddle Meeting", meeting_name, "recording_url", recording_url)

	return "OK"
