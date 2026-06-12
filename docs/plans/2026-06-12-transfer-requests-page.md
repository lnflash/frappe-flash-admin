# Transfer Requests Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Cashout Requests custom page link with a unified Transfer Requests page for Cashout requests and Bridge transfer audits.

**Architecture:** Keep Cashout as the actionable workflow and add Bridge as a read-only audit tab. The Admin Dashboard and Admin Panel workspace route to `/app/transfer-requests`; raw Cashout and Bridge DocType links remain available in the workspace.

**Tech Stack:** Frappe custom Page JavaScript, Frappe whitelisted Python APIs, JSON workspace/page fixtures, pytest static contract tests.

---

### Task 1: Add Route And Page Contract Tests

**Files:**
- Create: `admin_panel/tests/test_transfer_requests_page_contract.py`

**Steps:**
1. Write tests asserting the dashboard card routes to `/app/transfer-requests`.
2. Write tests asserting `setup.py` and the Page JSON register `transfer-requests`, not `cashout-requests`.
3. Write tests asserting the workspace keeps Cashout and Bridge DocType links but does not expose a Cashout Requests Page link.
4. Run the tests and verify they fail before implementation.

### Task 2: Rename The Custom Page

**Files:**
- Move: `admin_panel/admin_panel/page/cashout_requests/` to `admin_panel/admin_panel/page/transfer_requests/`
- Modify: `admin_panel/admin_panel/setup.py`
- Modify: `admin_panel/admin_panel/page/transfer_requests/transfer_requests.json`
- Modify: `admin_panel/admin_panel/page/transfer_requests/transfer_requests.js`

**Steps:**
1. Rename file paths and Frappe page key to `transfer-requests`.
2. Rename visible title to `Transfer Requests`.
3. Keep the Cashout table/action behavior working under the Cashouts tab.

### Task 3: Add Bridge Read-Only Requests

**Files:**
- Modify: `admin_panel/api/admin_api.py`
- Modify: `admin_panel/admin_panel/page/transfer_requests/transfer_requests.js`

**Steps:**
1. Add `get_bridge_transfer_requests(status=None, transaction_type=None, page=1, page_size=10)`.
2. Query `Bridge Transfer Request` with stable fields and newest-first pagination.
3. Add Bridge tab rendering, status filtering, row selection, and detail display.
4. Do not add Bridge mutation actions in this PR.

### Task 4: Update Entry Points

**Files:**
- Modify: `admin_panel/admin_panel/page/admin_dashboard/admin_dashboard.js`
- Modify: `admin_panel/fixtures/workspace.json`

**Steps:**
1. Route the Admin Dashboard Transfer Requests card to `/app/transfer-requests`.
2. Replace the workspace Cashout Requests Page link with a Transfer Requests Page link.
3. Keep existing Cashout and Bridge Transfer Request DocType links.

### Task 5: Verify And Commit

**Commands:**
- `pytest admin_panel/tests/test_transfer_requests_page_contract.py -q`
- `python -m py_compile admin_panel/api/admin_api.py`
- Frappe migrate/clear-cache in the local container if available

Commit the passing implementation and push to `feat/cashout-requests-page`.
