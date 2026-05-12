import frappe
import uuid

def generate_ics(meeting):
	"""Generate iCalendar text block for attachments."""
	frappe_start = frappe.utils.get_datetime(meeting.meeting_date)
	frappe_end = frappe.utils.get_datetime(meeting.end_date) if meeting.end_date else frappe.utils.add_to_date(meeting.meeting_date, minutes=meeting.duration or 60)
	
	dtstart = frappe_start.strftime("%Y%m%dT%H%M%S")
	dtend = frappe_end.strftime("%Y%m%dT%H%M%S")
	stamp = frappe.utils.now_datetime().strftime("%Y%m%dT%H%M%S")
	
	# Remove quotes and control chars for safe ICS
	safe_title = meeting.title.replace('"', '').replace('\n', ' ')
	
	ics = [
		"BEGIN:VCALENDAR",
		"VERSION:2.0",
		"PRODID:-//Frappe Huddle//EN",
		"METHOD:REQUEST",
		"BEGIN:VEVENT",
		f"UID:{meeting.name}-{uuid.uuid4().hex[:8]}@frappe",
		f"DTSTAMP:{stamp}",
		f"DTSTART:{dtstart}",
		f"DTEND:{dtend}",
		f"SUMMARY:{safe_title}",
		f"DESCRIPTION:Join video huddle here: {meeting.jitsi_url}",
		f"LOCATION:Huddle Video Call",
		f"URL:{meeting.jitsi_url}",
		"STATUS:CONFIRMED",
		"BEGIN:VALARM",
		"TRIGGER:-PT10M",
		"ACTION:DISPLAY",
		"DESCRIPTION:Meeting Reminder",
		"END:VALARM",
		"END:VEVENT",
		"END:VCALENDAR"
	]
	return "\r\n".join(ics)
