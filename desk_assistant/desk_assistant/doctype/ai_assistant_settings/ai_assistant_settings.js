frappe.ui.form.on("AI Assistant Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Leave Allowed DocTypes empty so the assistant can ask about anything the user can already read in Desk (secrets stay blocked). Add rows only if you want a narrower AI than that user's Desk permissions."
			)
		);
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.bind(frm, {
				provider: "default_provider",
				model: "default_model",
				api_key: "default_api_key",
				base_url: "default_base_url",
				source: "site",
			});
		}
		frm.add_custom_button(__("Fetch models"), () => {
			desk_assistant.form.fetch_models(frm, false);
		});
	},
	default_provider(frm) {
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.apply_defaults(frm, true);
			desk_assistant.form.fetch_models(frm, false);
		}
	},
	default_api_key(frm) {
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.fetch_models(frm, true);
		}
	},
	default_base_url(frm) {
		const refetch = ["openai_compatible", "ollama", "groq", "openrouter"];
		if (desk_assistant && desk_assistant.form && refetch.includes(frm.doc.default_provider)) {
			desk_assistant.form.fetch_models(frm, true);
		}
	},
});
