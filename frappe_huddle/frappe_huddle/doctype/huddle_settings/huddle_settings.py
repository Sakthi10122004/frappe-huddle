# Copyright (c) 2026, Sakthi and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HuddleSettings(Document):
	def validate(self):
		self._validate_livekit_url()

	def _validate_livekit_url(self):
		"""Clean up the LiveKit URL (strip trailing slashes)."""
		if self.livekit_url:
			self.livekit_url = self.livekit_url.strip().rstrip("/")
