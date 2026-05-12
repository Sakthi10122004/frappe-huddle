import frappe

def create_roles_and_permissions():
    roles = ["Huddle Admin", "Huddle User", "Huddle Guest"]
    for role_name in roles:
        if not frappe.db.exists("Role", role_name):
            doc = frappe.get_doc({
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1 if role_name != "Huddle Guest" else 0
            })
            doc.insert(ignore_permissions=True)
            print(f"Created role {role_name}")

    # Add permissions to Huddle Meeting
    meeting_doc = frappe.get_doc("DocType", "Huddle Meeting")
    
    # Check if permissions already exist
    existing_roles = [p.role for p in meeting_doc.permissions]
    
    if "Huddle Admin" not in existing_roles:
        meeting_doc.append("permissions", {
            "role": "Huddle Admin", "read": 1, "write": 1, "create": 1, "delete": 1, "submit": 0
        })
    if "Huddle User" not in existing_roles:
        meeting_doc.append("permissions", {
            "role": "Huddle User", "read": 1, "write": 1, "create": 1, "delete": 0, "submit": 0
        })
    if "Huddle Guest" not in existing_roles:
        meeting_doc.append("permissions", {
            "role": "Huddle Guest", "read": 1, "write": 0, "create": 0, "delete": 0, "submit": 0
        })
        
    meeting_doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("Permissions updated.")

if __name__ == "__main__":
    create_roles_and_permissions()
