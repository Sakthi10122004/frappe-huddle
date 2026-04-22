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
