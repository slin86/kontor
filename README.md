# Kontor

Household finance planner: cashflow with Sankey views, financings and savings contracts,
and a long-range depot projection with plan-vs-actual comparison.

Self-hosted, built for a homelab.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Backend skeleton, accounts (households with several members), Docker, CI | this branch |
| 2 | Cashflow: income/expenses (monthly, quarterly, yearly), timeline, Sankey and charts | this branch |
| 3 | Financings, building-society savings contracts (Bausparvertrag), loans, household budget forecast | planned |
| 4 | Depot plan: savings rates, dated rate changes, one-off payments, scenarios, history | planned |
| 5 | Instrument search (ETF / private equity), costs, comparison, CSV import | planned |
| 6 | Plan vs. actual, polish | planned |

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

## Deployment (homelab)

```bash
cp .env.example .env   # set KONTOR_DB_PASSWORD
docker compose up -d --build
```

The web UI is served on port 8080 and proxies `/api` to the API, which runs migrations on start.
Put a TLS-terminating reverse proxy in front of `web` and keep `KONTOR_COOKIE_SECURE=true`. For a quick
test over plain HTTP set `KONTOR_COOKIE_SECURE=false`, otherwise the browser drops the session cookie.
