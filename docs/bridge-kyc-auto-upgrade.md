# Bridge KYC → Level 2 auto-upgrade

Policy (2026-10-06): a Flash account whose Bridge customer has passed KYC has a
verified identity, and that is enough for Level 2. A scheduled job applies it.

## What it does

Every 15 minutes, while both switches below are on, the job finds each Flash
account that is linked to a Bridge customer and:

- the Bridge customer's **live** status is `active` (Bridge is the source of
  truth, not the status flash stored),
- the Bridge customer is an **individual**,
- the account is at Level 0 or 1 and active.

For each one it files an **Account Upgrade Request** (Level 2) and an **ID
Verification** with `identity_source = bridge_kyc`, then approves the request
with `approve_upgrade_request(..., reason_code="APPROVE_BRIDGE_KYC")`: the same
approval a reviewer clicks. That approval:

- creates the ERP **Customer** from the request (Bridge's verified legal name,
  the account's phone and email), or reuses one with the same mobile number,
  and passes it to flash as `erpParty`, which flash requires for Level 2;
- stamps the decision on the request and mirrors it onto the ID Verification;
- writes the `upgrade_approved` ledger event.

Flash then posts the level change to the ops feed. Scheduled approvals are
stamped as reviewed by the scheduler's session user (Administrator).

The request has no address or bank account. The request's address fields are
required only for Level 3, and only in the desk form (`mandatory_depends_on`);
frappe enforces static `reqd` on every save, so a required address would make
every later save of the request fail: this approval, a reviewer's reject, the
Account Hub's phone sync, and flash closing a user's pending requests. Flash's
API still requires an address on every request a customer submits.
`_create_erp_records` already treats address and bank as optional, and with no
`address_title` the Customer is created as an Individual.

The ID Verification keeps only Bridge's id, status, `updated_at` and endorsements
(the same slice flash keeps), not the name, email or address. Why the request
exists goes in its internal `reviewer_note`, not the request's `support_note`,
which the reviewer pages show as "Rejection Reason".

## Switches (ID Verification Settings)

| Field | Default | Effect |
|---|---|---|
| Bridge KYC Satisfies Identity | on | Prerequisite. Saving the auto-upgrade on while this is off is refused. |
| Auto-Upgrade Bridge KYC to Level 2 | **off** | Runs the job. Off makes the job a no-op that reads nothing. |

Changing either one is a ledger event (`idv_settings_changed`).

The first run after switching on catches up on existing accounts, at most
**25 per run**. Anything over that is picked up by the following runs.

## Who is skipped, and why

`preview_bridge_kyc_upgrades()` returns the candidates and the skips without
writing anything:

```
bench --site <site> execute admin_panel.api.bridge_kyc_upgrade.preview_bridge_kyc_upgrades
```

| reason | meaning |
|---|---|
| `pending_upgrade_request` | the user already has a Pending request; a reviewer owns it |
| `business_customer` | Bridge KYB customer: a Level 3 conversation, not Level 2 |
| `bridge_customer_linked_to_multiple_accounts` | one verified person, several Flash accounts; none is upgraded |
| `account_not_active` | locked, closed or otherwise not active |
| `missing_at_bridge` | the stored Bridge customer id is not in Bridge's list |
| `no_username` | the account has no username |
| `no_phone` / `no_legal_name` | the live re-check found no phone, or Bridge has no name |
| `already_level_two_or_above` | the live re-check found the account already upgraded |
| `failed_in_the_last_day` | its upgrade failed less than 24 hours ago; retried once that passes |
| `erp_party_not_found_by_mobile` | the account already has an ERP party that the approval would not find by mobile number; approving would repoint `erpParty` at a new Customer, so a human re-levels it (Account Hub) |

Accounts already at Level 2+ and Bridge customers still in review, rejected or
offboarded are not listed: that is the steady state. Nothing is ever
downgraded.

## Failures

Nothing is committed until the approval commits it. When an approval fails:

- **Flash is still below Level 2** (the common case: the flash lookup, the ERP
  records or the level change failed): everything is rolled back. The user is
  left with no request they never filed (the app would show it as pending and
  could not dismiss it) and no orphan Customer. The account is retried after 24
  hours.
- **Flash already moved, or cannot be read to tell**: the records are kept,
  because flash's `erpParty` may now name the new Customer. The request stays
  **Pending** for a reviewer, who can approve or reject it.

Each failure writes an **Error Log** row ("Bridge KYC auto-upgrade failed for
…", referencing the request when one was kept), committed on its own so a later
rollback cannot remove it. A run that upgraded or failed anything prints one
summary line to the worker's stdout.

Reviewers: don't use *Resubmit* on a request whose ID Verification has
`identity_source = bridge_kyc`. The app's resubmit path sends the customer
through a form that needs an address this request never had. Approve or reject
it instead. Scheduled approvals count toward reviewer throughput on the
dashboards, stamped as Administrator.

The job only runs when the site's scheduler is enabled and a scheduler worker
is running (see hooks.py).
