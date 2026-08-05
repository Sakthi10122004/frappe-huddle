import frappe

def execute():
	"""Remove old Jitsi values and reset room states for new architecture."""
	# Check if old columns still exist before trying to clear them
	columns = frappe.db.get_table_columns("Huddle Meeting")
	
	updates = {}
	if "jitsi_room" in columns:
		updates["jitsi_room"] = None
	if "jitsi_url" in columns:
		updates["jitsi_url"] = None
	if "jitsi_embed" in columns:
		updates["jitsi_embed"] = None
		
	updates["room_id"] = None
	
	# Update all records
	if updates:
		frappe.db.set_value("Huddle Meeting", None, updates, update_modified=False)
		
	# Update room status for active meetings
	frappe.db.sql("""
		UPDATE `tabHuddle Meeting`
		SET room_status = 'Pending'
		WHERE status IN ('Scheduled', 'Live')
	""")
	
	frappe.db.commit()
