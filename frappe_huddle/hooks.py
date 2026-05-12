app_name = "frappe_huddle"
app_title = "Frappe Huddle"
app_publisher = "Sakthi"
app_description = "Open source video meetings inside Frappe using Jitsi"
app_email = "sakthikaribeeran@gmail.com"
app_license = "mit"

# FIX: after_install hook so roles and settings are created automatically
after_install = "frappe_huddle.install.after_install"

# Document Events
doc_events = {
	"Event": {
		"on_update": "frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.sync_to_huddle_meeting"
	}
}

# Scheduled Tasks
scheduler_events = {
	"cron": {
		"* * * * *": [
			"frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.sync_all_statuses",
			"frappe_huddle.frappe_huddle.doctype.huddle_meeting.huddle_meeting.send_meeting_reminders",
		]
	}
}
