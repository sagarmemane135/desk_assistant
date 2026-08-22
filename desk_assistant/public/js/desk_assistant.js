// Right Desk sidebar. Mounts only when frappe.boot.desk_assistant.enabled.

frappe.provide("desk_assistant");

desk_assistant.MIN_WIDTH = 320;
desk_assistant.DEFAULT_WIDTH = 360;
desk_assistant.LAYOUT = 2;
desk_assistant._save_timer = null;
desk_assistant._last_prefs = null;
desk_assistant.SKIP_CONTEXT = [
	"User AI Settings",
	"AI Assistant Settings",
	"AI Chat Session",
	"AI Chat Message",
	"AI Assistant Audit Log",
];
desk_assistant.session = null;
desk_assistant.session_title = "";
desk_assistant.PROVIDERS = [
	"openai",
	"anthropic",
	"google",
	"groq",
	"openrouter",
	"ollama",
	"openai_compatible",
];

desk_assistant.boot = function () {
	return frappe.boot.desk_assistant || { enabled: false };
};

desk_assistant.start = function () {
	if (desk_assistant._started) {
		return;
	}
	if (desk_assistant.boot().enabled) {
		desk_assistant._started = true;
		desk_assistant.mount();
		return;
	}
	if (desk_assistant._status_checked) {
		return;
	}
	desk_assistant._status_checked = true;
	if (!frappe.call) {
		return;
	}
	// Bootinfo is cached per user; Settings.enabled can change without a new boot.
	frappe.call({
		method: "desk_assistant.api.chat.get_status",
		callback: function (r) {
			if (!(r.message && r.message.enabled)) {
				return;
			}
			frappe.boot.desk_assistant = Object.assign({}, desk_assistant.boot(), r.message);
			desk_assistant._started = true;
			desk_assistant.mount();
		},
	});
};

desk_assistant.open = function () {
	if (!desk_assistant.boot().enabled) {
		frappe.show_alert({
			message: __(
				"Desk Assistant is not enabled for this user. Ask an admin to assign the AI Assistant User role."
			),
			indicator: "orange",
		});
		return;
	}
	if (!desk_assistant._started) {
		desk_assistant._started = true;
		desk_assistant.mount();
	} else if (!document.getElementById("desk-assistant-panel")) {
		desk_assistant.mount();
	}
	desk_assistant.apply_layout(desk_assistant.clamp_width(desk_assistant.current_width()), false);
	setTimeout(function () {
		$("#desk-assistant-input").trigger("focus");
	}, 50);
};

desk_assistant.register_search = function () {
	if (desk_assistant._search_registered) {
		return;
	}
	if (!(frappe.search && frappe.search.utils && frappe.search.utils.make_function_searchable)) {
		return;
	}
	if (!desk_assistant.boot().enabled) {
		return;
	}
	desk_assistant._search_registered = true;
	frappe.search.utils.make_function_searchable(desk_assistant.open, __("Open Desk Assistant"));
	frappe.search.utils.make_function_searchable(desk_assistant.open, __("Desk Assistant"));
};

desk_assistant.mount = function () {
	if (!(desk_assistant.boot().enabled)) {
		return;
	}
	desk_assistant.register_search();
	if (document.getElementById("desk-assistant-panel")) {
		return;
	}

	const boot = desk_assistant.boot();
	const stored = desk_assistant.read_local();
	const width = stored.width || boot.sidebar_width || desk_assistant.DEFAULT_WIDTH;
	// LAYOUT 2 docks in the body flex row. Ignore older overlay collapse prefs.
	let collapsed = !!boot.sidebar_collapsed;
	if (stored.layout === desk_assistant.LAYOUT && stored.collapsed != null) {
		collapsed = stored.collapsed;
	}

	desk_assistant.inject(width, collapsed);
	desk_assistant.bind();
	desk_assistant.apply_layout(width, collapsed);
	desk_assistant.update_context();
	desk_assistant.refresh_status();
	desk_assistant.restore_session();
};

desk_assistant.read_local = function () {
	try {
		return JSON.parse(localStorage.getItem("desk_assistant_sidebar") || "{}");
	} catch (e) {
		return {};
	}
};

desk_assistant.write_local = function (width, collapsed) {
	localStorage.setItem(
		"desk_assistant_sidebar",
		JSON.stringify({
			layout: desk_assistant.LAYOUT,
			width: width,
			collapsed: collapsed,
		})
	);
};

desk_assistant.meta_label = function () {
	const boot = desk_assistant.boot();
	return [boot.provider, boot.model].filter(Boolean).join(" · ") || __("No model set");
};

desk_assistant.empty_copy = function () {
	if (desk_assistant.boot().has_api_key) {
		return __(
			"Ask about invoices, stock, customers, or the open document. Answers use only data you can already read."
		);
	}
	return __("Add your API key with the gear, or ask an admin to set a site default.");
};

desk_assistant.refresh_header = function () {
	const meta = desk_assistant.meta_label();
	$(".desk-assistant-meta").attr("title", meta).text(meta);
};

desk_assistant.apply_status = function (msg) {
	if (!msg) {
		return;
	}
	const next = {};
	if (msg.provider != null) {
		next.provider = msg.provider;
	}
	if (msg.model != null) {
		next.model = msg.model;
	}
	if (msg.has_api_key != null) {
		next.has_api_key = !!msg.has_api_key;
	}
	if (msg.enabled != null) {
		next.enabled = msg.enabled;
	}
	frappe.boot.desk_assistant = Object.assign({}, desk_assistant.boot(), next);
	desk_assistant.refresh_header();
};

desk_assistant.refresh_status = function () {
	frappe.call({
		method: "desk_assistant.api.chat.get_status",
		callback: function (r) {
			if (!(r.message && r.message.enabled)) {
				return;
			}
			desk_assistant.apply_status(r.message);
			const $empty = $("#desk-assistant-messages .desk-assistant-empty");
			if ($empty.length) {
				$empty.text(desk_assistant.empty_copy());
			}
		},
	});
};

desk_assistant.inject = function (width, collapsed) {
	const meta = desk_assistant.meta_label();
	const html = `
		<div id="desk-assistant-panel" class="desk-assistant-panel" aria-label="${__("Desk Assistant")}">
			<div class="desk-assistant-handle" title="${__("Resize")}"></div>
			<div class="desk-assistant-header">
				<div class="desk-assistant-title">${__("Assistant")}</div>
				<div class="desk-assistant-meta" title="${frappe.utils.escape_html(meta)}">${frappe.utils.escape_html(meta)}</div>
				<button type="button" class="btn btn-default btn-xs da-wide" title="${__("Wide")}" aria-pressed="false">⇄</button>
				<button type="button" class="btn btn-default btn-xs da-settings" title="${__("Your AI settings")}">⚙</button>
				<button type="button" class="btn btn-default btn-xs da-collapse" title="${__("Collapse")}">›</button>
			</div>
			<div class="desk-assistant-context" id="desk-assistant-context"></div>
			<div class="desk-assistant-settings" id="desk-assistant-settings" hidden>
				<label class="da-set-label">${__("Saved providers")}
					<span class="da-set-profile-row">
						<select id="da-set-profile"></select>
						<button type="button" class="btn btn-default btn-xs da-add-profile" title="${__("Add another provider or model")}">+</button>
						<button type="button" class="btn btn-default btn-xs da-del-profile" title="${__("Delete this saved provider")}">−</button>
					</span>
				</label>
				<label class="da-set-label">${__("Provider")}
					<select id="da-set-provider"></select>
				</label>
				<label class="da-set-label">${__("Model")}
					<input id="da-set-model" list="da-set-models" autocomplete="off" />
					<datalist id="da-set-models"></datalist>
				</label>
				<label class="da-set-label">${__("API Key")}
					<input id="da-set-key" type="password" autocomplete="off" />
				</label>
				<label class="da-set-label">${__("Base URL")}
					<input id="da-set-url" autocomplete="off" />
				</label>
				<p class="da-set-hint">${__("Each user has one settings document. Use + to add OpenAI, Claude, Groq, and so on, then switch with the list above.")}</p>
				<div class="da-set-actions">
					<button type="button" class="btn btn-default btn-sm da-fetch-models">${__("Fetch models")}</button>
					<button type="button" class="btn btn-default btn-sm da-test-settings">${__("Test")}</button>
					<button type="button" class="btn btn-primary btn-sm da-save-settings">${__("Save")}</button>
				</div>
			</div>
			<div class="desk-assistant-messages" id="desk-assistant-messages">
				<div class="desk-assistant-empty">
					${desk_assistant.empty_copy()}
				</div>
			</div>
			<div class="desk-assistant-footer">
				<textarea id="desk-assistant-input" rows="3" placeholder="${__("Ask about invoices, stock, customers…")}"></textarea>
				<div class="desk-assistant-footer-actions">
					<button type="button" class="btn btn-default btn-sm da-clear">${__("New")}</button>
					<button type="button" class="btn btn-primary btn-sm da-send">${__("Send")}</button>
				</div>
			</div>
		</div>
		<button type="button" id="desk-assistant-tab" class="desk-assistant-tab" title="${__("Open Assistant")}">${__("Assistant")}</button>
	`;
	const $nodes = $(html);
	const $main = $(".main-section");
	if ($main.length) {
		$nodes.insertAfter($main);
	} else {
		$nodes.appendTo("body");
	}
	document.documentElement.style.setProperty("--desk-assistant-width", `${width}px`);
};

desk_assistant.apply_layout = function (width, collapsed) {
	const w = desk_assistant.clamp_width(width);
	document.documentElement.style.setProperty("--desk-assistant-width", `${w}px`);
	$("body").addClass("desk-assistant-docked");
	$("body").toggleClass("desk-assistant-open", !collapsed);
	$("body").toggleClass("desk-assistant-collapsed", !!collapsed);
	$("#desk-assistant-panel").toggleClass("is-collapsed", !!collapsed);
	$("#desk-assistant-tab").toggleClass("is-visible", !!collapsed);
	desk_assistant.write_local(w, !!collapsed);
	desk_assistant.schedule_save(w, collapsed);
};

desk_assistant.clamp_width = function (width) {
	const max = Math.max(desk_assistant.MIN_WIDTH, Math.floor(window.innerWidth * 0.5));
	return Math.min(max, Math.max(desk_assistant.MIN_WIDTH, parseInt(width, 10) || desk_assistant.DEFAULT_WIDTH));
};

desk_assistant.schedule_save = function (width, collapsed) {
	const payload = { width: width, collapsed: collapsed ? 1 : 0 };
	const last = desk_assistant._last_prefs;
	if (last && last.width === payload.width && last.collapsed === payload.collapsed) {
		return;
	}
	clearTimeout(desk_assistant._save_timer);
	desk_assistant._save_timer = setTimeout(function () {
		frappe.call({
			method: "desk_assistant.api.sidebar.save_prefs",
			args: payload,
			freeze: false,
			callback: function () {
				desk_assistant._last_prefs = payload;
			},
		});
	}, 600);
};

desk_assistant.get_context = function () {
	const route = (frappe.get_route && frappe.get_route()) || [];
	const ctx = {
		route: window.location.pathname,
		doctype: null,
		name: null,
	};
	if (Array.isArray(route) && route.length) {
		ctx.route = route.join("/");
		if (route[0] === "Form" && route[1] && route[2]) {
			ctx.doctype = route[1];
			ctx.name = route[2];
		}
	}
	return ctx;
};

desk_assistant.update_context = function () {
	const $el = $("#desk-assistant-context");
	if (!$el.length) {
		return;
	}
	if ($("#desk-assistant-panel").hasClass("is-settings")) {
		$el.removeClass("is-visible").empty();
		return;
	}
	const ctx = desk_assistant.get_context();
	if (ctx.doctype === "AI Chat Session" && (ctx.name || desk_assistant.session_title)) {
		const label = desk_assistant.session_title || ctx.name;
		$el.addClass("is-visible").text(__("This chat: {0}", [label]));
		return;
	}
	if (ctx.doctype && ctx.name && desk_assistant.SKIP_CONTEXT.indexOf(ctx.doctype) === -1) {
		const label = ctx.doctype === ctx.name ? ctx.doctype : `${ctx.doctype} ${ctx.name}`;
		$el.addClass("is-visible").text(__("This document: {0}", [label]));
	} else if (desk_assistant.session_title) {
		$el.addClass("is-visible").text(__("This chat: {0}", [desk_assistant.session_title]));
	} else {
		$el.removeClass("is-visible").empty();
	}
};

desk_assistant.clear_empty = function () {
	$("#desk-assistant-messages .desk-assistant-empty").remove();
};

desk_assistant.error_text = function (r) {
	const json = (r && r.responseJSON) || {};
	const parsed = desk_assistant.server_message(json);
	if (parsed) {
		return parsed;
	}
	if (json && typeof json.exc === "string" && json.exc) {
		const first = json.exc.split("\n")[0].replace(/^[^:]*:\s*/, "");
		if (first) {
			return first;
		}
	}
	if (typeof json.exception === "string" && json.exception) {
		return json.exception.split("\n")[0].replace(/^[^:]*:\s*/, "");
	}
	if (r && typeof r.message === "string") {
		return r.message;
	}
	return __("Could not send. Check your key in User AI Settings.");
};

desk_assistant.server_message = function (json) {
	try {
		let raw = json && json._server_messages;
		if (!raw) {
			return "";
		}
		const arr = typeof raw === "string" ? JSON.parse(raw) : raw;
		const first = arr && arr[0];
		const obj = typeof first === "string" ? JSON.parse(first) : first;
		let msg = (obj && obj.message) || "";
		return String(msg)
			.replace(/<[^>]+>/g, " ")
			.replace(/\s+/g, " ")
			.trim();
	} catch (e) {
		return "";
	}
};

desk_assistant.escape_html = function (text) {
	return $("<div>").text(text || "").html();
};

desk_assistant.format_inline = function (text) {
	let html = desk_assistant.escape_html(text);
	html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
	html = html.replace(
		/\[([^\]]+)\]\((\/(?:desk|app)\/[^)\s]+|https?:\/\/[^)\s]+)\)/g,
		function (_m, label, href) {
			return '<a href="' + href + '">' + label + "</a>";
		}
	);
	html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
	html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
	html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
	html = html.replace(/(^|[^"'>])(\/desk\/[A-Za-z0-9._~\-/%]+)/g, function (_m, prefix, path) {
		return prefix + '<a href="' + path + '">' + path + "</a>";
	});
	return html;
};

desk_assistant._is_table_sep = function (line) {
	return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(String(line || "").trim());
};

desk_assistant._is_table_row = function (line) {
	const t = String(line || "").trim();
	return t.indexOf("|") !== -1 && t.split("|").length >= 3;
};

desk_assistant._split_table_row = function (line) {
	let t = String(line || "").trim();
	if (t.charAt(0) === "|") {
		t = t.slice(1);
	}
	if (t.charAt(t.length - 1) === "|") {
		t = t.slice(0, -1);
	}
	return t.split("|").map(function (cell) {
		return cell.trim();
	});
};

desk_assistant.format_table = function (lines) {
	const rows = [];
	for (let i = 0; i < lines.length; i++) {
		if (desk_assistant._is_table_sep(lines[i])) {
			continue;
		}
		rows.push(desk_assistant._split_table_row(lines[i]));
	}
	if (!rows.length) {
		return "";
	}
	const width = rows[0].length;
	let html = '<table class="desk-assistant-table"><thead><tr>';
	for (let c = 0; c < width; c++) {
		html += "<th>" + desk_assistant.format_inline(rows[0][c] || "") + "</th>";
	}
	html += "</tr></thead><tbody>";
	for (let r = 1; r < rows.length; r++) {
		html += "<tr>";
		for (let c = 0; c < width; c++) {
			html += "<td>" + desk_assistant.format_inline(rows[r][c] || "") + "</td>";
		}
		html += "</tr>";
	}
	html += "</tbody></table>";
	return '<div class="desk-assistant-table-wrap">' + html + "</div>";
};

desk_assistant.format_reply = function (text) {
	const lines = String(text || "").split("\n");
	const out = [];
	let i = 0;
	while (i < lines.length) {
		if (
			i + 1 < lines.length &&
			desk_assistant._is_table_row(lines[i]) &&
			desk_assistant._is_table_sep(lines[i + 1])
		) {
			const block = [lines[i], lines[i + 1]];
			i += 2;
			while (i < lines.length && desk_assistant._is_table_row(lines[i])) {
				block.push(lines[i]);
				i += 1;
			}
			out.push(desk_assistant.format_table(block));
			continue;
		}
		const chunk = [];
		while (
			i < lines.length &&
			!(
				i + 1 < lines.length &&
				desk_assistant._is_table_row(lines[i]) &&
				desk_assistant._is_table_sep(lines[i + 1])
			)
		) {
			chunk.push(lines[i]);
			i += 1;
		}
		if (chunk.length) {
			out.push(desk_assistant.format_inline(chunk.join("\n")));
		}
	}
	return out.join("\n");
};

desk_assistant.append_bubble = function (role, text) {
	desk_assistant.clear_empty();
	const $el = $("<div>").addClass("desk-assistant-bubble " + role);
	if (role === "assistant") {
		$el.html(desk_assistant.format_reply(text || ""));
	} else {
		$el.text(text || "");
	}
	$el.appendTo("#desk-assistant-messages");
	const box = document.getElementById("desk-assistant-messages");
	if (box) {
		box.scrollTop = box.scrollHeight;
	}
};

desk_assistant.send = function () {
	const $input = $("#desk-assistant-input");
	const text = ($input.val() || "").trim();
	if (!text) {
		return;
	}
	$input.val("");
	desk_assistant.append_bubble("user", text);
	$(".da-send").prop("disabled", true);
	frappe.call({
		method: "desk_assistant.api.chat.send",
		args: {
			message: text,
			session: desk_assistant.session || "",
			context: JSON.stringify(desk_assistant.get_context()),
		},
		callback: function (r) {
			const msg =
				(r.message && r.message.message) || __("No reply from the model.");
			if (r.message && r.message.session) {
				desk_assistant.session = r.message.session;
			}
			desk_assistant.append_bubble("assistant", msg);
			if (r.message && (r.message.provider || r.message.model)) {
				frappe.boot.desk_assistant = Object.assign({}, desk_assistant.boot(), {
					provider: r.message.provider || desk_assistant.boot().provider,
					model: r.message.model || desk_assistant.boot().model,
					has_api_key: true,
				});
				desk_assistant.refresh_header();
			}
			$(".da-send").prop("disabled", false);
			$("#desk-assistant-input").trigger("focus");
		},
		error: function (r) {
			desk_assistant.append_bubble("assistant", desk_assistant.error_text(r));
			$(".da-send").prop("disabled", false);
		},
	});
};

desk_assistant.session_from_route = function () {
	const route = (frappe.get_route && frappe.get_route()) || [];
	if (route[0] === "Form" && route[1] === "AI Chat Session" && route[2]) {
		return route[2];
	}
	return "";
};

desk_assistant.apply_session = function (data) {
	const payload = data || {};
	desk_assistant.session = payload.session || null;
	desk_assistant.session_title = payload.title || "";
	const rows = payload.messages || [];
	if (!rows.length) {
		$("#desk-assistant-messages").html(
			`<div class="desk-assistant-empty">${desk_assistant.empty_copy()}</div>`
		);
		desk_assistant.update_context();
		return;
	}
	$("#desk-assistant-messages").empty();
	rows.forEach(function (row) {
		desk_assistant.append_bubble(row.role, row.content || "");
	});
	desk_assistant.update_context();
};

desk_assistant.restore_session = function () {
	const named = desk_assistant.session_from_route();
	frappe.call({
		method: named
			? "desk_assistant.api.chat.resume_session"
			: "desk_assistant.api.chat.get_open_session",
		args: named ? { session: named } : {},
		callback: function (r) {
			desk_assistant.apply_session(r.message || {});
		},
	});
};

desk_assistant.start_new_chat = function () {
	frappe.call({
		method: "desk_assistant.api.chat.new_session",
		callback: function (r) {
			desk_assistant.apply_session(r.message || {});
		},
	});
};

desk_assistant.toggle_settings = function () {
	if ($("#desk-assistant-panel").hasClass("is-settings")) {
		desk_assistant.hide_settings();
		return;
	}
	desk_assistant.show_settings();
};

desk_assistant.show_settings = function () {
	const $panel = $("#desk-assistant-panel");
	$panel.addClass("is-settings");
	$panel.find(".da-settings").attr("title", __("Back to chat")).attr("aria-pressed", "true");
	$("#desk-assistant-settings").removeAttr("hidden");
	$("#desk-assistant-context").removeClass("is-visible").empty();
	desk_assistant.fill_panel_settings();
};

desk_assistant.hide_settings = function () {
	const $panel = $("#desk-assistant-panel");
	$panel.removeClass("is-settings");
	$panel.find(".da-settings").attr("title", __("Your AI settings")).attr("aria-pressed", "false");
	$("#desk-assistant-settings").attr("hidden", true);
	desk_assistant.update_context();
	desk_assistant.refresh_status();
};

desk_assistant.fill_panel_settings = function () {
	const $provider = $("#da-set-provider");
	if (!$provider.find("option").length) {
		$provider.append($("<option>").val("").text(__("Site default")));
		(desk_assistant.PROVIDERS || []).forEach(function (id) {
			$provider.append($("<option>").val(id).text(id));
		});
	}
	frappe.call({
		method: "desk_assistant.api.sidebar.get_llm_settings",
		callback: function (r) {
			desk_assistant.apply_panel_payload(r.message || {});
		},
	});
};

desk_assistant.apply_panel_payload = function (msg) {
	desk_assistant._panel_defaults = msg;
	desk_assistant.fill_profile_select(msg);
	const active = (msg.profiles || []).filter(function (row) {
		return row.is_active;
	})[0];
	const selected = $("#da-set-profile").val();
	let row = null;
	if (selected && selected !== "__new__") {
		row = (msg.profiles || []).filter(function (item) {
			return item.name === selected;
		})[0];
	}
	if (!row) {
		row = active;
	}
	desk_assistant.apply_profile_fields(row, msg);
	desk_assistant.apply_status({
		provider: msg.active_provider || (row && row.provider) || msg.provider || "",
		model: msg.active_model || (row && row.model) || msg.model || "",
		has_api_key: msg.has_api_key,
	});
	desk_assistant.fetch_panel_models(true);
};

desk_assistant.fill_profile_select = function (msg) {
	const $sel = $("#da-set-profile").empty();
	const profiles = msg.profiles || [];
	if (!profiles.length) {
		$sel.append($("<option>").val("").text(__("No saved providers yet")));
	}
	profiles.forEach(function (row) {
		const mark = row.is_active ? " ✓" : "";
		$sel.append($("<option>").val(row.name).text((row.label || row.model || row.provider) + mark));
	});
	$sel.append($("<option>").val("__new__").text(__("New provider…")));
	const current = msg.profile || (profiles[0] && profiles[0].name) || "";
	if (current) {
		$sel.val(current);
	}
};

desk_assistant.apply_profile_fields = function (row, msg) {
	const provider = (row && row.provider) || (msg && msg.provider) || "";
	const model = (row && row.model) || (msg && msg.model) || "";
	const url = (row && row.base_url) || (msg && msg.base_url) || "";
	const has_key = row ? !!row.has_api_key : !!(msg && msg.has_api_key);
	$("#da-set-provider").val(provider);
	$("#da-set-model").val(model);
	$("#da-set-url").val(url);
	$("#da-set-key").val("");
	$("#da-set-key").attr(
		"placeholder",
		has_key ? __("Saved — leave blank to keep") : __("Paste your API key")
	);
	if (!url && provider && desk_assistant.form && desk_assistant.form.DEFAULTS[provider]) {
		$("#da-set-url").val(desk_assistant.form.DEFAULTS[provider]);
	}
};

desk_assistant.current_profile_name = function () {
	const val = $("#da-set-profile").val() || "";
	if (!val || val === "__new__") {
		return "";
	}
	return val;
};

desk_assistant.start_new_profile = function () {
	$("#da-set-profile").val("__new__");
	$("#da-set-model").val("");
	$("#da-set-key").val("");
	$("#da-set-key").attr("placeholder", __("Paste your API key"));
	const provider = $("#da-set-provider").val() || "openai";
	$("#da-set-provider").val(provider);
	desk_assistant.apply_panel_provider();
	desk_assistant.sync_header_from_panel();
};

desk_assistant.on_profile_change = function () {
	const name = $("#da-set-profile").val();
	if (name === "__new__") {
		desk_assistant.start_new_profile();
		return;
	}
	if (!name) {
		return;
	}
	frappe.call({
		method: "desk_assistant.api.sidebar.activate_profile",
		args: { profile: name },
		freeze: true,
		freeze_message: __("Switching provider…"),
		callback: function (r) {
			desk_assistant.apply_panel_payload(r.message || {});
		},
	});
};

desk_assistant.delete_panel_profile = function () {
	const name = desk_assistant.current_profile_name();
	if (!name) {
		frappe.show_alert({ message: __("Save this provider first."), indicator: "orange" });
		return;
	}
	frappe.call({
		method: "desk_assistant.api.sidebar.delete_profile",
		args: { profile: name },
		freeze: true,
		callback: function (r) {
			desk_assistant.apply_panel_payload(r.message || {});
			frappe.show_alert({ message: __("Removed saved provider."), indicator: "green" });
		},
	});
};

desk_assistant.apply_panel_provider = function () {
	const provider = $("#da-set-provider").val();
	const defaults = (desk_assistant.form && desk_assistant.form.DEFAULTS) || {};
	const fixed = defaults[provider];
	if (!fixed) {
		return;
	}
	const current = ($("#da-set-url").val() || "").replace(/\/$/, "");
	const known = Object.values(defaults)
		.concat(["http://localhost:11434/v1", "https://generativelanguage.googleapis.com/v1beta/openai"])
		.map(function (u) {
			return (u || "").replace(/\/$/, "");
		});
	if (!current || known.includes(current)) {
		$("#da-set-url").val(fixed);
	}
};

desk_assistant.panel_key = function () {
	const raw = $("#da-set-key").val() || "";
	if (desk_assistant.form && desk_assistant.form.is_dummy_key(raw)) {
		return "";
	}
	return raw;
};

desk_assistant.fetch_panel_models = function (quiet) {
	const provider = $("#da-set-provider").val();
	if (!provider) {
		return;
	}
	frappe.call({
		method: "desk_assistant.api.models.list_models",
		args: {
			provider: provider,
			base_url: $("#da-set-url").val() || "",
			api_key: desk_assistant.panel_key(),
			source: "user",
			settings_doctype: "User AI Settings",
			settings_name: frappe.session.user,
			settings_user: frappe.session.user,
			profile_name: desk_assistant.current_profile_name(),
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
			const $list = $("#da-set-models").empty();
			(msg.models || []).forEach(function (id) {
				$list.append($("<option>").attr("value", id));
			});
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

desk_assistant.sync_header_from_panel = function () {
	desk_assistant.apply_status({
		provider: $("#da-set-provider").val() || desk_assistant.boot().provider || "",
		model: $("#da-set-model").val() || desk_assistant.boot().model || "",
	});
};

desk_assistant.save_panel_settings = function () {
	const provider = $("#da-set-provider").val() || "";
	const model = $("#da-set-model").val() || "";
	const is_new = $("#da-set-profile").val() === "__new__";
	desk_assistant.apply_status({ provider: provider, model: model });
	frappe.call({
		method: "desk_assistant.api.sidebar.save_llm_settings",
		args: {
			provider: provider,
			llm_model: model,
			model: model,
			base_url: $("#da-set-url").val() || "",
			api_key: desk_assistant.panel_key(),
			profile: is_new ? "" : desk_assistant.current_profile_name(),
			as_new: is_new ? 1 : 0,
		},
		freeze: true,
		freeze_message: __("Saving…"),
		callback: function (r) {
			desk_assistant.apply_panel_payload(r.message || {});
			$("#da-set-key").val("");
			frappe.show_alert({ message: __("Settings saved."), indicator: "green" });
		},
	});
};

desk_assistant.test_panel_settings = function () {
	frappe.call({
		method: "desk_assistant.api.chat.test_connection",
		args: {
			settings_user: frappe.session.user,
			profile: desk_assistant.current_profile_name(),
		},
		freeze: true,
		freeze_message: __("Calling the model…"),
		callback: function (r) {
			const msg = r.message || {};
			const who = [msg.provider, msg.model].filter(Boolean).join(" · ");
			const reply = msg.reply || __("Connected.");
			frappe.show_alert({
				message: who ? `${who}: ${reply}` : reply,
				indicator: "green",
			});
		},
	});
};

desk_assistant.bind = function () {
	const $panel = $("#desk-assistant-panel");

	$panel.find(".da-collapse").on("click", function () {
		desk_assistant.apply_layout(desk_assistant.clamp_width(desk_assistant.current_width()), true);
	});
	$("#desk-assistant-tab").on("click", function () {
		desk_assistant.apply_layout(desk_assistant.clamp_width(desk_assistant.current_width()), false);
	});
	$panel.find(".da-wide").on("click", function () {
		const wide = Math.floor(window.innerWidth * 0.5);
		const current = desk_assistant.current_width();
		if (current >= wide - 12) {
			const restore = desk_assistant._narrow_width || desk_assistant.DEFAULT_WIDTH;
			desk_assistant._narrow_width = null;
			desk_assistant.apply_layout(restore, false);
			$panel.find(".da-wide").attr("title", __("Wide")).attr("aria-pressed", "false");
			return;
		}
		desk_assistant._narrow_width = current;
		desk_assistant.apply_layout(wide, false);
		$panel.find(".da-wide").attr("title", __("Normal width")).attr("aria-pressed", "true");
	});
	$panel.find(".da-settings").on("click", function () {
		desk_assistant.toggle_settings();
	});
	$panel.find("#da-set-profile").on("change", function () {
		desk_assistant.on_profile_change();
	});
	$panel.find(".da-add-profile").on("click", function () {
		desk_assistant.start_new_profile();
	});
	$panel.find(".da-del-profile").on("click", function () {
		desk_assistant.delete_panel_profile();
	});
	$panel.find("#da-set-provider").on("change", function () {
		desk_assistant.apply_panel_provider();
		desk_assistant.sync_header_from_panel();
		desk_assistant.fetch_panel_models(false);
	});
	$panel.find("#da-set-model").on("change input", function () {
		desk_assistant.sync_header_from_panel();
	});
	$panel.find(".da-fetch-models").on("click", function () {
		desk_assistant.fetch_panel_models(false);
	});
	$panel.find(".da-save-settings").on("click", function () {
		desk_assistant.save_panel_settings();
	});
	$panel.find(".da-test-settings").on("click", function () {
		desk_assistant.test_panel_settings();
	});
	$panel.find(".da-clear").on("click", function () {
		desk_assistant.start_new_chat();
	});
	$panel.find(".da-send").on("click", function () {
		desk_assistant.send();
	});
	$("#desk-assistant-input").on("keydown", function (e) {
		if (e.key === "Enter" && !e.shiftKey) {
			e.preventDefault();
			desk_assistant.send();
		}
	});

	desk_assistant.bind_resize($panel.find(".desk-assistant-handle"));

	if (frappe.router && frappe.router.on) {
		frappe.router.on("change", function () {
			try {
				desk_assistant.update_context();
				if (desk_assistant.session_from_route()) {
					desk_assistant.restore_session();
				}
				const path = (window.location.pathname || "").toLowerCase();
				if (path.indexOf("desk-assistant") !== -1) {
					desk_assistant.open();
				}
			} catch (e) {
				console.error(e);
			}
		});
	}
};

desk_assistant.current_width = function () {
	const raw = getComputedStyle(document.documentElement).getPropertyValue("--desk-assistant-width");
	return parseInt(raw, 10) || desk_assistant.DEFAULT_WIDTH;
};

desk_assistant.bind_resize = function ($handle) {
	let start_x = 0;
	let start_w = 0;
	const on_move = function (e) {
		const dx = start_x - e.clientX;
		desk_assistant.apply_layout(start_w + dx, false);
	};
	const on_up = function () {
		$("body").removeClass("desk-assistant-resizing");
		$(document).off("mousemove.desk_assistant mouseup.desk_assistant");
	};
	$handle.on("mousedown", function (e) {
		e.preventDefault();
		start_x = e.clientX;
		start_w = desk_assistant.current_width();
		$("body").addClass("desk-assistant-resizing");
		$(document).on("mousemove.desk_assistant", on_move);
		$(document).on("mouseup.desk_assistant", on_up);
	});
};

$(document).on("app_ready", function () {
	try {
		desk_assistant.start();
		desk_assistant.register_search();
	} catch (e) {
		console.error("Desk Assistant failed to start", e);
	}
});

if (window.frappe && frappe.app) {
	try {
		desk_assistant.start();
	} catch (e) {
		console.error("Desk Assistant failed to start", e);
	}
}
