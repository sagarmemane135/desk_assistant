// Copyright (c) 2026, Desk Assistant and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Assistant Audit Log", {
	onload(frm) {
		frm.disable_save();
	},
	refresh(frm) {
		frm.disable_save();
		frm.set_read_only();
		const ctrl = frm.fields_dict.arguments;
		if (ctrl?.editor) {
			ctrl.editor.setReadOnly(true);
			ctrl.ace_editor_target && $(ctrl.ace_editor_target).css("pointer-events", "none");
		}
	},
});
