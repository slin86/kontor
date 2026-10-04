# Kontor

Household finance planner: cashflow with Sankey views, financings and savings contracts,
and a long-range depot projection with plan-vs-actual comparison.

Self-hosted, built for a homelab.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Backend skeleton, accounts (households with several members), Docker, CI | this branch |
| 2 | Cashflow: income/expenses (monthly, quarterly, yearly), timeline, Sankey and charts | planned |
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
- **Money is `Decimal`**, never floating point.
- **Pure calculation core.** Cashflow aggregation, loan amortisation and depot projection are pure
  functions, tested independently from HTTP and the database.
- **Household budget outlook.** Every financing/contract has an end date, so the projected free
  monthly budget is shown over the years as loans and savings contracts run out.

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

## Deployment (homelab)

```bash
cp .env.example .env   # set KONTOR_DB_PASSWORD
docker compose up -d --build
```

The API listens on port 8000 and runs migrations on start. Put a TLS-terminating reverse proxy in
front of it and keep `KONTOR_COOKIE_SECURE=true`.
