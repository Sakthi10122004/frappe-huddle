import frappe
from frappe.utils import format_datetime, get_url

def generate_ics(doc):
	"""Generates ICS content for a Huddle Meeting."""
	start = format_datetime(doc.meeting_date, "yyyyMMdd'T'HHmmss'Z'")
	end = format_datetime(doc.end_date, "yyyyMMdd'T'HHmmss'Z'") if doc.end_date else start
	
	url = get_url(f"/app/huddle-meeting/{doc.name}")
	
	description = doc.description or ""
	description += f"\\n\\nJoin URL: {url}"
	
	ics = [
		"BEGIN:VCALENDAR",
		"VERSION:2.0",
		"PRODID:-//Frappe Huddle//EN",
		"CALSCALE:GREGORIAN",
		"BEGIN:VEVENT",
		f"UID:{doc.name}@frappe_huddle",
		f"DTSTAMP:{start}",
		f"DTSTART:{start}",
		f"DTEND:{end}",
		f"SUMMARY:{doc.title}",
		f"DESCRIPTION:{description}",
		f"URL:{url}",
		"END:VEVENT",
		"END:VCALENDAR"
	]
	
	return "\n".join(ics)
