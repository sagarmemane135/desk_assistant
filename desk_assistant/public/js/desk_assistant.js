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
				<label class="da-set-label">${__("API Key")}
					<input id="da-set-key" type="password" autocomplete="off" />
				</label>
				<div class="da-set-fetch">
					<button type="button" class="btn btn-default btn-sm da-fetch-models">${__("Fetch models")}</button>
				</div>
				<label class="da-set-label">${__("Model")}
					<input id="da-set-model" list="da-set-models" autocomplete="off" />
					<datalist id="da-set-models"></datalist>
				</label>
				<label class="da-set-label">${__("Base URL")}
					<input id="da-set-url" autocomplete="off" />
				</label>
				<p class="da-set-hint">${__("Each user has one settings document. Use + to add OpenAI, Claude, Groq, and so on, then switch with the list above.")}</p>
				<div class="da-set-actions">
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
					<button type="button" class="btn btn-default btn-sm da-stop" hidden>${__("Stop")}</button>
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
	const was_collapsed = $("#desk-assistant-panel").hasClass("is-collapsed");
	document.documentElement.style.setProperty("--desk-assistant-width", `${w}px`);
	$("body").addClass("desk-assistant-docked");
	$("body").toggleClass("desk-assistant-open", !collapsed);
	$("body").toggleClass("desk-assistant-collapsed", !!collapsed);
	$("#desk-assistant-panel").toggleClass("is-collapsed", !!collapsed);
	$("#desk-assistant-tab").toggleClass("is-visible", !!collapsed);
	desk_assistant.write_local(w, !!collapsed);
	desk_assistant.schedule_save(w, collapsed);
	if (was_collapsed && !collapsed) {
		desk_assistant.schedule_charts(true);
	}
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

desk_assistant.parse_json_silent = function (raw) {
	try {
		return JSON.parse(raw || "");
	} catch (e) {
		return {};
	}
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

desk_assistant._doc_links = desk_assistant._doc_links || {};

desk_assistant.merge_citations = function (rows) {
	(rows || []).forEach(function (row) {
		if (row && row.name && row.desk_path) {
			desk_assistant._doc_links[row.name] = row.desk_path;
		}
	});
};

desk_assistant.escape_regex = function (text) {
	return String(text || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
};

desk_assistant.DESK_PATH_TAIL = "\\(\\s*\\/(?:desk|app)\\/[^\\)]+\\)";

desk_assistant.linkify_docs = function (text) {
	let out = String(text || "");
	out = out.replace(
		/\*\*([^*]+)\*\*\s*\(\s*(\/(?:desk|app)\/[^)]+)\)/g,
		"**[$1]($2)**"
	);
	out = out.replace(
		/\[([^\]]+)\]\((\/(?:desk|app)\/[^)]+)\)\s*\(\s*\/(?:desk|app)\/[^)]+\)/g,
		"[$1]($2)"
	);
	const names = Object.keys(desk_assistant._doc_links || {}).sort(function (a, b) {
		return b.length - a.length;
	});
	names.forEach(function (name) {
		const path = desk_assistant._doc_links[name];
		if (!path || out.indexOf(name) === -1) {
			return;
		}
		const esc = desk_assistant.escape_regex(name);
		const re = new RegExp(
			"\\[" +
				esc +
				"\\]\\([^\\)]+\\)(?:\\s*" +
				desk_assistant.DESK_PATH_TAIL +
				")?" +
				"|" +
				esc +
				"(?:\\s*" +
				desk_assistant.DESK_PATH_TAIL +
				")?",
			"g"
		);
		out = out.replace(re, "[" + name + "](" + path + ")");
	});
	out = out.replace(
		/\[([^\]]+)\]\((\/(?:desk|app)\/[^)]+)\)\s*\(\s*\/(?:desk|app)\/[^)]+\)/g,
		"[$1]($2)"
	);
	return out;
};

desk_assistant.desk_href_label = function (path) {
	try {
		const parts = decodeURIComponent(String(path || ""))
			.split("/")
			.filter(Boolean);
		return parts.length ? parts[parts.length - 1] : path;
	} catch (e) {
		return path;
	}
};

desk_assistant.doc_anchor = function (href, label) {
	const path = String(href || "")
		.trim()
		.replace(/ /g, "%20");
	const text =
		label != null && String(label).trim() ? String(label) : desk_assistant.desk_href_label(path);
	const cls =
		path.indexOf("/desk/") === 0 || path.indexOf("/app/") === 0 ? ' class="desk-assistant-doc-link"' : "";
	return "<a" + cls + ' href="' + desk_assistant.escape_html(path) + '">' + text + "</a>";
};

desk_assistant.open_desk_path = function (href) {
	const url = String(href || "");
	let path = url;
	try {
		path = new URL(url, window.location.origin).pathname;
	} catch (e) {
		path = url.split("?")[0];
	}
	if (!path || (path.indexOf("/desk/") !== 0 && path.indexOf("/app/") !== 0)) {
		return false;
	}
	if (frappe.set_route) {
		frappe.set_route(path);
		return true;
	}
	window.location.href = path;
	return true;
};

desk_assistant.escape_html = function (text) {
	return $("<div>").text(text || "").html();
};

desk_assistant.format_inline = function (text) {
	let html = desk_assistant.escape_html(text);
	html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
	html = html.replace(
		/\[([^\]]+)\]\(\s*<?(\/(?:desk|app)\/[^)>]+|https?:\/\/[^)\s]+)>?\s*\)/g,
		function (_m, label, href) {
			return desk_assistant.doc_anchor(href.trim(), label);
		}
	);
	html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
	html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
	html = html.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
	html = html.replace(/\s*\(\s*\/(?:desk|app)\/[^)]+\)/g, "");
	html = html.replace(/\(\s*<a class="desk-assistant-doc-link"[^>]*>[^<]*<\/a>\s*\)/g, "");
	html = html.replace(/(^|[^"'>])(\/(?:desk|app)\/[A-Za-z0-9._~\-/%]+)/g, function (_m, prefix, path) {
		return prefix + desk_assistant.doc_anchor(path);
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

desk_assistant.CHART_TYPES = { bar: 1, line: 1, pie: 1, donut: 1 };
desk_assistant.MAX_CHART_POINTS = 16;

desk_assistant.parse_number = function (raw) {
	if (raw == null) {
		return null;
	}
	let s = String(raw).trim();
	if (!s) {
		return null;
	}
	s = s.replace(/,/g, "").replace(/[%₹$€£]/g, "");
	const n = Number(s);
	return Number.isFinite(n) ? n : null;
};

desk_assistant.parse_chart_json = function (raw) {
	const s = String(raw || "").trim();
	if (!s) {
		return null;
	}
	try {
		return JSON.parse(s);
	} catch (e) {
		const start = s.indexOf("{");
		const end = s.lastIndexOf("}");
		if (start >= 0 && end > start) {
			try {
				return JSON.parse(s.slice(start, end + 1));
			} catch (err) {
				return null;
			}
		}
	}
	return null;
};

desk_assistant.normalize_chart_spec = function (raw) {
	let spec = raw;
	if (typeof raw === "string") {
		spec = desk_assistant.parse_chart_json(raw);
	}
	if (!spec || typeof spec !== "object") {
		return null;
	}
	const type = String(spec.type || "bar").toLowerCase();
	if (!desk_assistant.CHART_TYPES[type]) {
		return null;
	}
	let labels = spec.labels;
	let values = spec.values;
	if ((!Array.isArray(values) || !Array.isArray(labels)) && spec.datasets && spec.datasets[0]) {
		values = values || spec.datasets[0].values;
		labels = labels || spec.datasets[0].labels;
	}
	if (!Array.isArray(labels) || !Array.isArray(values)) {
		return null;
	}
	const n = Math.min(labels.length, values.length, desk_assistant.MAX_CHART_POINTS);
	const max_lab = type === "pie" || type === "donut" ? 24 : 10;
	const out_labels = [];
	const out_values = [];
	for (let i = 0; i < n; i++) {
		const v = desk_assistant.parse_number(values[i]);
		if (v == null) {
			continue;
		}
		let lab = String(labels[i] == null ? "" : labels[i]).replace(/[*`<>]/g, "").trim();
		if (lab.length > max_lab) {
			lab = lab.slice(0, max_lab - 1) + "…";
		}
		out_labels.push(lab || String(i + 1));
		out_values.push(v);
	}
	if (out_values.length < 2) {
		return null;
	}
	return {
		type: type,
		title: String(spec.title || "").slice(0, 80),
		labels: out_labels,
		values: out_values,
	};
};

desk_assistant.chart_placeholder = function (spec) {
	return (
		'<div class="desk-assistant-chart" data-spec="' +
		encodeURIComponent(JSON.stringify(spec)) +
		'"></div>'
	);
};

desk_assistant.strip_chart_fences = function (text) {
	return String(text || "").replace(/```chart[^\n]*\n[\s\S]*?(```|$)/g, "\n");
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

desk_assistant._is_table_start = function (lines, i) {
	return (
		i + 1 < lines.length &&
		desk_assistant._is_table_row(lines[i]) &&
		desk_assistant._is_table_sep(lines[i + 1])
	);
};

desk_assistant._heading_match = function (line) {
	return String(line || "").match(/^(#{1,6})\s+(.+?)\s*$/);
};

desk_assistant._is_hr = function (line) {
	return /^(\*\s*){3,}$|^(-{3,})\s*$|^_{3,}\s*$/.test(String(line || "").trim());
};

desk_assistant._is_ul = function (line) {
	return /^\s*[-*+]\s+\S/.test(String(line || ""));
};

desk_assistant._is_ol = function (line) {
	return /^\s*\d+[.)]\s+\S/.test(String(line || ""));
};

desk_assistant.format_heading = function (line) {
	const m = desk_assistant._heading_match(line);
	if (!m) {
		return "";
	}
	const level = Math.min(Math.max(m[1].length, 1), 4);
	return (
		"<h" +
		level +
		' class="desk-assistant-h">' +
		desk_assistant.format_inline(m[2]) +
		"</h" +
		level +
		">"
	);
};

desk_assistant.format_markdown = function (text) {
	const lines = String(text || "").split("\n");
	const out = [];
	let i = 0;
	while (i < lines.length) {
		if (desk_assistant._is_table_start(lines, i)) {
			const block = [lines[i], lines[i + 1]];
			i += 2;
			while (i < lines.length && desk_assistant._is_table_row(lines[i])) {
				block.push(lines[i]);
				i += 1;
			}
			out.push(desk_assistant.format_table(block));
			continue;
		}
		if (desk_assistant._heading_match(lines[i])) {
			out.push(desk_assistant.format_heading(lines[i]));
			i += 1;
			continue;
		}
		if (desk_assistant._is_hr(lines[i])) {
			out.push('<hr class="desk-assistant-hr">');
			i += 1;
			continue;
		}
		if (desk_assistant._is_ul(lines[i])) {
			const items = [];
			while (i < lines.length && desk_assistant._is_ul(lines[i])) {
				items.push(
					"<li>" +
						desk_assistant.format_inline(String(lines[i]).replace(/^\s*[-*+]\s+/, "")) +
						"</li>"
				);
				i += 1;
			}
			out.push('<ul class="desk-assistant-list">' + items.join("") + "</ul>");
			continue;
		}
		if (desk_assistant._is_ol(lines[i])) {
			const items = [];
			while (i < lines.length && desk_assistant._is_ol(lines[i])) {
				items.push(
					"<li>" +
						desk_assistant.format_inline(String(lines[i]).replace(/^\s*\d+[.)]\s+/, "")) +
						"</li>"
				);
				i += 1;
			}
			out.push('<ol class="desk-assistant-list">' + items.join("") + "</ol>");
			continue;
		}
		const chunk = [];
		while (
			i < lines.length &&
			!desk_assistant._is_table_start(lines, i) &&
			!desk_assistant._heading_match(lines[i]) &&
			!desk_assistant._is_hr(lines[i]) &&
			!desk_assistant._is_ul(lines[i]) &&
			!desk_assistant._is_ol(lines[i])
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

desk_assistant.format_reply = function (text, opts) {
	const live = !!(opts && opts.live);
	const src = String(text || "");
	if (live) {
		return desk_assistant.format_markdown(
			desk_assistant.linkify_docs(desk_assistant.strip_chart_fences(src))
		);
	}
	const parts = [];
	const re = /```chart[^\n]*\n([\s\S]*?)```/g;
	let last = 0;
	let match;
	while ((match = re.exec(src))) {
		if (match.index > last) {
			parts.push({ kind: "md", text: src.slice(last, match.index) });
		}
		parts.push({ kind: "chart", json: match[1] });
		last = match.index + match[0].length;
	}
	if (last < src.length) {
		parts.push({ kind: "md", text: src.slice(last) });
	}
	if (!parts.length) {
		return desk_assistant.format_markdown(desk_assistant.linkify_docs(src));
	}
	return parts
		.map(function (part) {
			if (part.kind === "chart") {
				const spec = desk_assistant.normalize_chart_spec(part.json);
				return spec ? desk_assistant.chart_placeholder(spec) : "";
			}
			return desk_assistant.format_markdown(desk_assistant.linkify_docs(part.text));
		})
		.join("\n");
};

desk_assistant.CHART_COLORS = ["#2490ef", "#7cd6fd", "#5e64ff", "#743ee2", "#ffa00a"];

desk_assistant.chart_height = function (el, spec) {
	const w = Math.max(240, el.clientWidth || el.offsetWidth || 280);
	if (spec.type === "pie" || spec.type === "donut") {
		return Math.round(Math.min(360, Math.max(280, w * 0.85)));
	}
	return Math.round(Math.min(280, Math.max(220, w * 0.55)));
};

desk_assistant.chart_legend = function (spec) {
	const wrap = document.createElement("div");
	wrap.className = "desk-assistant-chart-legend";
	spec.labels.forEach(function (label, i) {
		const item = document.createElement("div");
		item.className = "desk-assistant-chart-legend-item";
		const swatch = document.createElement("span");
		swatch.className = "desk-assistant-chart-swatch";
		swatch.style.background = desk_assistant.CHART_COLORS[i % desk_assistant.CHART_COLORS.length];
		const name = document.createElement("span");
		name.className = "desk-assistant-chart-legend-label";
		name.textContent = label;
		const val = document.createElement("span");
		val.className = "desk-assistant-chart-legend-val";
		val.textContent = Number(spec.values[i]).toLocaleString();
		item.appendChild(swatch);
		item.appendChild(name);
		item.appendChild(val);
		wrap.appendChild(item);
	});
	return wrap;
};

desk_assistant.unmount_chart = function (el) {
	if (el && el._daChart && typeof el._daChart.destroy === "function") {
		try {
			el._daChart.destroy();
		} catch (e) {
			// ignore
		}
	}
	if (el) {
		el._daChart = null;
		el.removeAttribute("data-mounted");
	}
};

desk_assistant.chart_needs_mount = function (el, force) {
	if (!el) {
		return false;
	}
	if (force || !el.getAttribute("data-mounted")) {
		return true;
	}
	const svg = el.querySelector("svg");
	if (!svg) {
		return true;
	}
	const box = svg.getBoundingClientRect();
	if (box.height < 48) {
		return true;
	}
	const avail = el.clientWidth || el.offsetWidth;
	return avail > 80 && box.width < avail * 0.75;
};

desk_assistant.schedule_charts = function (force) {
	desk_assistant._chart_force = !!(force || desk_assistant._chart_force);
	if (desk_assistant._chart_frame) {
		return;
	}
	desk_assistant._chart_frame = requestAnimationFrame(function () {
		desk_assistant._chart_frame = null;
		const force_now = desk_assistant._chart_force;
		desk_assistant._chart_force = false;
		desk_assistant.mount_charts($("#desk-assistant-messages"), force_now);
	});
};

desk_assistant.mount_charts = function ($root, force) {
	if (!$root || !frappe.Chart) {
		return;
	}
	let retry = false;
	$root.find(".desk-assistant-chart").each(function () {
		const el = this;
		if (!el.offsetWidth) {
			retry = true;
			return;
		}
		if (!desk_assistant.chart_needs_mount(el, force)) {
			return;
		}
		let spec = null;
		try {
			spec = desk_assistant.normalize_chart_spec(
				JSON.parse(decodeURIComponent(el.getAttribute("data-spec") || ""))
			);
		} catch (e) {
			return;
		}
		if (!spec) {
			return;
		}
		desk_assistant.unmount_chart(el);
		const pie = spec.type === "pie" || spec.type === "donut";
		el.innerHTML = "";
		if (spec.title) {
			const title = document.createElement("div");
			title.className = "desk-assistant-chart-title";
			title.textContent = spec.title;
			el.appendChild(title);
		}
		const host = document.createElement("div");
		host.className = "desk-assistant-chart-host";
		el.appendChild(host);
		const draw_w = Math.max(el.clientWidth || 0, 240);
		host.style.width = draw_w + "px";
		const args = {
			title: "",
			data: {
				labels: spec.labels,
				datasets: [{ name: spec.title || " ", values: spec.values }],
			},
			type: spec.type,
			height: desk_assistant.chart_height(el, spec),
			colors: desk_assistant.CHART_COLORS,
			isNavigable: false,
			showLegend: false,
			truncateLegends: true,
			tooltipOptions: {
				formatTooltipX: function (d) {
					return d;
				},
				formatTooltipY: function (d) {
					return typeof d === "number" ? d.toLocaleString() : d;
				},
			},
		};
		if (spec.type === "bar" || spec.type === "line") {
			args.axisOptions = { xAxisMode: "tick", shortenYAxisNumbers: 1 };
			args.barOptions = { spaceRatio: spec.labels.length > 8 ? 0.45 : 0.3 };
			args.lineOptions = { hideDots: spec.labels.length > 8, regionFill: 1 };
		}
		try {
			el._daChart = new frappe.Chart(host, args);
			if (pie) {
				el.appendChild(desk_assistant.chart_legend(spec));
			}
			el.setAttribute("data-mounted", "1");
			if (host.offsetWidth < 40) {
				retry = true;
			}
		} catch (err) {
			desk_assistant.unmount_chart(el);
			retry = true;
		}
	});
	if (retry) {
		desk_assistant._chart_retries = (desk_assistant._chart_retries || 0) + 1;
		if (desk_assistant._chart_retries > 8) {
			return;
		}
		clearTimeout(desk_assistant._chart_retry);
		desk_assistant._chart_retry = setTimeout(function () {
			desk_assistant.mount_charts($("#desk-assistant-messages"), true);
		}, 120);
	} else {
		desk_assistant._chart_retries = 0;
	}
	desk_assistant.schedule_scroll();
};

desk_assistant.add_copy_button = function ($el, text) {
	$el.find(".desk-assistant-copy").remove();
	const $btn = $("<button type='button'>")
		.addClass("desk-assistant-copy btn btn-xs btn-default")
		.text(__("Copy"))
		.attr("title", __("Copy"))
		.on("click", function (e) {
			e.preventDefault();
			e.stopPropagation();
			frappe.utils.copy_to_clipboard(text || "");
		});
	$el.append($btn);
};

desk_assistant.paint_assistant = function ($el, text) {
	const body = text || "";
	$el.html(desk_assistant.format_reply(body));
	desk_assistant.add_copy_button($el, body);
	desk_assistant.schedule_charts();
};

desk_assistant.append_bubble = function (role, text) {
	desk_assistant.clear_empty();
	const $el = $("<div>").addClass("desk-assistant-bubble " + role);
	$el.appendTo("#desk-assistant-messages");
	if (role === "assistant") {
		desk_assistant.paint_assistant($el, text || "");
	} else {
		$el.text(text || "");
	}
	desk_assistant.scroll_messages();
	return $el;
};

desk_assistant.scroll_messages = function () {
	const box = document.getElementById("desk-assistant-messages");
	if (box) {
		box.scrollTop = box.scrollHeight;
	}
};

desk_assistant.schedule_scroll = function () {
	desk_assistant.scroll_messages();
	requestAnimationFrame(function () {
		desk_assistant.scroll_messages();
		setTimeout(desk_assistant.scroll_messages, 80);
		setTimeout(desk_assistant.scroll_messages, 280);
	});
};

desk_assistant.set_busy = function (busy) {
	desk_assistant._busy = !!busy;
	$(".da-send").prop("disabled", !!busy);
	$(".da-stop").prop("hidden", !busy);
	$("#desk-assistant-input").prop("disabled", !!busy);
};

desk_assistant.end_busy = function () {
	desk_assistant.set_busy(false);
	$("#desk-assistant-input").trigger("focus");
};

desk_assistant.stop = function () {
	desk_assistant.flush_typewriter();
	if (desk_assistant._abort) {
		desk_assistant._abort.abort();
	}
};

desk_assistant.reset_typewriter = function () {
	if (desk_assistant._type_timer) {
		clearTimeout(desk_assistant._type_timer);
		desk_assistant._type_timer = null;
	}
	desk_assistant._type_queue = "";
	desk_assistant._pending_finish = null;
};

desk_assistant.flush_typewriter = function () {
	if (desk_assistant._type_queue) {
		desk_assistant._stream_text += desk_assistant._type_queue;
		desk_assistant._type_queue = "";
		desk_assistant.render_stream_body();
	}
	if (desk_assistant._type_timer) {
		clearTimeout(desk_assistant._type_timer);
		desk_assistant._type_timer = null;
	}
};

desk_assistant.type_slice_len = function (q) {
	if (!q) {
		return 0;
	}
	const cap = q.length > 800 ? 28 : q.length > 280 ? 14 : 8;
	if (q.length <= cap) {
		return q.length;
	}
	const ws = q.match(/^\s+/);
	if (ws) {
		return Math.min(ws[0].length, 4);
	}
	const word = q.match(new RegExp("^[^\\s]{1," + cap + "}"));
	let n = word ? word[0].length : cap;
	if (q.charAt(n) === " ") {
		n += 1;
	}
	return n;
};

desk_assistant.render_stream_body = function () {
	if (!desk_assistant._$stream) {
		return;
	}
	desk_assistant._$stream.find(".desk-assistant-status").hide();
	desk_assistant._$stream
		.find(".desk-assistant-stream-body")
		.html(desk_assistant.format_reply(desk_assistant._stream_text, { live: true }));
	desk_assistant.scroll_messages();
};

desk_assistant.pump_type = function () {
	if (desk_assistant._type_timer) {
		return;
	}
	const tick = function () {
		desk_assistant._type_timer = null;
		const q = desk_assistant._type_queue || "";
		if (!q) {
			desk_assistant.finish_typed();
			return;
		}
		const n = desk_assistant.type_slice_len(q);
		desk_assistant._type_queue = q.slice(n);
		desk_assistant._stream_text += q.slice(0, n);
		desk_assistant.render_stream_body();
		const delay = q.length > 400 ? 8 : 16;
		desk_assistant._type_timer = setTimeout(tick, delay);
	};
	tick();
};

desk_assistant.enqueue_type = function (text) {
	desk_assistant._type_queue = (desk_assistant._type_queue || "") + (text || "");
	desk_assistant.pump_type();
};

desk_assistant.finish_typed = function () {
	const finish = desk_assistant._pending_finish;
	if (!finish) {
		return;
	}
	desk_assistant._pending_finish = null;
	desk_assistant.reset_typewriter();
	if (finish.session) {
		desk_assistant.session = finish.session;
	}
	if (finish.provider || finish.model) {
		frappe.boot.desk_assistant = Object.assign({}, desk_assistant.boot(), {
			provider: finish.provider || desk_assistant.boot().provider,
			model: finish.model || desk_assistant.boot().model,
			has_api_key: true,
		});
		desk_assistant.refresh_header();
	}
	desk_assistant.finish_stream_bubble(finish.text || desk_assistant._stream_text || "");
	desk_assistant.end_busy();
};

desk_assistant.begin_stream_bubble = function () {
	desk_assistant.reset_typewriter();
	desk_assistant.clear_empty();
	desk_assistant._stream_text = "";
	const $el = $("<div>").addClass("desk-assistant-bubble assistant is-streaming");
	$el.append($("<div>").addClass("desk-assistant-status").hide());
	$el.append($("<div>").addClass("desk-assistant-stream-body"));
	$el.appendTo("#desk-assistant-messages");
	desk_assistant._$stream = $el;
	return $el;
};

desk_assistant.finish_stream_bubble = function (text) {
	desk_assistant.reset_typewriter();
	const $el = desk_assistant._$stream;
	desk_assistant._$stream = null;
	if (!$el || !$el.length) {
		if (text) {
			desk_assistant.append_bubble("assistant", text);
		}
		return;
	}
	$el.removeClass("is-streaming");
	$el.find(".desk-assistant-status").remove();
	const body = text != null ? text : desk_assistant._stream_text || "";
	$el.find(".desk-assistant-stream-body").html(desk_assistant.format_reply(body));
	desk_assistant.add_copy_button($el, body);
	desk_assistant.schedule_charts(true);
	desk_assistant.schedule_scroll();
};

desk_assistant.apply_stream_event = function (event) {
	if (!event || !event.type) {
		return;
	}
	if (event.type === "session" && event.session) {
		desk_assistant.session = event.session;
		return;
	}
	if (event.type === "status") {
		desk_assistant.reset_typewriter();
		if (!desk_assistant._$stream) {
			desk_assistant.begin_stream_bubble();
		}
		desk_assistant._stream_text = "";
		desk_assistant._$stream.find(".desk-assistant-stream-body").empty();
		desk_assistant._$stream
			.find(".desk-assistant-status")
			.text(event.text || "")
			.show();
		desk_assistant.scroll_messages();
		return;
	}
	if (event.type === "delta") {
		if (!desk_assistant._$stream) {
			desk_assistant.begin_stream_bubble();
		}
		desk_assistant.enqueue_type(event.text || "");
		return;
	}
	if (event.type === "done") {
		desk_assistant.merge_citations(event.citations);
		desk_assistant._pending_finish = {
			text: event.message || desk_assistant._stream_text || "",
			session: event.session,
			provider: event.provider,
			model: event.model,
		};
		desk_assistant.pump_type();
		return;
	}
	if (event.type === "error") {
		desk_assistant.reset_typewriter();
		desk_assistant.finish_stream_bubble(
			event.message || __("Could not send. Check your key in User AI Settings.")
		);
	}
};

desk_assistant.send = function () {
	if (desk_assistant._busy) {
		return;
	}
	const $input = $("#desk-assistant-input");
	const text = ($input.val() || "").trim();
	if (!text) {
		return;
	}
	$input.val("");
	desk_assistant.append_bubble("user", text);
	if (window.fetch) {
		desk_assistant.send_stream(text);
	} else {
		desk_assistant.send_full(text);
	}
};

desk_assistant.send_full = function (text) {
	desk_assistant.set_busy(true);
	frappe.call({
		method: "desk_assistant.api.chat.send",
		args: {
			message: text,
			session: desk_assistant.session || "",
			context: JSON.stringify(desk_assistant.get_context()),
		},
		callback: function (r) {
			const msg = (r.message && r.message.message) || __("No reply from the model.");
			if (r.message && r.message.session) {
				desk_assistant.session = r.message.session;
			}
			desk_assistant.merge_citations(r.message && r.message.citations);
			desk_assistant.append_bubble("assistant", msg);
			if (r.message && (r.message.provider || r.message.model)) {
				frappe.boot.desk_assistant = Object.assign({}, desk_assistant.boot(), {
					provider: r.message.provider || desk_assistant.boot().provider,
					model: r.message.model || desk_assistant.boot().model,
					has_api_key: true,
				});
				desk_assistant.refresh_header();
			}
			desk_assistant.set_busy(false);
			$("#desk-assistant-input").trigger("focus");
		},
		error: function (r) {
			desk_assistant.append_bubble("assistant", desk_assistant.error_text(r));
			desk_assistant.set_busy(false);
		},
	});
};

desk_assistant.send_stream = function (text) {
	desk_assistant.set_busy(true);
	desk_assistant.begin_stream_bubble();
	const controller = new AbortController();
	desk_assistant._abort = controller;
	let fallback = false;
	const body = new URLSearchParams();
	body.set("message", text);
	body.set("session", desk_assistant.session || "");
	body.set("context", JSON.stringify(desk_assistant.get_context()));
	fetch("/api/method/desk_assistant.api.chat.stream", {
		method: "POST",
		credentials: "same-origin",
		signal: controller.signal,
		headers: {
			Accept: "application/x-ndjson",
			"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
			"X-Frappe-CSRF-Token": frappe.csrf_token || "",
			"X-Requested-With": "XMLHttpRequest",
		},
		body: body.toString(),
	})
		.then(function (res) {
			const ctype = (res.headers.get("content-type") || "").toLowerCase();
			if (res.ok && ctype.indexOf("ndjson") !== -1) {
				return desk_assistant.read_ndjson(res);
			}
			return res.text().then(function (raw) {
				if (!res.ok && res.status !== 404) {
					const parsed = desk_assistant.error_text({
						responseJSON: desk_assistant.parse_json_silent(raw),
						message: raw,
					});
					throw new Error(parsed);
				}
				const err = new Error("stream-fallback");
				err._fallback = true;
				throw err;
			});
		})
		.catch(function (err) {
			if (err && err.name === "AbortError") {
				desk_assistant.flush_typewriter();
				desk_assistant.finish_stream_bubble(desk_assistant._stream_text || __("Stopped."));
				return;
			}
			if (err && err._fallback) {
				fallback = true;
				desk_assistant.send_full(text);
				return;
			}
			const msg =
				(err && err.message) || __("Could not send. Check your key in User AI Settings.");
			desk_assistant.reset_typewriter();
			if (desk_assistant._$stream) {
				desk_assistant.finish_stream_bubble(msg);
			} else {
				desk_assistant.append_bubble("assistant", msg);
			}
		})
		.finally(function () {
			desk_assistant._abort = null;
			if (fallback) {
				return;
			}
			if (desk_assistant._type_queue || desk_assistant._pending_finish) {
				return;
			}
			desk_assistant.end_busy();
		});
};

desk_assistant.read_ndjson = function (res) {
	const reader = res.body && res.body.getReader ? res.body.getReader() : null;
	if (!reader) {
		return res.text().then(function (raw) {
			desk_assistant.consume_ndjson_chunk(raw, true);
		});
	}
	const decoder = new TextDecoder();
	let buf = "";
	const pump = function () {
		return reader.read().then(function (result) {
			if (result.value) {
				buf += decoder.decode(result.value, { stream: !result.done });
			}
			buf = desk_assistant.consume_ndjson_chunk(buf, !!result.done);
			if (!result.done) {
				return pump();
			}
		});
	};
	return pump();
};

desk_assistant.consume_ndjson_chunk = function (buf, flush) {
	const parts = String(buf || "").split("\n");
	const rest = flush ? "" : parts.pop();
	if (flush && parts.length && parts[parts.length - 1] === "") {
		parts.pop();
	}
	parts.forEach(function (line) {
		const trimmed = line.trim();
		if (!trimmed) {
			return;
		}
		try {
			desk_assistant.apply_stream_event(JSON.parse(trimmed));
		} catch (e) {
			console.error(e);
		}
	});
	return rest || "";
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
	desk_assistant._doc_links = {};
	desk_assistant.merge_citations(payload.citations);
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
	desk_assistant.schedule_charts(true);
	desk_assistant.schedule_scroll();
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
	desk_assistant.stop();
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
	$panel.find(".da-stop").on("click", function () {
		desk_assistant.stop();
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

	$("#desk-assistant-messages").on("click", "a[href^='/desk/'], a[href^='/app/']", function (e) {
		if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.which === 2) {
			return;
		}
		e.preventDefault();
		desk_assistant.open_desk_path(this.getAttribute("href") || "");
	});

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
		desk_assistant.schedule_charts(true);
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
