frappe.ui.form.on("User AI Settings", {
	refresh(frm) {
		if (frm.fields_dict.api_key && frm.doc.api_key) {
			frm.set_df_property(
				"api_key",
				"description",
				__("A key is saved. Leave this field blank to keep it. Fetch models uses the saved key.")
			);
		}
		frm.set_intro(
			__(
				"Each user has one User AI Settings document. Add rows under Saved providers for extra models (OpenAI, Claude, Groq, …) and tick Active on the one chat should use."
			)
		);
		if (frm.is_new()) {
			desk_assistant_open_existing(frm);
		}
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.bind(frm, {
				provider: "provider",
				model: "model",
				api_key: "api_key",
				base_url: "base_url",
				source: "user",
			});
		}
		frm.add_custom_button(__("Fetch models"), () => {
			desk_assistant.form.fetch_models(frm, false);
		});
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test connection"), () => {
				const active = (frm.doc.profiles || []).find((row) => row.is_active);
				frappe.call({
					method: "desk_assistant.api.chat.test_connection",
					args: {
						settings_user: frm.doc.user,
						profile: active && active.name,
					},
					freeze: true,
					freeze_message: __("Calling the model…"),
					callback(r) {
						const msg = r.message || {};
						const who = [msg.provider, msg.model].filter(Boolean).join(" · ");
						const reply = msg.reply || __("Connected.");
						frappe.show_alert({
							message: who ? `${who}: ${reply}` : reply,
							indicator: "green",
						});
					},
				});
			});
		}
	},
	after_save(frm) {
		if (
			window.desk_assistant &&
			desk_assistant.refresh_status &&
			frm.doc.user === frappe.session.user
		) {
			desk_assistant.refresh_status();
		}
	},
	user(frm) {
		if (frm.is_new()) {
			desk_assistant_open_existing(frm);
		}
	},
	provider(frm) {
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.apply_defaults(frm, true);
			desk_assistant.form.fetch_models(frm, false);
		}
	},
	api_key(frm) {
		if (desk_assistant && desk_assistant.form) {
			desk_assistant.form.fetch_models(frm, true);
		}
	},
	base_url(frm) {
		const refetch = ["openai_compatible", "ollama", "groq", "openrouter"];
		if (desk_assistant && desk_assistant.form && refetch.includes(frm.doc.provider)) {
			desk_assistant.form.fetch_models(frm, true);
		}
	},
});

function desk_assistant_open_existing(frm) {
	const user = frm.doc.user || frappe.session.user;
	if (!user) {
		return;
	}
	frappe.db.exists("User AI Settings", user).then((exists) => {
		if (!exists || !frm.is_new()) {
			return;
		}
		frappe.show_alert({
			message: __("This user already has AI settings. Add another provider row there instead of creating a second document."),
			indicator: "orange",
		});
		frappe.set_route("Form", "User AI Settings", user);
	});
}
