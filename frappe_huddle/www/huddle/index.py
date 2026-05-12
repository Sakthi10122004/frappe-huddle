import frappe
from frappe import _

def get_context(context):
    context.meetings = get_meetings()
    context.can_configure = "System Manager" in frappe.get_roles()
    
    if context.can_configure:
        context.huddle_settings = frappe.get_doc("Huddle Settings")
        context.team_members = get_team_members()
    
    context.no_cache = 1

def get_meetings():
    meetings = frappe.get_all(
        "Huddle Meeting",
        fields=["name", "title", "status", "meeting_date", "duration", "jitsi_url", "owner"],
        order_by="meeting_date desc",
        filters={"status": ["!=", "Cancelled"]}
    )
    
    for meeting in meetings:
        meeting.user_fullname = frappe.db.get_value("User", meeting.owner, "full_name") or meeting.owner
        meeting.user_image = frappe.db.get_value("User", meeting.owner, "user_image")
        
        # Get participants for this meeting
        meeting.participants = frappe.get_all(
            "Huddle Participant",
            filters={"parent": meeting.name},
            fields=["full_name", "email", "user", "joined"]
        )
        for p in meeting.participants:
            if p.user:
                p.user_image = frappe.db.get_value("User", p.user, "user_image")
    
    return meetings

def get_team_members():
    return frappe.get_all(
        "User",
        fields=["name", "full_name", "user_image", "email", "enabled"],
        filters={"user_type": "System User", "enabled": 1},
        limit=100
    )

@frappe.whitelist()
def save_settings(settings):
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Not authorized"), frappe.PermissionError)
    
    import json
    data = json.loads(settings)
    
    doc = frappe.get_doc("Huddle Settings")
    for key, value in data.items():
        doc.set(key, value)
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
            meeting.append("participants", {
                "user": p.get("email"),
                "full_name": p.get("full_name"),
                "email": p.get("email")
            })
            
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
    """
    Webhook endpoint for Jitsi to send events to.
    Events like PARTICIPANT_JOINED, PARTICIPANT_LEFT.
    This requires configuring your Jitsi server to send POST webhooks.
    """
    expected_secret = frappe.db.get_single_value("Huddle Settings", "webhook_secret")
    if expected_secret and frappe.request.headers.get("Authorization") != expected_secret:
        return {"status": "unauthorized"}

    data = frappe.request.get_json() if frappe.request else None
    if not data:
        return {"status": "ignored"}
        
    event_type = data.get("eventType")
    room_name = data.get("room_name") or data.get("roomName")
    
    if not room_name:
        return {"status": "ignored"}
        
    # Find matching meeting by room name
    meeting_name = frappe.db.get_value("Huddle Meeting", {"jitsi_room": room_name})
    if not meeting_name:
        return {"status": "not_found"}
        
    meeting = frappe.get_doc("Huddle Meeting", meeting_name)
    
    if event_type == "PARTICIPANT_JOINED":
        email = data.get("email") or (data.get("user") or {}).get("email")
        if email:
            # Check if user exists
            participant_user = frappe.db.get_value("User", {"email": email}, "name")
            if participant_user:
                session_id = data.get("sessionId") or data.get("session_id") or "webhook_session"
                # Add attendance log
                if not frappe.db.exists("Huddle Attendance Log", {"meeting": meeting_name, "participant": participant_user, "session_id": session_id, "leave_time": ("is", "not set")}):
                    log = frappe.get_doc({
                        "doctype": "Huddle Attendance Log",
                        "meeting": meeting_name,
                        "participant": participant_user,
                        "join_time": frappe.utils.now_datetime(),
                        "session_id": session_id
                    })
                    log.insert(ignore_permissions=True)
        
        if meeting.status == "Scheduled":
            meeting.db_set("status", "In Progress", update_modified=False)
            
    elif event_type == "PARTICIPANT_LEFT":
        email = data.get("email") or (data.get("user") or {}).get("email")
        if email:
            participant_user = frappe.db.get_value("User", {"email": email}, "name")
            if participant_user:
                session_id = data.get("sessionId") or data.get("session_id") or "webhook_session"
                active_log = frappe.db.get_value(
                    "Huddle Attendance Log",
                    {"meeting": meeting_name, "participant": participant_user, "session_id": session_id, "leave_time": ("is", "not set")},
                    "name"
                )
                if active_log:
                    now_dt = frappe.utils.now_datetime()
                    frappe.db.set_value("Huddle Attendance Log", active_log, "leave_time", now_dt)
                    log_doc = frappe.get_doc("Huddle Attendance Log", active_log)
                    if log_doc.join_time:
                        duration = (now_dt - log_doc.join_time).total_seconds()
                        frappe.db.set_value("Huddle Attendance Log", active_log, "duration", duration)

    elif event_type == "ROOM_DESTROYED":
        # Usually means meeting ended
        if meeting.status != "Cancelled":
            meeting.db_set("status", "Completed", update_modified=False)
            
    return {"status": "ok"}
