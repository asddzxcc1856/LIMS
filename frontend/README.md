# LIMS Frontend (Vue 3 + Vite)

Single-page application for the LIMS wafer-fab management system. Built on
Vue 3 (Composition API + `<script setup>`), styled end-to-end with
**ant-design-vue**, state managed with Pinia, navigation guarded by Vue Router,
and internationalised to Traditional Chinese (default) + English with a
runtime light/dark theme switch.

The lab-member workbench is **specialty-aware**: each role only sees the
tabs they actually act on (coord sees 待分貨, dispatcher sees 待派工,
engineer sees 待設定參數, operator sees 上下貨), so colleagues can't step
on each other's tasks.

> Looking for the project overview? See the [root README](../README.md).
> The Django backend is documented in [`../backend/README.md`](../backend/README.md).

---

## Table of contents

- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Setup](#setup)
- [Development](#development)
- [Testing](#testing)
- [Theming and i18n](#theming-and-i18n)
- [Role + specialty UI gating](#role--specialty-ui-gating)
- [Admin console internals](#admin-console-internals)
- [Manager reports](#manager-reports)
- [Routing and role guards](#routing-and-role-guards)
- [API client](#api-client)
- [Common tasks](#common-tasks)

---

## Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Framework | Vue 3.5 | Composition API + `<script setup>` everywhere |
| Build | Vite 8 | `vite.config.js` left intentionally minimal |
| State | Pinia 3 | `auth` store (role + lab_specialty + can* flags) + `settings` store |
| Router | Vue Router 4 | Role-aware guards via `meta.roles` |
| UI library | ant-design-vue 4 | `<a-config-provider>` powers theme + locale switching |
| Icons | `@ant-design/icons-vue` | Tree-shaken |
| HTTP | axios | JWT interceptor + automatic refresh-on-401 in `api/client.js` |
| i18n | vue-i18n 9 | Composition API mode (`legacy: false`) |
| Charts | hand-rolled SVG `LineChart` / `BarChart` | No external chart dep — keeps the bundle small |
| Date | dayjs | Used by every date-picker / formatter |
| Unit / component testing | vitest 3 + @vue/test-utils + jsdom | `npm test` |
| End-to-end | Playwright (chromium) | `npm run e2e` |

---

## Project layout

```
frontend/
├── src/
│   ├── api/
│   │   ├── client.js            # axios instance + JWT interceptor + refresh-on-401
│   │   ├── users.js             # /api/users/*
│   │   ├── orders.js            # /api/orders/* incl. samples/<id>/dispatch / parameters /
│   │   │                        #   assign / load / telemetry / report-abnormal / complete
│   │   ├── equipments.js        # /api/equipments/* (+ patchEquipment for status flips)
│   │   ├── scheduling.js        # /api/scheduling/*
│   │   └── admin.js             # uniform CRUD wrappers + dashboard / logs /
│   │                            #   chart endpoints / lot-history list + detail
│   │
│   ├── stores/
│   │   ├── auth.js              # JWT + user profile + role + labSpecialty +
│   │   │                        #   canSplit / canDispatch / canSetParameters / canOperate
│   │   └── settings.js          # locale + theme + persistence
│   │
│   ├── router/
│   │   └── index.js             # routes + role-aware navigation guard
│   │
│   ├── i18n/
│   │   ├── index.js             # createI18n, reads persisted locale
│   │   ├── zh-TW.js             # Traditional Chinese catalogue (incl. recipe-knob labels)
│   │   └── en.js                # English catalogue
│   │
│   ├── components/
│   │   ├── TimelineChart.vue    # Equipment booking timeline
│   │   ├── SampleSplitDialog.vue # 分貨 dialog with 25-wafer cap + running total alert
│   │   ├── NotificationBell.vue # Bell with unread + critical badge
│   │   ├── charts/
│   │   │   ├── LineChart.vue    # Hand-rolled SVG
│   │   │   └── BarChart.vue
│   │   └── admin/
│   │       └── CrudTable.vue    # Generic CRUD driving 10 admin pages
│   │
│   ├── views/
│   │   ├── LoginView.vue        # gradient brand card, antd Form rules
│   │   ├── RegisterView.vue
│   │   ├── DashboardView.vue    # Specialty-aware MyStats cards + Recent Orders
│   │   ├── EquipmentDashboardView.vue   # Equipment grid + manager-only status quick-change
│   │   │
│   │   ├── requester/
│   │   │   ├── OrderListView.vue        # antd Table + relay Steps drawer
│   │   │   │                            # (operator names auto-masked)
│   │   │   └── OrderCreateView.vue      # antd Form + capacity preview
│   │   │
│   │   ├── manager/
│   │   │   ├── OrderReviewView.vue      # 簽核 modal — auto-reload on success
│   │   │   └── ManagerReportsView.vue   # Utilization line + KPI strip +
│   │   │                                #   stage/sub-LOT status tables +
│   │   │                                #   operator activity bar with timeline drill +
│   │   │                                #   子 LOT 履歷追蹤 timeline
│   │   │
│   │   ├── member/
│   │   │   └── OrderTasksView.vue       # Tabs gated by auth.canSplit /
│   │   │                                #   canDispatch / canSetParameters /
│   │   │                                #   canOperate; abnormal report modal
│   │   │
│   │   └── admin/
│   │       ├── AdminLayout.vue          # /admin shell — collapsible dark sider
│   │       ├── DashboardView.vue        # KPI cards + 30 s auto-refresh
│   │       ├── ActivityLogsView.vue     # 6 filters + detail Drawer
│   │       └── …                        # 10 CRUD pages (FAB/Dept/User/…)
│   │
│   ├── composables/
│   │   ├── useBreakpoint.js     # window-width reactive helper
│   │   └── useLocalizedLabel.js # picks name_en vs name based on active locale
│   │
│   ├── App.vue                  # ConfigProvider + layout shell + Settings drawer
│   ├── main.js                  # plugins: pinia, router, i18n, antd
│   └── style.css                # tokens + dark/light CSS variables
│
├── tests/                                # vitest unit / component tests
│   ├── setup.js                          # localStorage polyfill (Node 25 fix)
│   ├── auth.store.test.js                # auth store + role + specialty computeds
│   ├── settings.store.test.js
│   ├── admin.api.test.js                 # axios stubs for every admin CRUD verb
│   ├── LoginView.test.js
│   ├── CrudTable.test.js
│   ├── SampleSplitDialog.test.js         # 25-wafer cap validation
│   └── NotificationBell.test.js
│
├── e2e/                                  # Playwright specs
│   ├── login.spec.js
│   ├── admin-console.spec.js
│   └── admin-crud.spec.js
│
├── playwright.config.js
├── vitest.config.js
├── vite.config.js
└── package.json
```

---

## Setup

```bash
cd frontend
npm install
npm run dev     # http://127.0.0.1:5173
```

Backend must already be running on `http://127.0.0.1:8000`. Override with
`VITE_API_BASE` if pointing at a remote backend:

```bash
VITE_API_BASE=https://api.lims.example.com/api npm run dev
```

---

## Development

| Command | Effect |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview the production build |
| `npm test` | Run vitest once |
| `npm run test:watch` | Vitest in watch mode |
| `npm run test:coverage` | Vitest + v8 coverage report |
| `npm run e2e` | Playwright (auto-starts vite via webServer config) |
| `npm run e2e:ui` | Playwright UI mode |

The dev server hits the backend at `VITE_API_BASE` (default
`http://127.0.0.1:8000/api`). CORS is whitelisted for `localhost:5173` and
`127.0.0.1:5173` on the Django side.

---

## Testing

### Unit / component (vitest)

**55 cases** across 8 files.

| File | Coverage focus |
|---|---|
| `auth.store.test.js` | Token persistence, logout cleanup, profile-load failure path, role + specialty computed matrix |
| `settings.store.test.js` | Defaults, persistence, unknown-value rejection, toggle helpers, `data-theme` DOM stamping |
| `admin.api.test.js` | Every CRUD verb of every admin resource + dashboard / log / chart fetchers (axios stubbed) |
| `LoginView.test.js` | Form wiring + login flow + backend error message surfacing |
| `CrudTable.test.js` | Generic CRUD lifecycle: pagination, search reload, modal init, write-only password handling, delete reload |
| `SampleSplitDialog.test.js` | Cleaning + numeric coercion + 25-wafer cap validation |
| `NotificationBell.test.js` | Unread badge + critical-only filter + mark-all-read |

The `tests/setup.js` polyfills `localStorage` because Node 25 ships an
experimental built-in whose Web Storage methods are missing. jsdom 29
surfaces the same broken object on `window.localStorage`, so production
code that calls `localStorage.getItem(...)` would otherwise crash.

### End-to-end (Playwright)

**8 cases** across 3 files. Run with `npm run e2e` (the backend must be
available on `:8000` first).

| File | Coverage |
|---|---|
| `login.spec.js` | Empty-form validation, bad-credential error envelope, admin happy path |
| `admin-console.spec.js` | Dashboard KPI cards, log filter UI, sidebar nav, non-superuser router guard |
| `admin-crud.spec.js` | Full lifecycle: create → search → edit → delete an `EquipmentType` via the UI |

Selectors absorb ant-design's CJK button-spacing quirk (`登入` → `登 入`)
through a regex helper. Page titles anchor on
`.ant-page-header-heading-title` to disambiguate from sidebar / breadcrumb.

---

## Theming and i18n

Both preferences live in `stores/settings.js`, persist to localStorage, and
apply instantly without reloading.

### How theme switching works

- `App.vue` wraps everything in `<a-config-provider :theme="...">`.
- `theme.algorithm` is bound to `darkAlgorithm` or `defaultAlgorithm` based
  on `useSettingsStore().isDark`. Every antd component switches automatically.
- `style.css` defines a dark-mode block under `:root[data-theme='dark']` for
  the legacy `--c-*` custom properties used by `TimelineChart`.
- The store stamps `data-theme="dark"` onto `<html>` so global CSS sees it.

### How language switching works

- `App.vue` binds `<a-config-provider :locale="...">` to either `zh_TW` or
  `en_US` from ant-design-vue's bundled locales — that swaps date pickers,
  pagination text, etc.
- A `watch` on `settings.locale` updates vue-i18n's active locale.
- vue-i18n catalogues live in `src/i18n/zh-TW.js` and `src/i18n/en.js`.

### Add a new locale string

1. Add the key under both `zh-TW.js` and `en.js`. Match the nesting style
   (`auth.login`, `dashboard.totalOrders`, …).
2. In a component:
   ```vue
   <script setup>
   import { useI18n } from 'vue-i18n'
   const { t } = useI18n()
   </script>
   ```
3. For interpolations: `t('dashboard.welcome', { name: user.username })`.

### Recipe-knob labels

`paramLabel.<key>` in `zh-TW.js` maps every Recipe parameter key (e.g.
`accel_kV`, `helium_flow_sccm`, `beam_current_uA`) to a Chinese label
so the engineer's params dialog shows `加速電壓 (kV)` instead of the raw
DB key. New knobs added by `enrich_recipe_parameters` need a matching
entry here.

---

## Role + specialty UI gating

The `auth` store exposes a set of computed flags that drive both the
`/orders/tasks` tab visibility and the nav menu:

| Computed | True when | Used by |
|---|---|---|
| `isManager` | `role ∈ {lab_manager, superuser}` | Review / Reports nav entries |
| `isMember` | `role ∈ {lab_member, lab_manager, superuser}` | Dashboard quick-action panel |
| `isSuperuser` | role + `is_superuser` flag | Admin console entry |
| `labSpecialty` | `user.lab_specialty` string | UI gating below |
| `canSplit` | superuser OR `labSpecialty === 'coord'` | 待分貨 tab + split button |
| `canDispatch` | superuser OR `labSpecialty === 'dispatcher'` | 待派工 tab + dispatch button |
| `canSetParameters` | superuser OR `labSpecialty === 'engineer'` | 待設定參數 tab + params modal |
| `canOperate` | superuser OR `labSpecialty === 'operator'` | 進行中・上下貨 tab + load/abnormal buttons |

Managers intentionally **do NOT bypass** these computed flags — they have
their own Review / Reports pages and never touch the per-specialty workbench.
The router meta on `/orders/tasks` is restricted to `['lab_member', 'superuser']`.

`OrderTasksView` chooses its default active tab based on the same flags
so e.g. a `dispatcher` lands on 待派工 instead of the (hidden) 待分貨.

---

## Admin console internals

`/admin/*` is a self-contained shell rendered by `views/admin/AdminLayout.vue`.
It bypasses the main app shell because the route guard in `router/index.js`
sets `meta.roles = ['superuser']`, and `App.vue` skips its own layout for
paths starting with `/admin`.

### The CrudTable component

`components/admin/CrudTable.vue` is the workhorse: every admin CRUD page is
~40 lines of `columns + formFields` configuration on top of it.

| Prop | Purpose |
|---|---|
| `resource` | An object exposing `{ list, retrieve, create, update, remove }`. Each `api/admin.js` export already has this shape. |
| `columns` | ant-design `<a-table>` column descriptors |
| `formFields` | Custom shape: `{ name, label, type, required, options, optionsResource, optionLabel, span, defaultValue, writeOnly, nullableEmpty, help, rules }` |
| `searchPlaceholder` | Search input placeholder |
| `defaultOrdering` | Initial `ordering=` query parameter |

`writeOnly: true` (used for password fields) keeps the value out of the read
view: on edit, leaving it empty submits without that key, so passwords don't
get reset.

`optionsResource` lets a select dropdown lazily load its choices from another
admin endpoint.

---

## Manager reports

`/reports` (`views/manager/ManagerReportsView.vue`) is the primary
oversight surface for `lab_manager` and `superuser`. It pulls four
endpoints in parallel and renders:

1. **Order business KPI strip** — created / done / rejected / in-progress
   counts + rejection rate + mean lead times (done / rejected / sign-off latency).
2. **Daily charts** — equipment utilization line chart + order trend
   (created / done / rejected per day).
3. **Status breakdowns** — three side-by-side tables: stage status,
   sub-LOT status, per equipment type (running stages + completed sub-LOTs +
   mean run hours).
4. **Operator activity** — bar chart + drill-down table. Each row expands
   to a timeline of that operator's approvals, stage events, and sample
   lifecycle stamps.
5. **子 LOT 履歷追蹤** — every Sample in the lab over the window, with the
   per-step user names pre-joined into the row. Clicking expands a vertical
   `<a-timeline>` showing every milestone for that sub-LOT (簽核 / 接件 /
   分貨 / 派工 / 設定參數 / 指派 / 上貨 / 量測 / 下貨 / 中止 · 異常).

Lab managers see only their own lab; superusers see every lab.

---

## Routing and role guards

`router/index.js` registers a `beforeEach` guard that:

1. Loads the user profile if a JWT exists but no user object.
2. Redirects authenticated users away from `meta.guest` routes (login / register).
3. Redirects unauthenticated users to `/login`.
4. Redirects users whose `auth.role` isn't in `meta.roles` to `/`.

Standalone routes (login, register, `/admin/*`) bypass the main shell and
render their own layout — `App.vue` checks via the `STANDALONE_PREFIXES` array.

---

## API client

`src/api/client.js` configures a single axios instance with:

- `baseURL` from `VITE_API_BASE` (default `http://127.0.0.1:8000/api`)
- A request interceptor that attaches `Authorization: Bearer <access_token>`
- A response interceptor that, on 401, attempts a single `/users/token/refresh/`
  call, queues other in-flight 401s, and replays them with the new token. If
  refresh fails, it clears tokens and redirects to `/login`.

Per-domain modules (`api/users.js`, `api/orders.js`, …) wrap specific endpoints
with named functions. `api/admin.js` exposes a uniform `resource(name)` factory
returning `{ list, retrieve, create, update, remove }`, so `CrudTable` doesn't
need to know which endpoint it's talking to.

### Backend response shape

The `/api/equipments/` and `/api/equipments/recipes/` endpoints are
intentionally **non-paginated** (the dispatch dialog filters them
client-side by equipment_type). Other list endpoints follow the DRF
default `{count, next, previous, results}` shape. Per-domain wrappers
handle both via `data.results || data || []`.

---

## Common tasks

### Add a new admin CRUD page

1. Add an `admin<NewModel>` resource to `api/admin.js`:
   ```js
   export const adminNewModel = resource('new-model')
   ```
2. Create `views/admin/NewModelView.vue` using `<CrudTable>` with `columns`
   and `formFields` configs.
3. Wire it up in `router/index.js` under the `/admin` parent.
4. Add the menu entry in `views/admin/AdminLayout.vue`'s `menuConfig`.

### Add a new role-restricted page

```js
{
  path: '/secret',
  component: SecretView,
  meta: { roles: ['lab_manager', 'superuser'] },
}
```

The router guard already enforces `meta.roles`. No further code needed.

### Add a new specialty-gated tab

1. Add the relevant `can<Step>` computed in `stores/auth.js`.
2. Gate the `<a-tab-pane>` with `v-if="auth.can<Step>"`.
3. Pin the tab's default key in the parent's `_defaultTab()` helper.

### Translate a page

Already covered in [Theming and i18n § Add a new locale string](#add-a-new-locale-string).

### Run only one e2e spec

```bash
npx playwright test e2e/login.spec.js
npx playwright test -g "admin login"           # by test title regex
```
