"""
frappe_huddle/install.py
Runs automatically after `bench install-app frappe_huddle`.
Hooked via hooks.py: after_install = "frappe_huddle.install.after_install"
"""

import frappe


def after_install():
	"""Set up roles and seed default Huddle Settings."""
	_create_roles()
	_seed_settings()
	frappe.db.commit()
	print("[Frappe Huddle] Installation complete. Visit /app/huddle-settings to configure.")


def _create_roles():
	"""Create the three Huddle roles if they don't already exist."""
	roles = [
		{"role_name": "Huddle Admin", "desk_access": 1},
		{"role_name": "Huddle User", "desk_access": 1},
		{"role_name": "Huddle Guest", "desk_access": 0},
	]

	for role_def in roles:
		if not frappe.db.exists("Role", role_def["role_name"]):
			role = frappe.get_doc({"doctype": "Role", **role_def})
			role.insert(ignore_permissions=True)
			print(f"[Frappe Huddle] Created role: {role_def['role_name']}")
		else:
			print(f"[Frappe Huddle] Role already exists: {role_def['role_name']}")


def _seed_settings():
	"""Seed sensible defaults into Huddle Settings on first install."""
	settings = frappe.get_doc("Huddle Settings")

	changed = False

	if not settings.jitsi_domain:
		settings.jitsi_domain = "meet.jit.si"
		changed = True

	if not settings.default_duration:
		settings.default_duration = 60
		changed = True

	if settings.enable_reminders is None:
		settings.enable_reminders = 1
		changed = True

	if not settings.reminder_minutes:
		settings.reminder_minutes = 10
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
		print("[Frappe Huddle] Seeded default Huddle Settings.")
