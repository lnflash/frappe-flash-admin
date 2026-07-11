# Wallet Census (ENG-487)

An operator-facing admin page that answers the questions that required
hand-rolled mongo queries plus IBEX jumpbox scripts during the USDT cutover:

- Which accounts hold money? (sortable funded list, one-click CSV export)
- What is the total USD / USDT float?
- Who is a given funded account, and what state is its migration in?

## What it does

`Admin Panel > Wallet Census` (role: `Accounts Manager` / `Flash Admin` /
`System Manager`).

The full scan pages through **every** IBEX org account and reads its live
balance. That takes several minutes, so it runs as a **background job** that
writes a `Wallet Census Snapshot` DocType. The page shows the latest snapshot
and a **Run Census** button; while a run is in flight it polls for progress.

### Views

- **Summary cards** — USD float, USDT float, total accounts (funded / zero),
  BTC wallet count.
- **Bucket tabs** — `Active + Funded`, `Active + Zero`, `Closed w/ Dust`,
  `Migrated`, `System` (dealer / bankowner / funder), `Non-default Wallet`
  (funded on a wallet that isn't the account's default — an anomaly). Buckets
  are overlapping tags: a migrated account can also be active + funded.
- **Sortable table** — click any header; default sort is balance descending.
- **CSV export** — exports the currently filtered/sorted view, client-side.

## Operational notes

- **Stale runs** — a `Running` snapshot whose worker died (deploy, OOM, kill)
  would otherwise block new scans forever. The next start marks any `Running`
  snapshot older than 45 minutes (`STALE_RUN_SECONDS`) as `Failed` and starts
  fresh.
- **Retention** — only the last 20 snapshots are kept (`KEEP_SNAPSHOTS`);
  older ones are purged **permanently** after each successful run, since
  `rows_json` holds the full per-account table.
- **`run_census_now`** — synchronous variant for deployments without a `long`
  worker (local docker-compose, smoke tests). Deliberately **not whitelisted**
  — bench-execute / console only — because it blocks the caller for the full
  scan. The page always goes through the queued `start_census`.
- **Table paging vs CSV** — the table renders 200 rows at a time (**Show
  more** / **Show all** to expand), but **Export CSV** always exports the full
  filtered set regardless of how many rows are rendered.
- **Access** — the page is gated to the `Accounts Manager`, `Flash Admin`,
  and `System Manager` roles (plus `Administrator`).

## Data sources

This page talks **directly** to IBEX and the customer MongoDB (it does not go
through the Flash GraphQL admin API, which has no bulk-list or migration-state
query).

### IBEX Hub API — bulk balances

- Auth: OAuth2 **client-credentials** (not email/password). Token from
  `POST {auth_domain}/oauth/token` (`grant_type=client_credentials`,
  `audience`). The hub expects the token as a **raw** `Authorization` header
  value — no `Bearer` prefix.
- Bulk list: `GET {hub_url}/v2/account?expand=true&page=N&limit=100`. `expand`
  is required for balances to appear; balances are in **dollars** and are
  absent when zero.
- IBEX only custodies USD (`currencyId 3`) and USDT (`currencyId 29`). BTC is
  on the Lightning side and is **not** returned here — BTC wallets are counted
  but their balance is reported as `null`, intentionally.
- The scan paces ~1 req/s and refetches the token once on a `401`.
- **Prod caps the page size silently**: requesting `limit=100` returns 25 rows
  (sandbox honors 100). Pagination therefore terminates only on an **empty
  page**, never on a short one — a short-page inference truncated the first
  prod census to 25 of ~8,750 accounts.

### Customer MongoDB (`galoy`)

Read-only joins against three collections:

| Collection             | Used for                                   |
| ---------------------- | ------------------------------------------ |
| `wallets`              | currency, type, wallet→account link        |
| `accounts`             | username, level, status, role, default wallet |
| `cashwalletmigrations` | migration status / runId per account       |

**Join keys** (verified in prod):

```
IBEX account.id   == wallets.id
IBEX account.name == str(accounts._id) == str(wallets._accountId)
                  == cashwalletmigrations.accountId
```

Note: `accounts` has no flat `status` field (it's the last entry of
`statusHistory`) and no `accountId` field (the join value is the `_id`
ObjectId).

## Configuration

Add to the site's `site_config.json` (`frappe.conf`):

```json
{
  "ibex_client_id": "…",
  "ibex_client_secret": "…",
  "customer_mongo_uri": "mongodb://user:pass@flash-mongodb:27017/galoy"
}
```

Optional:

- `ibex_environment` — `"production"` (default) or `"sandbox"`. Both have their
  URLs baked in, so sandbox only needs `ibex_environment: "sandbox"` plus
  sandbox `ibex_client_id` / `ibex_client_secret`.
- `ibex_auth_domain`, `ibex_hub_url`, `ibex_audience` — per-field overrides for
  a bespoke staging setup.
- `customer_mongo_db` — defaults to `"galoy"`.

The `customer_mongo_uri` value is the same connection string the Flash backend
uses as `MONGODB_CON`. **It is optional:** if unset, the census runs from IBEX
alone (totals + balances work; rows lack username / status / migration state).
Useful for an IBEX-only sandbox smoke test.

### Local sandbox smoke test

```bash
# from the bench dir (…/frappe-bench-v15)
env/bin/pip install "pymongo>=4.6,<5"          # new dep; workers need it too
bench --site flashapp.me.localhost set-config ibex_environment sandbox
bench --site flashapp.me.localhost set-config ibex_client_id     <sandbox-id>
bench --site flashapp.me.localhost set-config ibex_client_secret <sandbox-secret>
# (optional) point at a sandbox galoy mongo to get the join:
# bench --site flashapp.me.localhost set-config customer_mongo_uri "mongodb://…/galoy"
bench --site flashapp.me.localhost migrate      # creates the DocType + page
bench build --app admin_panel && bench --site flashapp.me.localhost clear-cache
bench start
```

Then open `/app/wallet-census`, click **Run Census**, and watch the worker log
(`tail -f logs/worker.log`). The user needs the `Accounts Manager` role (same
gate as Account Hub).

## Code map

| File                                    | Purpose                                        |
| --------------------------------------- | ---------------------------------------------- |
| `admin_panel/api/census_core.py`        | Pure join / bucket / totals (`build_census`) — no IO, unit-tested |
| `admin_panel/api/ibex_client.py`        | IBEX Hub client (client-credentials, bulk list) |
| `admin_panel/api/mongo_reader.py`       | Read-only mongo loaders (pymongo)              |
| `admin_panel/api/census.py`             | Whitelisted endpoints + background job         |
| `admin_panel/.../doctype/wallet_census_snapshot/` | Snapshot storage                     |
| `admin_panel/.../page/wallet_census/`   | The page (JS)                                  |
| `admin_panel/tests/test_census_core.py` | Unit tests for the census logic                |

## Testing / verification

All correctness risk lives in `build_census`, which is a pure function and is
unit-tested against fixtures covering every bucket and edge case
(`pytest admin_panel/tests/test_census_core.py`). The IBEX/mongo/page wiring is
exercised end-to-end only against a live Frappe site with the config above set —
it cannot run offline because it needs the production IBEX client-credentials
and the in-cluster mongo URI.
