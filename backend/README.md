# LIMS Backend (Django 5.2 + DRF)

Server-side of the LIMS wafer-fab management system. Built around six focused
Django apps, with a **per-sample state-machine service layer**, specialty-gated
authorisation, a transactional schedule-conflict guard, Celery sweeps for
auto-close and alert fan-out, an audit-trail middleware that captures every
authenticated request, and a 285-test pytest suite covering the AAA pattern and
all five canonical test-double styles.

> If you arrived here looking for the project overview, see the
> [root README](../README.md).

---

## Table of contents

- [App map](#app-map)
- [Domain model](#domain-model)
- [Sample state machine](#sample-state-machine)
- [Role × specialty matrix](#role--specialty-matrix)
- [Workflow services](#workflow-services)
- [API surface](#api-surface)
- [Setup](#setup)
- [Configuration / environment](#configuration--environment)
- [Custom management commands](#custom-management-commands)
- [Celery tasks](#celery-tasks)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Common tasks](#common-tasks)

---

## App map

| App | Purpose | Key models |
|---|---|---|
| **users** | Identity, lab hierarchy, **specialty** | `FAB`, `Department`, `User` (`role` + `lab_specialty`) , `WaferLot` |
| **equipments** | Equipment catalogue + recipes | `Experiment`, `EquipmentType`, `Equipment`, `ExperimentRequiredEquipment`, `Recipe` (≥5 knobs guaranteed) |
| **orders** | Sample submission, sub-LOT relay, state machine | `Order`, `OrderStage`, `Sample`, `Approval` (+ `services.py`) |
| **scheduling** | Equipment-time bookings + typed audit events + Celery sweeps | `EquipmentBooking`, `StageEvent` (typed) |
| **monitoring** | Activity log, notifications, dashboard, reports, LOT history | `ActivityLog`, `Notification`, plus chart / drill-down views |
| **admin_api** | Superuser-only ModelViewSets (CRUD over 11 tables) | re-uses the above; defines admin-shaped serializers |

Cross-cutting `utils/` package: a `RequestIDMiddleware` plus a
`custom_exception_handler` that wraps every API error in a uniform envelope.

---

## Domain model

```
            ┌─────────┐ 1     N ┌────────────┐ 1     N ┌───────────────────────────┐
            │   FAB   │────────►│ Department │────────►│ User                       │
            └────┬────┘         └─────┬──────┘         │ role + lab_specialty       │
                 │ 1                  │                │ (coord/dispatcher/         │
                 │                    │ N              │  engineer/operator/none)   │
                 ▼ N                  ▼                └─────────┬─────────────────┘
            ┌──────────────┐    ┌──────────────────┐             │
            │  WaferLot    │    │ EquipmentType    │             │
            │  (code = PK) │    │ + Recipe (≥5     │             │ submitter
            └──────┬───────┘    │   knobs each)    │             │
                   │            └──────┬───────────┘             ▼
                   │ 1                 │ 1               ┌──────────┐
                   │                   │ N               │  Order   │
                   │                   ▼                 └────┬─────┘
                   │            ┌──────────────┐              │ 1
                   │            │  Equipment   │              │
                   │            │ (status,     │              ▼ 1
                   │            │  dept-scoped)│        ┌────────────┐
                   │            └──────┬───────┘        │ OrderStage │
                   │                   │                └──────┬─────┘
                   │                   │ 1                     │
                   ▼                   │                       │ 1..N    1..N ┌──────────┐
              (Order.lot)              │                       └─────────────►│ Approval │
                                       │ N                                    │ (append- │
                                       ▼                                      │  only)   │
                            ┌────────────────────┐  N        1                └──────────┘
                            │ EquipmentBooking   │◄─────────────┐
                            │ (overlap-checked,  │              │
                            │  released on done) │              │
                            └────────────────────┘              │
                                                                │
                            ┌──────────────────────────┐        │
                            │ StageEvent (typed enum:  │◄───────┤
                            │  receive / split /       │        │
                            │  dispatch / set_params / │        │
                            │  assign / load / unload /│        │
                            │  abort / note)           │        │
                            └──────────────────────────┘        │
                                                                │
                            ┌──────────────────────────┐        │
                            │ Sample (sub-LOT)         │        │
                            │  - created_by (coord)    │        │
                            │  - dispatched_by         │        │
                            │  - parameters_set_by     │        │
                            │  - assignee (operator,   │ N    1 │
                            │    auto-picked)          │────────┘
                            │  - loaded_by, completed_by│
                            │  - status enum           │
                            └──────────────────────────┘
```

All primary keys are UUIDs except `WaferLot.code` (which is the lot code itself).

---

## Sample state machine

`orders/services.py` encapsulates the lifecycle. Order moves WAITING → IN_PROGRESS
→ DONE as a side-effect of its samples; the actionable state lives on `Sample`.

```
              split_order()       dispatch_sample()    set_sample_parameters()
                ────►              ────►                ────►              ────►
   (none)  ─►  WAITING         ─►  DISPATCHED      ─►  PARAMS_SET     ─►  READY
   (Order      (created_by=        (equipment +       (parameters_       (assignee =
    APPROVED)   coord)              recipe +           set_by =            auto-picked
                                    schedule +         engineer)           operator,
                                    booking row)                           not upstream)
                                                                                │
                                                                                │ load_sample()
                                                                                ▼
                              report_sample_abnormal()                       RUNNING
                                 (abort + flip                                  │
                                  equipment to                                  │ complete_sample()
                                  maintenance)                                  ▼
                                                                                DONE
```

Allowed transitions are enforced inline in each service function;
`_require_specialty(...)` rejects calls from the wrong tier, and the
`各司其職` rotation rule on `assign_sample` rejects re-using any upstream
user as the operator.

---

## Role × specialty matrix

| Endpoint family | requester | coord | dispatcher | engineer | operator | manager | superuser |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Submit / read own order | ✅ (operator names masked) | — | — | — | — | — | ✅ |
| Sign-off / reject (auto-receives) | — | — | — | — | — | ✅ | ✅ |
| `split_order` (25-wafer hard cap) | — | ✅ | — | — | — | — | ✅ |
| `dispatch_sample` (overlap-guarded) | — | — | ✅ | — | — | — | ✅ |
| `set_sample_parameters` (→ auto-assign) | — | — | — | ✅ | — | — | ✅ |
| `load_sample` / `complete_sample` | — | — | — | — | ✅ (assignee) | — | ✅ |
| `record_sample_telemetry` | — | — | — | — | ✅ (assignee) | — | ✅ |
| `report_sample_abnormal` | — | — | — | — | ✅ (assignee) | — | ✅ |
| Reports (utilization / business / operator / LOT history) | — | — | — | — | — | ✅ own lab | ✅ all |
| Equipment status patch (→ CRITICAL alert) | — | — | — | — | — | ✅ own lab | ✅ all |
| `/admin/*` CRUD | — | — | — | — | — | — | ✅ |

Visibility scoping for **list / detail reads** is enforced row-level per
specialty (`_lab_member_order_filter` + `_lab_member_sample_filter`):

| Specialty | What `GET /api/orders/` and `/api/orders/samples/` return |
|---|---|
| `coord` | Orders in their lab with APPROVED stage + no samples yet (待分貨 queue) **OR** orders/samples they personally split |
| `dispatcher` | Orders/samples in their lab where any sub-LOT is WAITING **OR** samples they personally dispatched |
| `engineer` | Orders/samples in their lab where any sub-LOT is DISPATCHED **OR** samples they personally set parameters on |
| `operator` | Only orders/samples directly assigned to them |
| `lab_manager` | Everything in their lab |
| `superuser` | Everything |
| `regular_employee` | Their own orders, with operator identities scrubbed by `_MaskOperatorMixin` |

Out-of-scope reads return **404, not 403** — keeps existence opaque.

---

## Workflow services

Core service functions in [`orders/services.py`](orders/services.py):

| Function | Spec gate | Side-effects |
|---|---|---|
| `create_order(...)` | regular_employee / superuser | Creates Order + 1 OrderStage; notifies the lab manager. |
| `sign_off_stage(stage, actor, ...)` | manager / superuser | Writes `Approval`; **auto-stamps `received_at` + appends `receive` StageEvent**; notifies requester. |
| `reject_order(order, rejection_reason, actor)` | manager / superuser | Append-only Approval row with `decision='rejected'`; cancels downstream. |
| `split_order(order, splits, operator)` | specialty=coord, NO manager bypass | Creates `Sample` rows; **hard equality** on total wafer count (`WAFER_COUNT_PER_ORDER = 25`); writes `split` StageEvent. |
| `dispatch_sample(sample, operator, equipment, recipe, schedule_start, schedule_end)` | specialty=dispatcher | **Transactional `select_for_update` + overlap query on `EquipmentBooking`**; creates booking row; writes `dispatch` StageEvent. |
| `set_sample_parameters(sample, operator, parameter_overrides, auto_assign=True)` | specialty=engineer | Validates overrides against recipe knobs; writes `set_parameters` StageEvent; **calls `_auto_pick_assignee` → flips to READY + writes `assign` StageEvent + notifies the operator**. |
| `assign_sample(sample, operator, assignee)` | (manual fallback) — rejects non-operator specialty and upstream users (rotation rule) | Writes `assign` StageEvent. |
| `load_sample(sample, operator)` | assignee only | Time-locked against `schedule_start`; writes `load` StageEvent. |
| `record_sample_telemetry(sample, operator, measurement, finished)` | assignee only | Appends `note` StageEvent with JSON measurement; `finished=True` auto-closes via `complete_sample`. |
| `report_sample_abnormal(sample, operator, reason, flip_equipment)` | assignee only | Writes `abort` StageEvent; flips equipment to `maintenance`; sends CRITICAL Notification to engineers in the lab; shrinks the EquipmentBooking. |
| `complete_sample(sample, operator, measurement)` | assignee only | Writes `unload` StageEvent; shrinks EquipmentBooking to actual end-time; cascades to closing the stage/order when every sub-LOT is DONE. |

Helpers worth knowing:

- `_require_specialty(user, expected, label, allow_manager=True)` — the
  central authorization check. Superuser always passes; `allow_manager=False`
  for `split_order` (manager never carries out the split).
- `_auto_pick_assignee(sample)` — picks the lab_member with the lowest
  count of READY/RUNNING assignments, restricted to `lab_specialty='operator'`
  and excluding upstream (`created_by`, `dispatched_by`, `parameters_set_by`).

---

## API surface

| Prefix | Module | Endpoints |
|---|---|---|
| `/api/users/` | `users.urls` | `login` (JWT), `token/refresh`, `register`, `profile` (includes `lab_specialty`), `fabs`, `departments`, `<list>` |
| `/api/orders/` | `orders.urls` | `<list>` / `<detail>` / `create` / `<id>/samples/` (split) / `<id>/review` / `<id>/complete` |
| `/api/orders/stages/` |  | `<id>/review/` (sign-off) / `<id>/receive/` (manager fallback) / `<id>/events/` / `<id>/approvals/` |
| `/api/orders/samples/` |  | `<list>` / `<id>/dispatch/` / `<id>/parameters/` / `<id>/assign/` / `<id>/load/` / `<id>/telemetry/` / `<id>/report-abnormal/` / `<id>/complete/` |
| `/api/equipments/` | `equipments.urls` | `<list>` (pagination disabled), `types/`, `recipes/` (pagination disabled), `experiments/`, `status-matrix/`, `capacity-check/`, `<id>/telemetry/` |
| `/api/scheduling/` | `scheduling.urls` | `bookings/`, `availability-check/` |
| `/api/monitoring/` | `monitoring.urls` | `dashboard/`, `my-stats/` (specialty-aware cards), `logs/`, `notifications/` (+ `summary/`, `mark-read/`, `mark-all-read/`) |
| `/api/monitoring/charts/` |  | `equipment-utilization/`, `order-trend/`, `operator-activity/` (+ `<user_id>/` drill-down), `order-business/` |
| `/api/monitoring/lot-history/` |  | `<list>` (manager browse), `<sample_id>/` (per-LOT step-by-step timeline) |
| `/api/admin/` | `admin_api.urls` | DefaultRouter ViewSets — fabs, departments, users, wafer-lots, experiments, equipment-types, equipment, recipes, experiment-requirements, orders, order-stages, samples, bookings, stage-events, approvals |

All routes require JWT (`Bearer …`) except `/api/users/login/`,
`/api/users/register/`, and `/api/users/token/refresh/`.

Pagination is **disabled** on `RecipeListView` and `EquipmentListView` so the
dispatch dialog (which client-side filters recipes by equipment_type) never
loses options on page 2.

---

## Setup

### Option A — Docker Compose (recommended)

```bash
cd ..
docker compose up --build
```

The container's startup chain runs
`migrate → seed_demo_accounts → enrich_recipe_parameters → seed_demo_orders → gunicorn`,
so the DB lands populated.

### Option B — local venv

```bash
cd backend
python -m venv ../venv
source ../venv/bin/activate          # Windows: ..\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_accounts
python manage.py enrich_recipe_parameters
python manage.py seed_demo_orders
python manage.py runserver
```

The API listens on `http://127.0.0.1:8000`.

---

## Configuration / environment

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `True` | Set to `False` for production |
| `DJANGO_PRODUCTION` | `False` | When `True`: refuses dev secret + wildcard hosts; enables HSTS, SSL redirect, secure cookies |
| `DJANGO_SECRET_KEY` | dev fallback | Required when `DJANGO_PRODUCTION=True` |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated |
| `DB_ENGINE` | (sqlite) | `mysql` to switch backends |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | — | MySQL only |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Cache + Celery broker |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | For `auto_close_stalled_samples` + `alert_schedule_overruns` |
| `CORS_ALLOWED_ORIGINS` | dev frontends | Comma-separated origins |
| `SENTRY_DSN` | empty | Enable when present; otherwise inert |
| `LIMS_ADMIN_PASSWORD` | `Admin@LIMS_2026!Sup` | Bootstrap admin |
| `LIMS_DEMO_PASSWORD` | `Lims@2026!Init` | Demo accounts |
| `LIMS_ENFORCE_WAFER_CAP` | `True` | Strict 25-wafer-per-order cap; tests disable it in `conftest.py` |
| `SEED_DEMO_DATA` | `True` | Set to `False` for production to skip demo seeds |
| `DJANGO_LOG_LEVEL` | `INFO` | Stdlib logging level |

`CORS_ALLOW_ALL_ORIGINS` is **never** enabled.

---

## Custom management commands

| Command | What it does |
|---|---|
| `python manage.py seed_demo_accounts [--list-only] [--force-reseed]` | Provisions / reports the canonical demo roster — admin + 3 managers + 18 lab_members (6 per lab × 3 labs with specialties) + testuser. Idempotent. |
| `python manage.py seed_demo_orders [--force]` | Per lab, creates 5 demo orders (2 DONE, 1 IN_PROGRESS w/ a RUNNING + DISPATCHED sub-LOT, 1 REJECTED, 1 WAITING for manager, 1 APPROVED with a WAITING sub-LOT for dispatcher demo). Refuses to overwrite without `--force`. |
| `python manage.py enrich_recipe_parameters [--dry-run] [--min N]` | Tops every recipe up to a 5-knob baseline and creates a `Default-<type>` recipe for any EquipmentType with zero recipes. Idempotent. |
| `python manage.py clear_orders [--dry-run] [--diagnose-visibility]` | Wipes orders/stages/samples/bookings and resets equipment to available. Diagnose flag dumps experiment→dept→manager routing. |
| `python manage.py auto_close_stalled_samples [--grace MINUTES]` | Cron wrapper for the Celery task — closes RUNNING samples past their `schedule_end + grace`. |
| `python manage.py alert_schedule_overruns [--grace MINUTES]` | Cron wrapper for the Celery task — sends a CRITICAL Notification when a RUNNING sample has overrun. |

---

## Celery tasks

[`scheduling/tasks.py`](scheduling/tasks.py):

| Task | What it does |
|---|---|
| `scheduling.auto_close_stalled_samples(grace_minutes=5)` | Sweeps RUNNING samples whose `schedule_end + grace` is in the past and calls `complete_sample`. |
| `scheduling.alert_schedule_overruns(grace_minutes=30)` | Scans the same set and sends CRITICAL notifications to the sample's assignee + the lab managers when a run is significantly overdue. |

A Celery worker is started automatically by `docker-compose.yml` (`command:
celery -A backend worker -l info`). To run on a schedule, add a Celery Beat
config or call the management-command wrappers from a host cron.

---

## Testing

```bash
unset PYTHONPATH                        # avoid ROS humble's broken pytest plugin (Linux)
pytest
```

Current count: **285 passed**.

### Notable test files

| File | What it covers |
|---|---|
| `tests/test_sample_dispatch.py` | Full per-sample chain, specialty gates, rotation rule, **schedule-conflict overlap rejection** |
| `tests/test_samples.py` | `split_order` validation incl. exact 25-wafer cap (re-enabled via `settings.LIMS_ENFORCE_WAFER_CAP=True` in cap-specific tests) + manager-cannot-split |
| `tests/test_telemetry_alerts.py` | Telemetry endpoint, auto-close sweep, **alarm fan-out to engineers** |
| `tests/test_charts.py` | Utilization / order business / operator activity drill-down / per-LOT history endpoints |
| `tests/test_visibility_scoping.py` | Row-level scoping per role × specialty (+ operator-identity masking for requesters) |
| `tests/test_my_stats.py` | Specialty-specific dashboard cards |
| `tests/test_recipes.py` | Lab-scoped recipe listing (non-paginated) |
| `tests/test_receive.py` | 接件 auto-stamping on sign-off + manager-only fallback endpoint |
| `tests/test_monitoring_middleware.py` | `_redact`, `_classify`, `_client_ip`, persistence semantics |
| `tests/test_orders_services.py` | Five test-double styles in action |

### Five test-double styles (showcased in `test_orders_services.py`)

| Style | Where |
|---|---|
| **Fake** (full ORM) | `factory_boy` factories under `tests/factories.py` |
| **Stub** (canned input) | conftest fixtures (`lab_member`, `lab_dispatcher`, `lab_engineer`, `lab_operator`, …) |
| **Mock** (replace + verify) | `mocker.patch('scheduling.services.allocate_equipments_for_stage', return_value=[])` |
| **Spy** (observe without replacing) | `mocker.spy(services, '_send_notification')` |
| **Time fake** | `freezegun.freeze_time('2026-05-21 10:00:00')` |

### Pytest fixtures (in `conftest.py`)

| Fixture | Returns |
|---|---|
| `employee`, `lab_manager`, `lab_member` (= coord by default), `superuser` | A `User` of that role with department + fab attached |
| `lab_dispatcher`, `lab_engineer`, `lab_operator` | lab_member fixtures pinned to the matching `lab_specialty` |
| `employee_client`, `manager_client`, `member_client`, `superuser_client` | Pre-authenticated `APIClient` for each role |
| `equipment_type`, `equipment`, `experiment`, `order`, `order_stage`, `approved_order` | Domain objects via `factory_boy` |
| `api_client` | Anonymous `APIClient` |

---

## Project layout

```
backend/
├── backend/                # project conf
│   ├── settings.py         # env-driven, prod-aware
│   ├── celery.py           # Celery app + autodiscovery
│   └── urls.py             # /api/<app>/
│
├── users/
│   ├── models.py           # FAB, Department, User (UUID + role + lab_specialty), WaferLot
│   ├── serializers.py      # exposes lab_specialty on /profile/ + /users/
│   ├── views.py            # register, profile, list, JWT login (delegated)
│   └── migrations/         # 0006 adds lab_specialty
│
├── orders/
│   ├── models.py           # Order, OrderStage, Sample, Approval
│   ├── services.py         # split_order / dispatch_sample / set_sample_parameters /
│   │                       #  assign_sample / load_sample / record_sample_telemetry /
│   │                       #  report_sample_abnormal / complete_sample /
│   │                       #  sign_off_stage / reject_order / _require_specialty /
│   │                       #  _auto_pick_assignee
│   ├── serializers.py      # OrderListSerializer / OrderDetailSerializer /
│   │                       #  SampleSerializer (+ _MaskOperatorMixin)
│   ├── views.py            # OrderListView / OrderDetailView (with specialty-aware
│   │                       #  visibility) / OrderCreateView / OrderReviewView /
│   │                       #  SampleListView / SampleDispatchView / SampleParameters
│   │                       #  View / SampleAssignView / SampleLoadView /
│   │                       #  SampleTelemetryView / SampleReportAbnormalView /
│   │                       #  SampleCompleteView / OrderReceiveView / …
│   ├── management/commands/{clear_orders.py,seed_demo_orders.py}
│   └── migrations/
│
├── equipments/
│   ├── models.py           # Experiment, EquipmentType, Equipment, Recipe
│   ├── serializers.py
│   ├── views.py            # EquipmentListView (no pagination), RecipeListView
│   │                       #  (no pagination, lab-scoped), status-matrix,
│   │                       #  capacity-check, telemetry
│   ├── management/commands/enrich_recipe_parameters.py
│   └── migrations/         # 0007_seed_recipes + 0010_enrich_recipe_parameters
│
├── scheduling/
│   ├── models.py           # EquipmentBooking + StageEvent (typed EventType)
│   ├── services.py         # allocate_equipments + record_stage_event
│   ├── tasks.py            # auto_close_stalled_samples + alert_schedule_overruns
│   ├── management/commands/{auto_close_stalled_samples.py,alert_schedule_overruns.py}
│   └── migrations/         # 0005_alter_stageevent_event_type
│
├── monitoring/
│   ├── models.py           # ActivityLog + Notification (+ post_save fan-out signal)
│   ├── middleware.py       # ActivityLogMiddleware
│   ├── signals.py          # Equipment status change → CRITICAL notification
│   ├── permissions.py      # IsSystemSuperuser
│   ├── serializers.py
│   ├── views.py            # DashboardStatsView / MyStatsView (specialty-aware) /
│   │                       #  ChartEquipmentUtilizationView / ChartOrderTrendView /
│   │                       #  ChartOperatorActivityView (+ Detail) /
│   │                       #  ChartOrderBusinessView / SampleHistoryView /
│   │                       #  SampleListForReportsView / NotificationListView / …
│   ├── urls.py
│   ├── admin.py
│   └── management/commands/ensure_admin.py
│
├── admin_api/
│   ├── serializers.py      # admin-shaped serializers (denormalised labels)
│   ├── views.py            # 11 ModelViewSets gated by IsSystemSuperuser
│   └── urls.py             # DefaultRouter
│
├── utils/
│   ├── request_id.py       # X-Request-ID middleware
│   └── exception_handler.py # uniform DRF error envelope + 5xx masking
│
├── tests/
│   ├── conftest.py         # role + specialty fixtures + approved_order
│   ├── factories.py        # LabCoord/Dispatcher/Engineer/OperatorFactory + ...
│   └── test_*.py           # 285 cases across ~20 files
│
├── pytest.ini
├── requirements.txt
└── manage.py
```

---

## Common tasks

### Add a new domain model

1. Define the model in the relevant app (`<app>/models.py`).
2. `python manage.py makemigrations <app>` and inspect the migration before committing.
3. If the superuser console should manage it:
   - Add a serializer in `admin_api/serializers.py` (denormalise labels for the table view).
   - Register a `ModelViewSet` in `admin_api/views.py` and route it in `admin_api/urls.py`.
4. Add a factory in `tests/factories.py`.
5. Cover the new behaviour with an integration test.

### Promote a regular user to a specific specialty

```bash
python manage.py shell -c "from users.models import User; u = User.objects.get(username='alice'); u.role = 'lab_member'; u.lab_specialty = 'dispatcher'; u.save()"
```

### Re-seed the demo data

```bash
docker compose exec backend python manage.py seed_demo_orders --force
```

(Or any of `seed_demo_accounts` / `enrich_recipe_parameters` individually — all idempotent.)

### Add a new specialty-gated service

1. Build the service in `<app>/services.py`. Open with `_require_specialty(operator,
   expected=User.LabSpecialty.<TIER>, label='中文步驟名稱',
   allow_manager=<bool>)`.
2. Add a view in `<app>/views.py` that gates on `request.user.role` first, then
   defers to the service (it owns the specialty + business-rule checks).
3. Add fixture coverage in `tests/test_<app>.py` using `LabCoordFactory` /
   `LabDispatcherFactory` / `LabEngineerFactory` / `LabOperatorFactory`.

### Tail the audit trail in dev

```python
python manage.py shell -c "from monitoring.models import ActivityLog; [print(l) for l in ActivityLog.objects.order_by('-timestamp')[:20]]"
```
