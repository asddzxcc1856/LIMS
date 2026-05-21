# LIMS — Semiconductor Wafer Fab Laboratory Information Management System

[![CI](https://github.com/asddzxcc1856/LIMS/actions/workflows/ci.yml/badge.svg)](https://github.com/asddzxcc1856/LIMS/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Django](https://img.shields.io/badge/django-5.2-success)
![Vue](https://img.shields.io/badge/vue-3.5-brightgreen)
![Tests](https://img.shields.io/badge/tests-285%20pytest%20%2B%2055%20vitest%20%2B%208%20e2e-success)
![License](https://img.shields.io/badge/license-MIT-blue)

A laboratory information management system tailored for semiconductor wafer
fabs. The workflow tracks every 25-wafer FOUP through three specialised labs
(Photolithography, Thin Film & Etch, Metrology & Inspection) at **sub-LOT
granularity** — every wafer split is dispatched independently, parameters are
tuned per sub-LOT, and the operator who runs the machine is auto-picked by
workload while honouring an explicit "各司其職" rotation rule.

---

## Table of contents

- [Highlights](#-highlights)
- [Workflow at a glance](#-workflow-at-a-glance)
- [Architecture](#-architecture)
- [Technology stack](#-technology-stack)
- [Quick start](#-quick-start)
- [Demo accounts](#-demo-accounts)
- [Role × specialty matrix](#-role--specialty-matrix)
- [Project layout](#-project-layout)
- [Testing](#-testing)
- [CI / CD](#-ci--cd)
- [Configuration](#-configuration)
- [Subsystem docs](#-subsystem-docs)
- [License](#-license)

---

## ✨ Highlights

| Feature | Detail |
|---|---|
| **Per-sample dispatch chain** | An order's wafer lot is split into `Sample` sub-LOTs; every sub-LOT independently picks its own machine, recipe, parameter set, and operator. Different sub-LOTs of the same order can run on different machines in parallel. |
| **Specialty-gated workflow** | `lab_member.lab_specialty ∈ {coord, dispatcher, engineer, operator}` enforces 各司其職. The 分貨 / 派工 / 設定參數 steps can only be executed by the matching tier; the manager has sign-off rights but cannot touch any downstream step. |
| **Auto-assigned operator** | `set_sample_parameters` automatically picks the least-busy operator-specialty lab_member who isn't upstream on this sub-LOT. The "待指派" manual step is gone. |
| **25-wafer cap** | A FOUP holds exactly 25 wafers, so every split must sum to exactly 25 — the backend rejects over- and under-split with a clear Chinese message. |
| **Schedule-conflict guard** | `dispatch_sample` runs a transactional `select_for_update` + overlap query on `EquipmentBooking`. A second sub-LOT pointed at an already-booked machine window is rejected before the sample state changes. |
| **數據蒐集 + 自動結單** | Operators (or machine agents) POST to `/samples/<id>/telemetry/` with one measurement; `finished=true` auto-closes the sub-LOT. A Celery sweep `auto_close_stalled_samples` mops up runs that overrun their `schedule_end`. |
| **報警系統** | Operators can press 回報機台異常 mid-run. The backend appends an `abort` `StageEvent`, flips the equipment to `maintenance` (the `post_save` signal fans out a CRITICAL notification to managers), and pings every engineer in the lab directly. |
| **Manager reports** | Lab-scoped utilization line chart + order business KPIs (lead time, sign-off latency, per-stage status mix) + operator activity bar + an expandable **per-sub-LOT timeline** showing every 簽核 / 接件 / 分貨 / 派工 / 設定參數 / 指派 / 上貨 / 量測 / 下貨 step. |
| **Auto-mask operator identity for requesters** | The `regular_employee` view of their own order is scrubbed: requesters see which **lab** is handling the work, but not which **person** — operator anonymity is preserved. |
| **Three-layer audit** | `ActivityLog` (HTTP-level) + `Approval` (manager sign-off, append-only) + `StageEvent` (typed milestones: receive / split / dispatch / set_parameters / assign / load / unload / abort / note + JSON measurement). |
| **Admin console** | Superuser-only `/admin/*` UI: KPI dashboard, filterable activity log, full CRUD over every domain table (10 resources). |
| **i18n + light/dark theme** | Per-user language (zh-TW / English) and theme preferences, persisted in localStorage, applied without reload. |

---

## 🔁 Workflow at a glance

```
   testuser                Lab_Mgr           Lab_Mem_*_001       Lab_Mem_*_002
   (requester)             (manager)         (coord)             (dispatcher)
   ───────────             ─────────         ───────────         ─────────────
   submit order  ───►  簽核 (auto-接件) ───►  分貨 25 wafers  ───►  派工
                                              into sub-LOTs        (machine + recipe
                                                                    + schedule;
                                                                    conflict-guarded)
                                                                          │
                                                                          ▼
   Lab_Mem_*_003             Lab_Mem_*_004 / 005 / 006
   (engineer)                (operator pool — auto-picked by workload)
   ─────────────             ─────────────────────────
   設定參數     ─────────►   ⟨system 自動指派⟩  ───►   上貨 → 量測 → 下貨
                                                       (or 回報機台異常 if something breaks)
```

Each transition writes an Approval / typed StageEvent / Notification trail, so
the manager's reports view replays every sub-LOT step-by-step.

---

## 🏗 Architecture

```
                      ┌───────────────────────────────────────┐
                      │           Browser (Vue 3)             │
                      │  ant-design-vue · Pinia · vue-router  │
                      │  vue-i18n (zh-TW / en) · light/dark   │
                      └───────────┬───────────────────────────┘
                                  │ JSON over HTTPS · JWT Bearer
                                  │ X-Request-ID round-trips
                                  ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                          Django 5.2 + DRF                             │
   │                                                                        │
   │  ┌──────────┐  ┌──────────┐  ┌────────────┐  ┌──────────┐  ┌──────┐  │
   │  │  users   │  │  orders  │  │ equipments │  │scheduling│  │admin_│  │
   │  │ + role + │  │ Order /  │  │ Equipment /│  │EquipBook │  │  api │  │
   │  │specialty │  │  Stage / │  │  Recipe    │  │StageEvent│  │      │  │
   │  │          │  │  Sample  │  │ (≥5 knobs) │  │ (typed)  │  │      │  │
   │  └────┬─────┘  └────┬─────┘  └────┬───────┘  └────┬─────┘  └──┬───┘  │
   │       │             │             │                │            │     │
   │       └─────────────┴─────────────┴────────────────┴────────────┘     │
   │                                  │                                     │
   │       ┌──────────────────────────┴──────────────────────────┐          │
   │       │  monitoring · ActivityLog · Notification · MyStats   │         │
   │       │  reports endpoints (charts, LOT history, operator)   │         │
   │       │  utils · request_id middleware · custom exception    │         │
   │       └──────────────────────────────────────────────────────┘          │
   │                                  │                                     │
   └──────────────────────────────────┼─────────────────────────────────────┘
                                      ▼
                       ┌──────────────────────────┐
                       │  SQLite (dev) / MySQL    │
                       │  Redis (Celery, cache)   │
                       │  Sentry (errors, opt)    │
                       └──────────────────────────┘
```

**Sample state machine**

```
              split_order()       dispatch_sample()    set_sample_parameters()
   ┌─────────┐   ────►   ┌────────────┐   ────►   ┌────────────┐   ────►   ┌─────────┐
   │ (none)  │           │  WAITING   │           │ DISPATCHED │           │PARAMS_  │
   │  Order  │           │  (queued   │           │ (machine + │           │  SET    │
   │ APPROVED│           │ for派工)   │           │ recipe set)│           │         │
   └─────────┘           └────────────┘           └────────────┘           └────┬────┘
                                                                                │ auto_pick
                                                                                ▼
                                                                          ┌─────────┐
                                                                          │  READY  │
                                                                          │ (op自動  │
                                                                          │ 指派)   │
                                                                          └────┬────┘
                                                                                │ load_sample()
                                                                                ▼
                                                                          ┌─────────┐
                          report_sample_abnormal()                        │ RUNNING │
                          ────────────────────────►  abort / maintenance  └────┬────┘
                                                                                │ complete_sample()
                                                                                ▼
                                                                          ┌─────────┐
                                                                          │  DONE   │
                                                                          └─────────┘
```

---

## 🛠 Technology stack

### Backend

| Layer | Choice |
|---|---|
| Framework | Django 5.2 + Django REST Framework |
| Auth | JWT via `djangorestframework-simplejwt` (2h access, 7d refresh) |
| Database | SQLite (dev) / MySQL 8 (production) |
| Caching | Redis 7 (cache + Celery broker) |
| Background jobs | Celery 5.6 + Celery Beat (`auto_close_stalled_samples`, `alert_schedule_overruns`) |
| Observability | django-prometheus metrics + structured logging + Sentry (opt-in via `SENTRY_DSN`) |
| Testing | pytest + pytest-django + factory-boy + freezegun + pytest-mock |

### Frontend

| Layer | Choice |
|---|---|
| Framework | Vue 3 (Composition API + `<script setup>`) |
| State | Pinia 3 |
| Router | Vue Router 4 (role + specialty-aware guards) |
| UI library | Ant Design Vue 4 (`@ant-design/icons-vue`) |
| Build | Vite 8 |
| HTTP | Axios with JWT interceptor + automatic refresh-on-401 |
| i18n | vue-i18n 9 (Composition API mode) |
| Charts | Hand-rolled SVG `LineChart` / `BarChart` (no external dep) |
| Date | dayjs |
| Testing | Vitest 3 + @vue/test-utils + jsdom + Playwright |

### Operations

| Layer | Choice |
|---|---|
| CI | GitHub Actions (`.github/workflows/ci.yml`) — backend pytest + frontend vitest + frontend build + Playwright e2e |
| CD | Helm + Argo CD ApplicationSet on GKE — see [`gitops/`](gitops/) and [`docs/02-GCP-BRINGUP-RUNBOOK.md`](docs/02-GCP-BRINGUP-RUNBOOK.md) |
| Containers | `Dockerfile` for backend (Python slim) and frontend (nginx); `docker-compose.yml` for local stack |
| Secrets | All sensitive values flow from environment variables / Kubernetes Secrets; never committed |

---

## 🚀 Quick start

### Option A — Docker Compose (recommended)

```bash
git clone https://github.com/HCIS-Lab/aicapstone-leaderboard.git LIMS
cd LIMS
cp .env.example .env       # edit DJANGO_SECRET_KEY etc.
docker compose up --build
```

The startup chain runs `migrate → seed_demo_accounts → enrich_recipe_parameters
→ seed_demo_orders → gunicorn`, so a fresh database lands with:

- 3 fabs × 3 labs × 6 lab_members (1 coord + 1 dispatcher + 1 engineer + 3 operators) + 3 lab_managers + admin + testuser
- 12 EquipmentTypes × 23 Equipment instances
- 60 recipes (each with ≥ 5 tunable knobs) + a `Default-<type>` fallback recipe for any custom EquipmentType
- 5 demo orders per lab covering DONE / IN_PROGRESS / REJECTED / WAITING and one APPROVED + WAITING-sub-LOT for the dispatcher to test 派工

Frontend at `http://127.0.0.1:5173`, backend at `http://127.0.0.1:8000`.

### Option B — Local dev (no Docker)

```bash
# Backend
cd backend
python -m venv ../venv && source ../venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_accounts
python manage.py enrich_recipe_parameters
python manage.py seed_demo_orders
python manage.py runserver

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

---

## 🔐 Demo accounts

All demo passwords default to `Lims@2026!Init` (admin uses `Admin@LIMS_2026!Sup`),
overridable via `LIMS_DEMO_PASSWORD` / `LIMS_ADMIN_PASSWORD`. Rotate any of
them via `python manage.py changepassword <username>` before going live.

| Username | Role | Specialty | Notes |
|---|---|---|---|
| `admin` | Superuser | — | Full system + admin console |
| `Lab_Mgr_Photo` | Lab manager (Photo) | — | Sign-off + reports; cannot touch downstream steps |
| `Lab_Mgr_Process` | Lab manager (Thin Film & Etch) | — | ditto |
| `Lab_Mgr_QC` | Lab manager (Metrology & Inspection) | — | ditto |
| `Lab_Mem_<Lab>_001` | Lab member | `coord` | 接件 (auto via sign-off) + 分貨 |
| `Lab_Mem_<Lab>_002` | Lab member | `dispatcher` | 派工 (機台 + Recipe + 排程) |
| `Lab_Mem_<Lab>_003` | Lab member | `engineer` | 設定參數 + triggers auto-assign |
| `Lab_Mem_<Lab>_004 / 005 / 006` | Lab member | `operator` | 上下貨 + 量測 + 回報異常 (pool, auto-picked by workload) |
| `testuser` | Regular employee | — | Sample requester (R&D engineer persona) |

`<Lab>` ∈ `Photo` / `Process` / `QC` → 6 members × 3 labs = 18 lab_members + 3 managers + admin + testuser = **23 demo accounts**.

---

## 👥 Role × specialty matrix

| Capability | Requester | Coord | Dispatcher | Engineer | Operator | Manager | Superuser |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Submit a sample order | ✅ own | — | — | — | — | — | ✅ |
| View own orders | ✅ (operator names masked) | — | — | — | — | — | ✅ |
| View lab-scoped orders | — | ✅ scope | ✅ scope | ✅ scope | ✅ scope | ✅ full | ✅ |
| 簽核 / 駁回 stage (auto-receives) | — | — | — | — | — | ✅ | ✅ |
| 分貨 — split into 25-wafer sub-LOTs | — | ✅ | — | — | — | — | ✅ |
| 派工 — pick machine + recipe + schedule | — | — | ✅ | — | — | — | ✅ |
| 設定參數 — tune recipe knobs (triggers auto-assign) | — | — | — | ✅ | — | — | ✅ |
| Auto-assigned 上貨 / 量測 / 下貨 | — | — | — | — | ✅ self | — | ✅ |
| 回報機台異常 mid-run | — | — | — | — | ✅ self | — | ✅ |
| Reports (utilization / order biz / operator drill) | — | — | — | — | — | ✅ own lab | ✅ all |
| Equipment status flip → CRITICAL alert fan-out | — | — | — | — | — | ✅ own lab | ✅ all |
| CRUD any domain table | — | — | — | — | — | — | ✅ admin |

Row-level scoping is enforced at the API layer — out-of-scope reads return 404
rather than 403 to avoid leaking existence. The 各司其職 rotation rule on
`assign_sample` rejects re-using any upstream user as the operator.

---

## 📁 Project layout

```
LIMS/
├── backend/                       # Django project — see backend/README.md
│   ├── backend/                   #   project settings + URL conf
│   ├── users/                     #   FAB / Department / User (role + lab_specialty)
│   ├── orders/                    #   Order / OrderStage / Sample + state-machine services
│   ├── equipments/                #   Experiment / EquipmentType / Equipment / Recipe
│   ├── scheduling/                #   EquipmentBooking + typed StageEvent + Celery tasks
│   ├── monitoring/                #   ActivityLog + Notification + reports + LOT history
│   ├── admin_api/                 #   Superuser-only ModelViewSets (CRUD over 11 models)
│   ├── utils/                     #   request_id middleware + custom DRF exception handler
│   ├── tests/                     #   285 pytest cases (factories, AAA, freezegun)
│   ├── conftest.py                #   shared fixtures incl. per-role/specialty APIClient
│   ├── pytest.ini                 #   pytest config
│   └── manage.py
│
├── frontend/                      # Vue 3 SPA — see frontend/README.md
│   ├── src/
│   │   ├── api/                   #   axios + per-domain modules (orders, equipments, admin)
│   │   ├── stores/                #   auth (JWT + specialty-aware can* flags) + settings
│   │   ├── router/                #   role + specialty guards
│   │   ├── i18n/                  #   zh-TW + en catalogues (incl. recipe-knob labels)
│   │   ├── components/charts/     #   LineChart / BarChart (hand-rolled SVG)
│   │   ├── views/
│   │   │   ├── admin/             #     12 admin pages — dashboard, logs, 10 CRUD pages
│   │   │   ├── requester/         #     OrderList / OrderCreate
│   │   │   ├── manager/           #     OrderReview + ManagerReports (LOT history timeline)
│   │   │   └── member/            #     OrderTasks (specialty-gated tabs + abnormal modal)
│   │   ├── App.vue                #   Layout shell + ConfigProvider + Settings drawer
│   │   └── main.js
│   ├── tests/                     # 55 vitest cases (stores, api, components)
│   ├── e2e/                       # 8 Playwright specs (login, admin console, CRUD)
│   └── vite.config.js
│
├── docs/                          # Deployment runbooks + ops manual (see docs/README.md)
├── helm/lims/                     # Helm chart (Deployment, Service, Ingress, HPA, PDB)
├── gitops/                        # Argo CD ApplicationSet bootstrap
├── infra/                         # Terraform GCP foundation (VPC / NAT / subnets)
├── .github/workflows/             # CI (always-on) + CD draft (Cloud Run, disabled)
└── docker-compose.yml             # local backend + frontend + MySQL + Redis stack
```

---

## ✅ Testing

| Suite | Tool | Count | Run |
|---|---|---:|---|
| Backend unit + integration | pytest + factory-boy + freezegun | **285** | `cd backend && pytest` |
| Frontend unit + component | vitest + @vue/test-utils | **55** | `cd frontend && npm test` |
| End-to-end | Playwright (chromium) | **8** | `cd frontend && npm run e2e` |

Backend tests follow Arrange / Act / Assert and demonstrate the five canonical
**test-double** styles (Fake / Stub / Mock / Spy / Time-fake). Notable coverage:

- `test_sample_dispatch.py` — full per-sample chain, rotation rule, specialty
  gates, **schedule-conflict guard** (overlap rejection)
- `test_telemetry_alerts.py` — 數據蒐集 endpoint, auto-close Celery sweep,
  **alarm fan-out** to engineers
- `test_visibility_scoping.py` — row-level scoping per role × specialty
- `test_charts.py` — utilization / business KPI / operator activity drill-down /
  per-LOT history endpoints
- `test_samples.py` — split validation incl. exact 25-wafer cap

E2E tests need both servers running. The `webServer` block in
`playwright.config.js` boots Vite automatically; the backend must be started
separately.

---

## 🤖 CI / CD

`.github/workflows/ci.yml` runs on every push and PR to `main`:

| Job | Steps |
|---|---|
| **backend** | install deps → run `pytest` |
| **frontend-unit** | `npm ci` → `npm test` (vitest) → `npm run build` |
| **e2e** | boot Django (load seed + `seed_demo_accounts`) → `npx playwright test` → upload report on failure |

Concurrency group cancels in-progress runs on rapid pushes.

`.github/workflows/cd.yml` is a draft Cloud Run pipeline. Production deployment
runs through Helm + Argo CD on GKE; see [`docs/02-GCP-BRINGUP-RUNBOOK.md`](docs/02-GCP-BRINGUP-RUNBOOK.md) and
[`docs/06-ARGO-CD-ON-KIND.md`](docs/06-ARGO-CD-ON-KIND.md).

---

## ⚙️ Configuration

All environment variables read by Django:

| Var | Default | Description |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Set to `False` for production |
| `DJANGO_PRODUCTION` | `False` | When `True`, refuses dev secret + wildcard hosts, enables HSTS / SSL redirect / Secure cookies |
| `DJANGO_SECRET_KEY` | dev fallback | Required when `DJANGO_PRODUCTION=True` |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated host list |
| `DB_ENGINE` | (sqlite) | Set to `mysql` to switch to MySQL |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | — | MySQL credentials |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Cache + Celery broker |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Used by `auto_close_stalled_samples` + `alert_schedule_overruns` |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated |
| `SENTRY_DSN` | (empty) | Set to enable Sentry error tracking |
| `LIMS_ADMIN_PASSWORD` | `Admin@LIMS_2026!Sup` | Bootstrap admin password |
| `LIMS_DEMO_PASSWORD` | `Lims@2026!Init` | Demo-account password |
| `LIMS_ENFORCE_WAFER_CAP` | `True` | Strict 25-wafer-per-order split cap; `conftest.py` disables it for tests |
| `SEED_DEMO_DATA` | `True` | Set to `False` for production to skip demo seeds |

Frontend (Vite):

| Var | Default | Description |
|---|---|---|
| `VITE_API_BASE` | `http://127.0.0.1:8000/api` | Override to point at a deployed backend |

---

## 📚 Subsystem docs

- [`backend/README.md`](backend/README.md) — Django app structure, sample state machine, services, testing patterns
- [`frontend/README.md`](frontend/README.md) — Vue project layout, role-aware tabs, theming, i18n, admin console internals
- [`docs/README.md`](docs/README.md) — Deployment runbooks (kind / GCP / Argo CD), ops manual, account inventory
- [`helm/lims/README.md`](helm/lims/README.md) — Helm chart values + scaling knobs
- [`gitops/README.md`](gitops/README.md) — Argo CD GitOps pattern
- [`infra/README.md`](infra/README.md) — Terraform GCP foundation (VPC / NAT / subnets)

---

## 📝 License

Distributed under the MIT License.

---

*Built with care for semiconductor FAB excellence.*
