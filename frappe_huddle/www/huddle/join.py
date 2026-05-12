import frappe
from frappe import _


def get_context(context):
    """Redirect /huddle/join?meeting=HM-xxxx to the desk form view.
    
    Validates login first, then redirects to /app/huddle-meeting/HM-xxxx
    where the user can click "Join Huddle" to open the Jitsi dialog.
    """
    meeting_name = frappe.form_dict.get("meeting")
    
    if not meeting_name:
        frappe.throw(
            _("No meeting specified. Use /huddle/join?meeting=MEETING-ID"),
            frappe.DoesNotExistError
        )

    # If not logged in, redirect to login with redirect-to back here
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = (
            f"/login?redirect-to=/huddle/join?meeting={meeting_name}"
        )
        raise frappe.Redirect

    # Verify meeting exists
    if not frappe.db.exists("Huddle Meeting", meeting_name):
        frappe.throw(_("Meeting not found"), frappe.DoesNotExistError)

    # Redirect to the desk form view
    frappe.local.flags.redirect_location = f"/app/huddle-meeting/{meeting_name}"
    raise frappe.Redirect
