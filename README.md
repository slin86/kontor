# Kontor

Household finance planner: cashflow with Sankey views, financings and savings contracts,
and a long-range depot projection with plan-vs-actual comparison.

Self-hosted, built for a homelab.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Backend skeleton, accounts (households with several members), Docker, CI | this branch |
| 2 | Cashflow: income/expenses (monthly, quarterly, yearly), timeline, Sankey and charts | this branch |
| 3 | Financings, building-society savings contracts (Bausparvertrag), loans, household budget forecast | this branch |
| 4 | Depot plan: savings rates, dated rate changes, one-off payments, scenarios, history | this branch |
| 5 | Instrument search (ETF / private equity), costs, cost comparison | this branch |
| 6 | Actual values, plan vs. actual, broker CSV import (Trade Republic), deleting positions and financings | this branch |
| 7 | Tax estimate for the depot projection (Abgeltungsteuer, Vorabpauschale, Teilfreistellung) | this branch |

## Design principles

- **Households, not single users.** One registration creates a household; further members join with
  the household invite code. All financial data belongs to the household.
- **History is immutable, the future is editable.** Planning data is effective-dated
  (`valid_from` / `valid_to`, append-only). Changing a value closes the current version at the
  effective date and creates a new one. Past months are locked; corrections are an explicit action
  with a reason and an audit trail.
- **Money is `Decimal`** in the database and in all calculations. API responses expose plain numbers
  (rounded to cents) because they feed charts; inputs are parsed as exact decimals.
- **Pure calculation core.** Cashflow aggregation, loan amortisation and depot projection are pure
  functions, tested independently from HTTP and the database.
- **Household budget outlook.** Every financing/contract has an end date, so the projected free
  monthly budget is shown over the years as loans and savings contracts run out.

## Cashflow

- Categories form a two-level tree per household; a default German set is created on registration.
- An item (e.g. "Rent") has **versions**: amount and frequency (monthly, quarterly, yearly) valid from a
  month up to, but excluding, another month. Amounts are normalised to a monthly equivalent.
- **Change from month X**: cuts the version covering X and starts a new one; already planned later
  changes are kept. Only the current month or later is allowed.
- **End from month X**: the item no longer applies from X on.
- **Locked history**: months before the current month cannot be changed with the calls above (HTTP 409).
  A **correction** fixes the amount of a version in place and requires a reason; every change, backfill
  and correction is written to the audit log.
- Views: monthly summary, Sankey (income sources -> household -> expense groups -> sub-categories, plus
  surplus or shortfall), month series (also used for the outlook when items end) and expense shares.

Not covered yet: correcting the *dates* of a version, deleting items, renaming/deleting categories in the UI.

## Financings and budget outlook

- **Loan** (real estate, car, consumer, ...): amount, annual rate, first month and either a fixed monthly
  payment or an initial repayment percentage (payment = amount x (rate + repayment) / 12). Interest accrues
  monthly on the remaining balance (annuity loan).
- **Bausparvertrag**: saving phase (monthly contribution, interest credited each December, one-off
  Abschlussgebuehr), allocation month, then a loan phase with its own rate and payment.
- **Events** from the current month on: special repayment, payment change, rate change. Past events are
  locked (409); contract data can be corrected with a reason and is audited.
- The cashflow summary, Sankey (financings -> contract -> interest / principal / saving / fees) and series
  include the financings automatically.
- **Outlook** (`GET /api/outlook`): the free monthly budget (income - expenses - financings) for up to 50
  years, with events for ending financings and items and optional yearly income/expense growth. One-off
  special repayments are left out so the curve shows the regular budget.

Not covered yet: deleting a financing, scenarios with several interest paths.

## Depot plan

- A **position** is an ETF or a private-equity holding with an expected annual return, running costs (TER),
  an optional entry fee, a start month and the value it already has at the start.
- Every position has its own **savings rate** (effective-dated like cashflow items: change from month X,
  later planned changes are kept, 0 pauses saving) and **one-off payments** (deposits or withdrawals).
  The **depot base rate** is the sum of all current rates.
- Projection: each month the balance grows by `(1 + return - cost)^(1/12) - 1`, then the savings rate and
  one-offs are added (minus the entry fee). It runs for up to 100 years and starts at the earliest
  position, so the past is visible too. Withdrawals larger than the balance are rejected.
- Scenarios shift every position's return by a number of percentage points; optional inflation shows
  values in today's purchasing power.
- Locking works as elsewhere: the plan for past months cannot be changed. Start month and start value can be
  corrected with a reason; every change is in the audit log.

Not covered yet: tax, actual values (plan vs. actual), instrument search and cost comparison,
CSV import, deleting positions.

## Instrument catalog

- Built-in reference data: 59 widely used UCITS ETFs (MSCI World, S&P 500, FTSE All-World, MSCI ACWI,
  MSCI Emerging Markets) with TER, distribution policy, replication, domicile and fund size.
  Source: justETF comparison tables, as of 2026-10 (`backend/src/kontor/data/etf_catalog.json`).
  Costs and sizes change, so verify them with the provider before buying.
- Search by name, ISIN or index with filters (index, distribution, replication, maximum TER) and sorting.
- Households can add their own entries, e.g. private-equity funds. Only the household sees them.
- **Cost comparison**: all selected funds get the same gross return and savings plan, so the difference in
  final value comes from the TER alone.
- "Adopt into the depot plan" prefills a new position (name, ISIN, TER). A position with a known ISIN can
  take over the catalog's TER and jump to the comparison.

Not covered yet: automatic data updates, tracking difference, live prices.

## Plan vs. actual and broker import

- **Month-end values**: enter what a position was worth at the end of a month (up to the current month).
  The current month can always be changed; overwriting a closed month needs a reason and is audited.
- **Transactions**: buys, sells and dividends, entered by hand or imported. They feed the comparison of
  planned and real net deposits per month.
- **Comparison**: the plan is shown for the positions that have actual values (so both lines cover the same
  money), per position with the deviation in euros and percent. Months where a tracked position has no
  value show no actual point.
- **CSV import** (built for Trade Republic's transaction export): upload, preview, optionally map unknown
  ISINs to a position, then import. Only securities orders, savings plans and dividends are taken over;
  other rows (card payments, deposits, interest, corporate actions) are counted and reported. Re-importing
  a file is safe: rows are deduplicated by transaction id (or a stable hash when the file has none).
  The parser accepts commas or semicolons, ISO or German dates and German or English number formats.
  The real export format is not officially documented, so check the preview before importing.
- Positions and financings can be deleted (audited). Transactions of a deleted position stay, unlinked.

Not covered yet: live prices, importing month-end values from a statement.

## Tax estimate

The depot projection shows a second line, **after tax if everything were sold in that month**. It is an
approximation of German capital gains tax, not tax advice. Rules and rates change, so check them.

- **Rate**: 25 % plus 5.5 % solidarity surcharge (26.375 %). With church tax (8 % or 9 %) the base rate
  drops to `25 % / (1 + 25 % * church rate)`, giving about 27.8 % or 28.0 %.
- **Sparer-Pauschbetrag**: 1,000 euro per year (2,000 for couples), applied once per year to the whole depot.
- **Teilfreistellung** per position: share of gains that is tax free (30 % equity funds, 15 % mixed funds,
  0 % bond funds). Defaults: 30 for ETFs, 0 for private equity. Change it per position.
- **Vorabpauschale** (accumulating funds): taxed each January for the previous year, as
  `value * Basiszins * 70 %`, every purchase counting only for the months held, capped at the fund's real gain.
  Basiszins: 2023 2.55 %, 2024 2.29 %, 2025 2.53 %, 2026 3.20 %, later years use your assumption (default 3.2 %).
  The tax is assumed to be paid from outside the depot and is credited at sale, so gains are not taxed twice.
- **Tax on sale**: gains minus the Vorabpauschalen already taxed, less Teilfreistellung and allowance.
  Gains and losses of all positions are netted.

Simplifications: planned withdrawals are not taxed individually, distributions are not modelled, no
Verlustverrechnungstöpfe, no further income that uses up the allowance, tax on ETF-specific rules for
special funds is not covered. Settings (church tax, allowance, Basiszins) are per household.

## Frontend

React, Vite, TypeScript, Tailwind and Apache ECharts. Fonts are bundled locally (no external requests).

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to http://localhost:8000
npm run build && npm run lint
```

## Backend

Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL (SQLite for tests and quick local runs).

```bash
cd backend
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .

# local dev server with SQLite
uv run alembic upgrade head
uv run uvicorn kontor.main:app --reload
```

### Authentication

- E-mail + password, hashed with Argon2. No e-mail is sent yet; verification and password reset
  are intentionally left for a later phase.
- Opaque session token in an `HttpOnly` cookie; only its SHA-256 digest is stored.
- CSRF protection: a second, JS-readable cookie must be echoed in the `X-CSRF-Token` header on
  every non-safe request.

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/register` | Create a household (`household_name`) **or** join one (`invite_code`) |
| `POST /api/auth/login` | Start a session |
| `POST /api/auth/logout` | End the session (needs CSRF header) |
| `GET /api/auth/me` | Current user and household |
| `GET /api/health` | Liveness |

Cashflow endpoints (all need a session, mutating calls need the CSRF header):

| Endpoint | Description |
|----------|-------------|
| `GET/POST /api/categories` | List / create categories |
| `GET /api/cashflow/items?month=YYYY-MM` | Items valid in a month (`include_inactive=true` for all) |
| `POST /api/cashflow/items` | Create an item (a start in a closed month is logged as backfill) |
| `POST /api/cashflow/items/{id}/change` | New amount from a month on |
| `POST /api/cashflow/items/{id}/end` | End an item from a month on |
| `POST /api/cashflow/versions/{id}/correct` | Correct a version in place (reason required) |
| `GET /api/cashflow/summary` / `sankey` | Aggregates for one month |
| `GET /api/cashflow/series?from=&to=` | Income, expenses and balance per month |
| `GET /api/audit` | Audit log |
| `GET/POST /api/financings` | List / create loans and Bauspar contracts |
| `GET /api/financings/{id}` | Contract data, schedule and events |
| `POST /api/financings/{id}/correct` | Correct contract data (reason required) |
| `POST /api/financings/{id}/events`, `DELETE .../events/{event_id}` | Add / remove a dated event |
| `GET /api/outlook?start=&years=&income_growth=&expense_growth=` | Budget outlook |
| `GET /api/depot` | Base rate, planned value and all positions |
| `POST /api/depot/instruments`, `GET/PUT .../{id}` | Create a position, read it, change its assumptions |
| `POST /api/depot/instruments/{id}/correct` | Correct start month and value (reason required) |
| `POST /api/depot/instruments/{id}/rate` | New savings rate from a month on |
| `POST /api/depot/instruments/{id}/one-offs`, `DELETE .../{one_off_id}` | Add / remove a one-off payment |
| `GET /api/depot/projection?years=&start=&return_shift=&inflation=` | Month-by-month projection incl. tax estimate |
| `GET/PUT /api/tax/settings` | Church tax, allowance, assumed Basiszins |
| `PUT /api/actuals/values`, `GET /api/actuals/values`, `DELETE /api/actuals/values/{id}` | Month-end values |
| `GET/POST /api/actuals/transactions`, `DELETE .../{id}` | Real buys, sells, dividends |
| `POST /api/actuals/import/preview`, `POST /api/actuals/import` | Broker CSV import (JSON body with the file text) |
| `GET /api/actuals/compare` | Plan vs. actual |
| `DELETE /api/depot/instruments/{id}`, `DELETE /api/financings/{id}` | Delete (audited) |
| `GET /api/catalog?q=&index=&distribution=&replication=&max_ter=&sort=` | Search instruments |
| `POST /api/catalog`, `DELETE /api/catalog/{id}` | Own catalog entries |
| `GET /api/catalog/compare?ids=&monthly=&years=&expected_return=` | Cost comparison |

## Deployment (homelab)

```bash
cp .env.example .env   # set KONTOR_DB_PASSWORD to a long random value
docker compose up -d --build
```

Three containers: Postgres (volume `kontor-db`), the API (runs migrations on every start, non-root, with a
health check) and nginx serving the UI on port 8080 (`KONTOR_PORT`) and proxying `/api`. The API container
trusts the forwarding headers of the proxy in front of it.

- **TLS**: put your reverse proxy (Traefik, Caddy, nginx proxy manager) in front of `web` and keep
  `KONTOR_COOKIE_SECURE=true`. For a quick test over plain HTTP set it to `false`, otherwise the browser
  drops the session cookie.
- **Backup**: `scripts/backup.sh [dir]` writes a compressed `pg_dump`; the restore command is in the script.
  Run it from cron and copy the files off the machine.
- **Update**: `git pull && docker compose up -d --build`. Migrations are applied automatically.
- **Registration is open**: anyone who can reach the UI can create a household. Do not expose it to the
  internet without an access layer in front (VPN, SSO proxy or basic auth).

CI builds and starts the whole stack on every push and smoke-tests it through nginx. A separate job checks
the migrations (up, down, up, model drift) against real Postgres, because the unit tests run on SQLite.
