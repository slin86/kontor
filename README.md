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
  The **Categories** page (link on the cashflow page) creates, renames, reorders and moves them between
  groups and deletes them. A category with items needs a target that takes the items over; a group with
  sub-categories cannot be deleted before they are moved or removed. Changes are audited and never touch
  amounts. Items booked directly on a group that also has sub-categories show up as "Ohne Unterkategorie".
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

Not covered yet: correcting the *dates* of a version, deleting items.

## Financings and budget outlook

- **Loan** (real estate, car, consumer, ...): amount, annual rate, first month and either a fixed monthly
  payment or an initial repayment percentage (payment = amount x (rate + repayment) / 12). Interest accrues
  monthly on the remaining balance (annuity loan).
- **Bausparvertrag**: saving phase (monthly contribution, interest credited each December, one-off
  Abschlussgebuehr), allocation month, then a loan phase with its own rate and payment.
- **Bausparfinanzierung** (Bausparvertrag with advance loan): the whole contract sum is paid out on day 1 as an
  interest-only advance loan (Vorausdarlehen). Until allocation you pay its interest plus the monthly saving;
  at allocation savings and Bauspardarlehen settle the advance loan and only the Bauspar loan keeps running.
  It is a Bauspar contract with `prefinance_rate_percent` set. The fee can be given in percent or euros.
  With `payouts` (month and amount) the advance loan is paid out in stages and interest runs only on what has been
  paid out so far; the savings run from the first month regardless.
- **0 %-Finanzierung** (installment purchase): a loan with purpose `zero_percent`. The interest must be 0; the form
  derives the monthly payment from the amount and the number of months.
- **Credit line** (Rahmenkredit): limit, amount drawn today, annual rate and a fixed monthly payment. Runs
  like an annuity loan, but money can be taken out again up to the limit. Deposits are special repayments,
  withdrawals are `drawdown` events (money received, so no cashflow outflow). Exceeding the limit is rejected.
- **Events** from the current month on: special repayment (a deposit on a credit line), drawdown (credit line
  only), payment change, rate change. Past events are
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

## People and household

A household has several **people**. Every user gets one on registration; children (or anyone without a login) are added on the *Haushalt* page.
Positions, actual values, transactions, CSV imports, tax settings, cashflow items and financings belong to one person; categories are shared.
The Depot, Plan & Ist, Cashflow and Finanzierungen pages have a switcher (one person, or *Alle zusammen*, which sums everything; taxes are computed per owner with that owner's settings).
A **transfer** is a cashflow item with a receiver (e.g. Mandy pays 800 € per month to Nils): an expense of the sender, income of the receiver, and netted out in the household total.
It has versions like any other item, so it can change over time. Transfers are booked on the categories *Übertrag an andere Person* / *Übertrag erhalten*, created on first use.
The *Haushalt* page also manages login members, the invite code (renewing invalidates the old one), the household name and the own profile/password.
Migrations `0008` and `0009` assign existing positions, items and financings to the earliest member and move the tax settings to their person.

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

## AI helper (optional)

Everything below also works without AI; the helper only saves typing.

- **Items from a bank statement** (Cashflow, Posten, *Aus Kontoauszug*): upload a CSV, CAMT.053, MT940 or a
  PDF with a text layer, ideally several months. Kontor finds payments that come back in a fixed rhythm
  (same payee, similar amount, monthly, quarterly, semiannual or yearly) by plain arithmetic, not by the
  model. The AI then proposes a category from your own category tree and judges single payments ("a gym
  fee probably comes back, a petrol station does not"). You review and edit every row before anything
  is created. Payees that match an existing item are not preselected. The file is not stored.
- **Name to category** (new item form): after typing a name the AI proposes a category and whether and how
  often it recurs. Names that already exist as items are answered from your own data first.
- **PDF statements** are read by the local model (text extraction, then the model lists the bookings).
  Scans without a text layer are refused; use the bank's CSV or CAMT export instead.
- **Any bank, any CSV.** Known German and English headers are read without AI. For a layout nobody has
  seen, the AI only tells Kontor which column is the date, amount (or debit/credit), payee and purpose,
  from the first rows; the file itself is then parsed by plain code.
- **Contracts and invoices** (Cashflow, Posten, *Aus Dokument*): insurance, energy, internet, mobile, rent,
  Kita, club or subscription documents as PDF or text. The AI reads amount and payment rhythm and proposes
  items; you review them like statement rows.
- **Loan, building savings and credit line contracts** (Finanzierungen, *Aus Vertrag*): the AI fills the
  form for the matching type (loan, 0 % financing, credit line, Bausparvertrag, Bausparfinanzierung).
  Nothing is saved until you submit the form.
- **Broker documents** (Depot, Plan & Ist, *Import aus dem Broker*): Trade Republic's transaction CSV is read
  without AI; other CSV layouts and PDF statements go through the AI. Rows are matched to positions by ISIN,
  unknown ISINs can be assigned by hand, and rows already imported are skipped.
- **Checks against hallucinations.** Every amount, share count, date and ISIN the model returns is compared
  with the document text (several number spellings, ISIN check digit). What is not in the text is marked
  "Bitte prüfen" and starts unselected. Every kind of document is first classified; a document that clearly
  belongs elsewhere is refused with a pointer to the right page ("Das ist ein Kontoauszug ...").

**Background jobs.** An upload does not block the page. Kontor starts a job, you keep working, and a notice in the
corner of every page says when the document is read ("Ergebnis ansehen"). Jobs run one at a time on the local
server. If the AI machine is off or still loading its model, the job waits (`KONTOR_AI_WAIT_MINUTES`, default 10,
retrying every `KONTOR_AI_RETRY_SECONDS`, default 15) and continues by itself, so a machine that wakes up on
demand works. Results stay in the API's memory for up to 24 hours or until you dismiss them; nothing is written
to the database and the file is dropped when the job ends. A restart of the API loses open jobs; upload again.

**Where the model runs.** Statements, and anything derived from them, only go to a *local* server that
speaks the OpenAI API: Ollama (`OLLAMA_HOST=0.0.0.0` so the cluster can reach it) or LM Studio (serve on
the local network, Developer tab). Set `KONTOR_AI_LOCAL_URL` in `base/configmap.yaml`: Ollama listens on
port 11434 (`http://gaming-pc.home.lan:11434`), LM Studio on 1234 (`http://gaming-pc.home.lan:1234`); a
trailing `/v1` is accepted. `KONTOR_AI_LOCAL_MODEL` is optional: when empty, Kontor uses the first model the
server lists, which for LM Studio is the one you have loaded. If the machine is off, Kontor says so and everything
keeps working by hand; start the machine and retry. Text models handle categories and names; reading PDFs
needs a model that follows JSON schemas well, so check the preview. An optional `KONTOR_AI_CLOUD_API_KEY`
(Infisical) lets a cloud model answer the *single item name* suggestion when the local server is off. It
never receives statements or payees from statements.

Ollama truncates prompts at its default context of 4096 tokens. Kontor sends small chunks (about 6,000
characters), but set `OLLAMA_CONTEXT_LENGTH=16384` (or the context in LM Studio) for long PDFs. Scanned
PDFs need OCR and are not supported yet.

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
The theme follows the system by default; the header button cycles automatic, light and dark and remembers the choice. Colors are CSS variables in `index.css`, charts are recolored in `charts/EChart.tsx`.
The name in the header opens the account menu (account, household, appearance, sign out, version). Images are built with `APP_VERSION` (the release tag), shown there and returned by `/api/health`.

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
| `GET/POST /api/categories`, `PUT/DELETE /api/categories/{id}`, `POST .../{id}/move` | List, create, rename or move, delete (`?move_to=`), reorder categories |
| `GET /api/cashflow/items?month=YYYY-MM` | Items valid in a month (`include_inactive=true` for all) |
| `POST /api/cashflow/items` | Create an item (a start in a closed month is logged as backfill) |
| `POST /api/cashflow/items/{id}/change` | New amount from a month on |
| `POST /api/cashflow/items/{id}/end` | End an item from a month on |
| `POST /api/cashflow/versions/{id}/correct` | Correct a version in place (reason required) |
| `GET /api/cashflow/summary` / `sankey` | Aggregates for one month |
| `GET /api/cashflow/series?from=&to=` | Income, expenses and balance per month |
| `GET /api/audit` | Audit log |
| `GET/POST /api/financings` | List / create loans, credit lines and Bauspar contracts |
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

Kontor uses a Postgres you already run, so no extra database container is started. Create a database
and user once:

```sql
CREATE USER kontor WITH PASSWORD '<long random value>';
CREATE DATABASE kontor OWNER kontor;
```

```bash
cp .env.example .env   # set KONTOR_DATABASE_URL (host, password)
docker compose up -d --build
```

Two small containers: the API (runs migrations on every start, non-root, with a health check) and nginx
serving the UI on port 8080 (`KONTOR_PORT`) and proxying `/api`. The API trusts the forwarding headers of
the proxy in front of it. If Postgres runs on the Docker host itself, use `host.docker.internal` as host
(it is mapped in the compose file) and let Postgres listen on the Docker bridge address and accept it in
`pg_hba.conf`.

- **TLS**: put your reverse proxy (Traefik, Caddy, nginx proxy manager) in front of `web` and keep
  `KONTOR_COOKIE_SECURE=true`. For a quick test over plain HTTP set it to `false`, otherwise the browser
  drops the session cookie.
- **Backup**: `scripts/backup.sh [dir]` writes a compressed `pg_dump` (needs `pg_dump` on the host); the
  restore command is in the script. Run it from cron and copy the files off the machine.
- **Update**: `git pull && docker compose up -d --build`. Migrations are applied automatically.
- **Who can sign up**: the very first household can always be created. After that
  `KONTOR_ALLOW_NEW_HOUSEHOLDS=false` (the default) refuses new households; further family members join
  with the household's invite code. Set it to `true` to allow anyone to create a household.
- **Brute force**: five failed logins per e-mail address within 15 minutes, or 20 per client address
  (also counting wrong invite codes), block further attempts with HTTP 429. The counters live in the API
  process and reset on restart. The block also applies to the real owner of an attacked address, which is
  an acceptable trade-off for a household tool.

CI starts the whole stack on every push against a throwaway Postgres and smoke-tests it through nginx. A
separate job checks the migrations (up, down, up, model drift) against Postgres, because the unit tests
run on SQLite.

## Kubernetes and Argo CD

Manifests live in `deploy/k8s` (Kustomize) and the Argo CD application in `deploy/argocd`. The layout and
the secret handling follow the other homelab apps (Traefik, Infisical).

```
deploy/k8s/base                  namespace, config, InfisicalSecret, API, web
deploy/k8s/overlays/homelab      ingress host and image tags (edit this one)
deploy/argocd/application.yaml   Argo CD Application (auto-sync, prune, self-heal)
```

**Secrets are kept in Infisical.** `base/infisical-secret.yaml` syncs the path `/kontor` (project
`homelab-ei-fj`, environment `prod`, same machine identity as the other apps) into the Secret
`kontor-secrets`, which the API reads as environment variables. Add these keys in Infisical:

| Key | Value |
|---|---|
| `KONTOR_DATABASE_URL` | `postgresql+psycopg://kontor:<password>@<postgres service>.<namespace>.svc.cluster.local:5432/kontor` (percent-encode special characters of the password, an at sign becomes `%40`) |

Optional: `KONTOR_AI_CLOUD_API_KEY` (see the AI helper section). Non-secret settings (cookie flag, time zone, whether new households may be created)
are in `base/configmap.yaml`. The project slug and path are the first thing to change if you keep Kontor
in a different Infisical project.

**Database**: like the other apps, Kontor uses the shared PostgreSQL in the cluster with its own role and
database. Create them once:

```bash
kubectl -n <postgres namespace> exec -it <postgres pod> -- psql -U postgres \
  -c "CREATE ROLE kontor WITH LOGIN PASSWORD '<password from KONTOR_DATABASE_URL>';" \
  -c "CREATE DATABASE kontor OWNER kontor;"
kubectl -n <postgres namespace> exec -it <postgres pod> -- \
  psql -U postgres -d kontor -c "GRANT ALL ON SCHEMA public TO kontor;"
```

**Setup**:

1. Enter the secret in Infisical and create the database.
2. Edit the host in `deploy/k8s/overlays/homelab/ingress.yaml` (default `kontor.home.lan`, Traefik,
   internal), and the host in `ingressroute.yaml` (public Traefik IngressRoute, default `kontor.slin.io`).
3. `kubectl apply -f deploy/argocd/application.yaml`.

**How it runs**: the images are `ghcr.io/slin86/kontor-api` and `kontor-web`. Every push to `main` that
touches application code builds both (workflow *Images*) and commits the new `sha-...` tag into the homelab
overlay, which Argo CD then syncs. The API container migrates the database on start and runs as a single
replica with the `Recreate` strategy (migrations, and the login throttle keeps its counters in the process),
as non-root with a read-only root file system. Requests are a few MB and milli-CPUs. Until the Infisical
operator has created the Secret, the API pod waits and retries by itself.

Notes:
- The images are meant to be public, so the cluster pulls them without a pull secret. Both Dockerfiles carry the
  `org.opencontainers.image.source` label, which links the packages to this repository. If GitHub still creates a
  package as private on its first push, set it to public once under Packages, Package settings, Danger zone.
- The *Images* workflow pushes the tag commit to `main`. With branch protection that blocks it, let the workflow
  open a pull request instead, or drop the `release` job and pin the tag by hand.
- CI renders and schema-checks the manifests on every push (CRDs such as `InfisicalSecret` are skipped).
