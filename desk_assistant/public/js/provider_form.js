frappe.provide("desk_assistant.form");

desk_assistant.form.DEFAULTS = {
	openai: "https://api.openai.com/v1",
	anthropic: "https://api.anthropic.com",
	google: "https://generativelanguage.googleapis.com/v1beta",
	groq: "https://api.groq.com/openai/v1",
	openrouter: "https://openrouter.ai/api/v1",
	ollama: "http://127.0.0.1:11434/v1",
};

desk_assistant.form.bind = function (frm, map) {
	frm._da_fields = map;
	desk_assistant.form.apply_defaults(frm, false);
	desk_assistant.form.fetch_models(frm, true);
};

desk_assistant.form.apply_defaults = function (frm, dirty) {
	const map = frm._da_fields;
	const provider = frm.doc[map.provider];
	const fixed = desk_assistant.form.DEFAULTS[provider];
	if (!fixed) {
		return;
	}
	const current = (frm.doc[map.base_url] || "").replace(/\/$/, "");
	const want = fixed.replace(/\/$/, "");
	if (current === want) {
		return;
	}
	const known = Object.values(desk_assistant.form.DEFAULTS)
		.concat([
			"http://localhost:11434/v1",
			"https://generativelanguage.googleapis.com/v1beta/openai",
		])
		.map((u) => (u || "").replace(/\/$/, ""));
	if (!current || known.includes(current)) {
		if (dirty) {
			frm.set_value(map.base_url, fixed);
		} else {
			frm.doc[map.base_url] = fixed;
			frm.refresh_field(map.base_url);
		}
	}
};

desk_assistant.form.set_models = function (frm, models) {
	const map = frm._da_fields;
	const field = map && frm.fields_dict[map.model];
	if (!field) {
		return;
	}
	const list = (models || []).filter(Boolean);
	frm._da_models = list;
	field.df.max_items = Math.max(list.length, 99);
	if (field.awesomplete) {
		field.awesomplete.maxItems = field.df.max_items;
	}
	if (field.set_data) {
		field.set_data(list);
	} else {
		frm.set_df_property(map.model, "options", list.join("\n"));
	}
	if (field.$input && !field._da_open_on_focus) {
		field._da_open_on_focus = true;
		field.$input.on("focus", function () {
			field.$input.trigger("input");
		});
	}
};

desk_assistant.form.is_dummy_key = function (val) {
	if (!val) {
		return true;
	}
	return String(val).replace(/\*/g, "") === "";
};

desk_assistant.form.doc_name = function (frm) {
	const name = frm.doc.name || "";
	if (!name || name === "undefined" || String(name).startsWith("new-")) {
		return frm.doc.user || "";
	}
	return name;
};

desk_assistant.form.fetch_models = function (frm, quiet) {
	const map = frm._da_fields;
	if (!map) {
		return;
	}
	const provider = frm.doc[map.provider];
	if (!provider) {
		return;
	}
	if (quiet && frm._da_models && frm._da_models.length) {
		desk_assistant.form.set_models(frm, frm._da_models);
		return;
	}
	const field = frm.fields_dict[map.api_key];
	const input_val = field && field.$input ? field.$input.val() : frm.doc[map.api_key];
	const raw = input_val || frm.doc[map.api_key];
	const dummy = desk_assistant.form.is_dummy_key(raw);
	const base_url = frm.doc[map.base_url] || desk_assistant.form.DEFAULTS[provider] || "";
	frappe.call({
		method: "desk_assistant.api.models.list_models",
		args: {
			provider: provider,
			base_url: base_url,
			api_key: dummy ? "" : raw,
			source: map.source,
			settings_doctype: frm.doctype,
			settings_name: desk_assistant.form.doc_name(frm),
			settings_user: frm.doc.user || "",
		},
		freeze: !quiet,
		freeze_message: __("Loading models…"),
		callback: function (r) {
			const msg = r.message || {};
			if (!msg.ok) {
				if (!quiet && msg.message) {
					frappe.show_alert({ message: msg.message, indicator: "orange" });
				}
				return;
			}
			desk_assistant.form.set_models(frm, msg.models || []);
			if (!quiet) {
				frappe.show_alert({
					message: __("Loaded {0} models. Click Model and type to pick one.", [
						cstr((msg.models || []).length),
					]),
					indicator: "green",
				});
			}
		},
	});
};
