# Cashout Requests Page Implementation Plan

> **Goal:** Wire Nodirbek75's Cashout Requests UI (PR #19) to the real Cashout doctype and get it merged.

**Architecture:** The JS page and API shell exist from PR #19 but use DUMMY data. The Cashout doctype (PR #27, merged) has the real data model. We need to: (1) update the doctype statuses to match the support view, (2) replace API methods with real doctype queries, (3) update the JS field names, (4) fix workspace/setup.

**Tech Stack:** Frappe ERPNext, JavaScript, Python

---

### Task 1: Add support-view statuses to Cashout doctype

- `cashout.json`: add "Pending", "Canceled" to status options
- Keep existing "Draft", "In Progress", "Completed" — just append

### Task 2: Rewrite admin_api.py cashout methods

- `get_cashout_requests()` → query Cashout doctype with Customer/Bank Account joins
- `search_cashout_account()` → search via Customer name/phone  
- `record_cashout_payment()` → call `create_payment_journal_entry`

### Task 3: Update cashout_requests.js to use real doctype fields

- Copy from origin/feat/cashout
- Map field names: send→user_pays, receive_jmd→user_receives (conditional on currency), etc.
- Resolve Customer/Bank Account fields via linked docs
- Update status badge mapping

### Task 4: Fix page registration and workspace shortcuts

- `setup.py` → already has cashout-requests (verify)
- `workspace.json` → add cashout-requests link
- `cashout_requests.json` → verify page definition

### Task 5: Commit, push, and open PR
