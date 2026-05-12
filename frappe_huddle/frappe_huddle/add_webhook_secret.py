import frappe
def add_webhook_secret():
    try:
        doc = frappe.get_doc("DocType", "Huddle Settings")
        field_exists = False
        for f in doc.fields:
            if f.fieldname == "webhook_secret":
                field_exists = True
                break
        if not field_exists:
            doc.append("fields", {
                "fieldname": "webhook_secret",
                "label": "Webhook Secret",
                "fieldtype": "Data",
                "insert_after": "app_secret"
            })
            doc.save()
            print("webhook_secret added")
    except Exception as e:
        print(f"Error: {e}")
