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

The request has no address or bank account. The form marks the address block
mandatory, so the job saves with `ignore_mandatory`; `_create_erp_records`
already treats address and bank as optional. The ID Verification keeps only
Bridge's id, status, `updated_at` and endorsements (the same slice flash keeps),
not the name, email or address.

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
| `erp_party_not_found_by_mobile` | the account already has an ERP party that the approval would not find by mobile number; approving would repoint `erpParty` at a new Customer, so a human re-levels it (Account Hub) |

Accounts already at Level 2+ and Bridge customers still in review, rejected or
offboarded are not listed: that is the steady state. Nothing is ever
downgraded.

## Failures

If an approval fails, its request stays **Pending**, so it shows up in the
reviewer queue, and later runs skip that account instead of retrying it. Each
failure also writes an **Error Log** row ("Bridge KYC auto-upgrade failed for
…"). A run that upgraded or failed anything prints one summary line to the
worker's stdout.

The job only runs when the site's scheduler is enabled and a scheduler worker
is running (see hooks.py).
