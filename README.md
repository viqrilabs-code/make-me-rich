# Make Me Rich

Personal-use algorithmic trading web app for a single user, built around an advisory-first workflow with paper trading support out of the box and live execution isolated behind broker adapters and hard risk controls.

## Important risk warning

This software does not guarantee profits, target achievement, or safe live execution.

- Start in `advisory` mode.
- Move to `paper` mode only after reviewing decisions and risk events.
- Enable `live` mode only after you have verified broker endpoints, credentials, order semantics, market hours assumptions, and stop-loss behavior for your broker.
- `GrowwAdapter` is now the primary live broker path and is wired through Groww's official Python SDK plus public instrument metadata. Start in advisory or paper mode before using it with real capital.
- `INDMoneyAdapter` remains available as a legacy broker option if you still want to keep the older INDstocks path around.

## What ships

- FastAPI backend on Python 3.12 style code
- SQLite persistence with SQLAlchemy 2.x and Alembic
- APScheduler polling, monitoring, and end-of-day jobs
- Mock broker that keeps the app usable with no real broker credentials
- Groww-first live broker integration with API key or access-token support
- Market/news service with Marketaux integration plus cached fallback headlines
- Once-per-day top-5 market sweep across tracked stocks and option lanes
- Deterministic strategy features and candidate action generation
- OpenAI-compatible structured LLM decision engine with schema validation and HOLD fallback
- Hard risk engine with kill switch, cooldown, stale-data checks, position sizing, and duplicate protection
- Paper/live/advisory execution flow with audit logs
- Next.js App Router frontend with Tailwind, shadcn-style UI primitives, Zustand, and Recharts
- Docker, Compose, systemd, and nginx deployment artifacts for a small GCP VM

## Project tree

```text
.
├── backend
│   ├── Dockerfile
│   ├── alembic
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions
│   │       └── 20260323_0001_initial.py
│   ├── alembic.ini
│   ├── app
│   │   ├── api
│   │   ├── brokers
│   │   ├── core
│   │   ├── db
│   │   ├── llm
│   │   ├── models
│   │   ├── risk
│   │   ├── scheduler
│   │   ├── schemas
│   │   ├── services
│   │   ├── utils
│   │   └── main.py
│   ├── requirements.txt
│   └── tests
├── deploy
│   ├── nginx
│   │   └── trading-app.conf
│   └── systemd
│       └── make-me-rich-stack.service
├── frontend
│   ├── Dockerfile
│   ├── app
│   ├── components
│   ├── lib
│   ├── public
│   ├── types
│   └── package.json
├── scripts
│   ├── backend-entrypoint.sh
│   └── frontend-entrypoint.sh
├── .env.example
├── docker-compose.yml
└── README.md
```

## Default behavior

- Mode: `advisory`
- Max risk per trade: `1%`
- Max daily loss: `2%`
- Max drawdown: `8%`
- Max open positions: `2`
- Max capital per trade: `20%`
- Mandatory stop loss: enabled
- Options selling: disabled
- Futures: disabled
- Shorting: disabled
- Live execution: disabled until both env and strategy toggles allow it

## Backend modules

- `backend/app/brokers`: broker abstraction plus `MockBrokerAdapter`, `GrowwAdapter`, and `INDMoneyAdapter`
- `backend/app/services/orchestration_service.py`: polling-cycle orchestrator
- `backend/app/risk/engine.py`: hard constraints and position sizing
- `backend/app/llm/service.py`: OpenAI-compatible decision client with schema validation
- `backend/app/services/execution_service.py`: advisory, paper, and live execution handling
- `backend/app/scheduler/engine.py`: APScheduler manager
- `backend/app/api/routes`: REST API under `/api`

## Frontend pages

- `/`: overview dashboard
- `/strategy`: goal, mode, broker, watchlist, and risk settings
- `/decisions`: AI decision log
- `/orders`: orders and open positions
- `/market`: news and sentiment
- `/audit`: audit trail, risk events, and scheduler runs
- `/safety`: kill switch, pause, advisory fallback, and manual run controls
- `/login`: single local admin login
- `/signup`: one-time single-user account creation

## Environment setup

1. Copy the env template:

```bash
cp .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Edit at least these values:

- `SECRET_KEY`
- `FRONTEND_ORIGIN`
- `GROWW_API_KEY` if you want to use Groww as the live broker with either a ready access token or the API key half of the official key-secret flow
- `GROWW_API_SECRET` if you are using the official Groww API key + secret flow instead of pasting a ready access token
- `LLM_API_KEY` if you want live OpenAI decisions instead of heuristic fallback
- `ANTHROPIC_API_KEY` if you want Claude Sonnet fallback when the primary OpenAI call fails
- `MARKETAUX_API_KEY` if you want live Marketaux headlines
- `INDMONEY_API_KEY` only if you want to keep using the older INDstocks broker option
- broker credentials only if you are actively verifying a real adapter
- leave `BOOTSTRAP_ADMIN_ON_STARTUP=false` if you want the app to start with the signup page
- set `BOOTSTRAP_ADMIN_ON_STARTUP=true` only if you explicitly want a pre-created env-based admin account

Important for Docker Compose:

- If any secret in `.env` contains a dollar sign, escape each `$` as `$$` before running `docker compose up`.
- This matters for keys like `GROWW_API_SECRET`, because Compose performs variable interpolation before the value reaches the container.

## Local development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..
export PYTHONPATH=backend
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --reload
```

PowerShell:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ..
$env:PYTHONPATH="backend"
alembic -c backend/alembic.ini upgrade head
uvicorn app.main:app --app-dir backend --reload
```

Backend runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://localhost:3000`.

### First account

- Fresh installs now start at `/signup`
- The first created account becomes the only local user for the app
- If you prefer env bootstrap instead, set `BOOTSTRAP_ADMIN_ON_STARTUP=true`
- After a user exists, future sessions use `/login`

## Docker Compose

Build and run both services:

```bash
docker compose up --build
```

Endpoints:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Health: `http://localhost:8000/health`

If port `8000` is already in use on your machine, set a different host port in `.env` before starting:

```env
BACKEND_PUBLIC_PORT=8001
```

Then run:

```bash
docker compose up --build
```

The frontend still works on `http://localhost:3000` because it proxies API requests internally to the backend container.

If port `3000` is busy too, set:

```env
FRONTEND_PUBLIC_PORT=3001
```

SQLite is persisted on the bind-mounted `./backend/data` directory.

Fresh Docker installs also use the signup-first flow unless `BOOTSTRAP_ADMIN_ON_STARTUP=true`.

## GCP Compute Engine deployment

Target assumption: small personal VM such as `e2-micro` with a persistent disk.

### Recommended VM flow

1. Create a Debian or Ubuntu VM.
2. Install Docker Engine and the Docker Compose plugin.
3. Attach a persistent disk or use the main disk for app data.
4. Clone this repo into `/opt/make-me-rich`.
5. Copy `.env.example` to `.env` and edit secrets.
6. For production, set at least these values in `.env`:

```env
APP_ENV=production
FRONTEND_ORIGIN=https://your-domain.example
SECRET_KEY=replace-with-a-long-random-secret
BOOTSTRAP_ADMIN_ON_STARTUP=false
BACKEND_PUBLIC_PORT=8000
FRONTEND_PUBLIC_PORT=3000
```

7. Start the stack:

```bash
cd /opt/make-me-rich
docker compose up -d --build
```

8. Visit `https://your-domain.example/signup` once and create the single local user.
9. Optional: place nginx in front using `deploy/nginx/trading-app.conf`.
10. Optional: install the systemd unit:

```bash
sudo cp deploy/systemd/make-me-rich-stack.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now make-me-rich-stack.service
```

11. Recommended GCP extras:

- Reserve a static external IP for the VM.
- Allow inbound `80` and `443` in the relevant firewall rules.
- Terminate TLS with nginx plus Certbot or your preferred certificate flow.
- Keep `backend/data` on persistent disk storage so SQLite survives restarts.
- Keep the app on a single backend instance because APScheduler is intentionally in-process and single-seat.

### Notes for small VMs

- Keep the backend and frontend on one VM.
- Keep SQLite on disk volume storage.
- Do not add Redis, Kubernetes, Cloud SQL, or Cloud Run unless you deliberately want a more complex architecture.
- APScheduler already handles recurring jobs inside the backend process, so you do not need a separate systemd timer for trading cycles.

## Nginx reverse proxy

The sample config at `deploy/nginx/trading-app.conf` routes:

- `/` to the Next.js frontend on port `3000`
- `/api/`, `/health`, and `/ready` to the FastAPI backend on port `8000`
- includes basic hardening headers and websocket-safe proxy settings

## Real broker adapter status

`GrowwAdapter` is the primary live broker integration.

- Auth supports either a ready Groww access token in `GROWW_API_KEY` or the official API key + secret flow using `GROWW_API_KEY` and `GROWW_API_SECRET`.
- Holdings, positions, order book, quotes, candles, account margin, and cash-equity order placement are wired through the Groww SDK.
- Manual market analysis now fails closed instead of silently showing mock prices when the selected live broker is unhealthy.
- `INDMoneyAdapter` remains available as a legacy broker path through `api.indstocks.com` if you still want to use it.

## Scheduler design

The backend scheduler includes:

- startup sync run
- recurring poll check every minute with dynamic interval gating
- open-position monitoring job
- end-of-day reconciliation job
- in-process overlap protection with `SchedulerLock`

## API summary

Main routes:

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/config`
- `PUT /api/config`
- `GET /api/goals/current`
- `POST /api/goals`
- `PUT /api/goals/current`
- `GET /api/strategy`
- `PUT /api/strategy`
- `POST /api/strategy/kill-switch`
- `POST /api/strategy/resume`
- `POST /api/strategy/run-once`
- `GET /api/broker/health`
- `GET /api/broker/account`
- `GET /api/broker/positions`
- `GET /api/broker/orders`
- `POST /api/broker/test-connection`
- `GET /api/decisions`
- `GET /api/orders`
- `GET /api/portfolio/latest`
- `GET /api/portfolio/performance`
- `GET /api/portfolio/overview`
- `GET /api/market/best-trade`
- `GET /api/market/daily-top-deals`
- `POST /api/market/daily-top-deals/refresh`
- `GET /api/news`
- `GET /api/news/summary`
- `GET /api/scheduler/status`
- `GET /api/audit/logs`
- `GET /api/audit/risk-events`
- `GET /api/audit/scheduler-runs`
- `GET /health`
- `GET /ready`

## Testing

Run backend tests:

```bash
cd backend
pytest
```

Included test coverage:

- risk engine approval and rejection
- goal planner calculations
- LLM malformed output fallback
- mock broker order placement
- duplicate execution prevention

## Operational guidance

- Keep `LLM_TEMPERATURE` low for consistent structured output.
- If `LLM_API_KEY` is absent, the app uses a deterministic heuristic decision fallback instead of breaking.
- If `ANTHROPIC_API_KEY` is present, the app automatically falls back to Anthropic after OpenAI request failures.
- If `MARKETAUX_API_KEY` is absent, the app uses cached mock headlines instead of wasting requests.
- Use the safety page to pause the scheduler, trigger a kill switch, or force advisory mode quickly.
- Review the audit log before enabling live trading.

