// Copyright (c) 2026, Desk Assistant and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Chat Session", {
	refresh(frm) {
		frm.set_df_property("messages", "read_only", 1);
		const grid = frm.fields_dict.messages?.grid;
		if (!grid) {
			return;
		}
		grid.cannot_add_rows = true;
		grid.cannot_delete_rows = true;
		grid.refresh();
		const payload = grid.grid_rows?.[0]?.docfields?.find((df) => df.fieldname === "tool_payload");
		if (payload) {
			payload.read_only = 1;
		}
	},
});
