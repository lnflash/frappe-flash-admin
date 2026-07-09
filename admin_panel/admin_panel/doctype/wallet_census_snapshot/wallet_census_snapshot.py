# Copyright (c) 2026, Flash and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WalletCensusSnapshot(Document):
	"""A single run of the bulk wallet-balance census.

	Populated by the `admin_panel.api.census.run_census_job` background job.
	The heavy join/bucket payload is stored as JSON in the *_json fields; the
	scalar summary fields exist for list-view browsing.
	"""

	pass
