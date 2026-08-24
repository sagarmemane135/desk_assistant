# Copyright (c) 2026, Desk Assistant and contributors
# For license information, please see license.txt

from frappe.model.document import Document


def ignore_blank_or_dummy_password(doc: Document, fieldname: str) -> None:
	"""Match the form copy: leave the Password field blank to keep the saved key.

	Frappe deletes __Auth when a Password field is empty on save. After Save the
	widget shows dummy stars, and some saves send an empty value instead.
	"""
	if doc.is_new():
		return
	pwd = doc.get(fieldname)
	if pwd and not doc.is_dummy_password(pwd):
		return
	ignored = doc.flags.ignore_save_passwords
	if ignored is True:
		return
	names = list(ignored) if ignored else []
	if fieldname not in names:
		names.append(fieldname)
	doc.flags.ignore_save_passwords = names
