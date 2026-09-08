app_name = "desk_assistant"
app_title = "Desk Assistant"
app_publisher = "Desk Assistant"
app_description = "Permission-aware AI sidebar for Frappe Desk"
app_email = "developers@example.com"
app_license = "mit"
app_home = "/desk/desk-assistant"
required_apps = []

add_to_apps_screen = [
	{
		"name": "desk_assistant",
		"logo": "/assets/desk_assistant/images/desk-assistant-logo.svg",
		"title": "Desk Assistant",
		"route": "/desk/desk-assistant",
		"has_permission": "desk_assistant.permissions.check_app_permission",
	}
]

app_include_css = "desk_assistant.bundle.css"
app_include_js = "desk_assistant.bundle.js"

after_install = "desk_assistant.install.after_install"
after_migrate = "desk_assistant.install.after_migrate"
before_uninstall = "desk_assistant.install.before_uninstall"
after_uninstall = "desk_assistant.install.after_uninstall"

boot_session = "desk_assistant.boot.boot_session"
extend_bootinfo = "desk_assistant.boot.extend_bootinfo"

permission_query_conditions = {
	"User AI Settings": "desk_assistant.permissions.get_user_ai_settings_query",
	"AI Chat Session": "desk_assistant.permissions.get_chat_session_query",
}

has_permission = {
	"User AI Settings": "desk_assistant.permissions.has_user_ai_settings_permission",
	"AI Chat Session": "desk_assistant.permissions.has_chat_session_permission",
	"AI Assistant Audit Log": "desk_assistant.permissions.has_audit_log_permission",
}

doctype_js = {
	"User AI Settings": "public/js/provider_form.js",
	"AI Assistant Settings": "public/js/provider_form.js",
}

export_python_type_annotations = True
