# LIMS — Project Context Prompt

複製整份貼給任何 AI / 新進工程師,即可拿到完整專案上下文。本文件會跟程式碼一起 commit,作為持續的 source of truth。

---

## 你接手的是什麼專案

LIMS (Lab Information Management System) — 給半導體 wafer fab 用的晶圓送樣 +
排程 + 即時追蹤系統。每張 Order 對應一個 25-wafer FOUP,在實驗室內被切成多個
子 LOT (`Sample`),每片子 LOT 獨立決定機台、Recipe、參數、操作員、排程。

架構:Vue 3 SPA + Django REST + MySQL 8 + Redis 7 + Celery 5,以 GitOps 方式
(Helm + Argo CD ApplicationSet) 部署在 GKE Autopilot 上,使用 lims.ddns.net
對外。期末 demo 部署規格 (Scenario B): ~$210/月,$300 GCP free credit 撐 ~1.5
個月,所有功能保留。

---

## 領域模型 (絕對不要破壞的 invariant)

**四種 role × 五種 lab_specialty** (`backend/users/models.py`):

| 角色 | 專長欄位 (`lab_specialty`) | 在 LIMS 內做什麼 |
|---|---|---|
| `regular_employee` (廠區送樣使用者) | — | 送樣;只看自己 Order;**operator 身分被遮蔽**,只看到實驗室名稱 |
| `lab_manager` (實驗室主管) | — (none) | 簽核 / 駁回 (auto-接件)、Reports、機台狀態切換。**不可碰 split / dispatch / set_params**(specialty gate 直接 reject) |
| `lab_member` + `coord` | 分貨 | Lab_Mem_*_001 — 簽核完成後負責 split,每張 Order 必須剛好 25 片 |
| `lab_member` + `dispatcher` | 派工 | Lab_Mem_*_002 — 派工 (機台 + Recipe + 排程);**schedule_conflict 由 `EquipmentBooking` 做 `select_for_update` 攔截** |
| `lab_member` + `engineer` | 設定參數 | Lab_Mem_*_003 — 調 recipe knobs;set_sample_parameters 完成後自動觸發 auto-assign |
| `lab_member` + `operator` | 機台執行 | Lab_Mem_*_004 / 005 / 006 — 系統依工作量自動指派,執行 上貨 / 量測 / 下貨 / 回報異常 |
| `superuser` (admin) | — | 全域,bypass 所有 specialty / role gate |

**訂單流程** (`backend/orders/services.py`):

1. 廠區使用者選 Experiment + 從 WaferLot 下拉選 Lot ID + 寫實驗需求 → 送出 Order
2. Order 自動 route 到該 Experiment 對應的 Department
3. 主管在審核列表看到 → `sign_off_stage` (auto-stamps `received_at` + writes `Approval` row + `receive` `StageEvent`)
4. Coord (001) 做 `split_order` → 創 1+ 個 `Sample`,總片數必須剛好 25
5. Dispatcher (002) 對每個 sample 做 `dispatch_sample` → 機台 + Recipe + 排程,寫 `EquipmentBooking` 攔截後續衝突
6. Engineer (003) 對每個 sample 做 `set_sample_parameters` → 調 recipe knobs;**完成後自動觸發 `_auto_pick_assignee`** 把 sample 指給某位 operator
7. Operator 透過 `load_sample` → RUNNING → `complete_sample` 結單
   - 中途可 `record_sample_telemetry` 上傳量測,`finished=True` 自動結單
   - 中途可 `report_sample_abnormal` 回報異常,backend 切機台為 `maintenance` + 通知 engineer
8. 每個 sample 都 DONE 後,Order 自動 close;requester 收通知

**Hard invariants — 絕對不要違反:**
- 一個 Experiment 釘一個 Department (`Experiment.department` 必填)
- 一張 Order 只有一個 OrderStage;Sample 切自這個 stage 的 Order
- `Order.department == OrderStage.department == Experiment.department`
- `WaferLot.code` 是 primary key,`Order.lot` 是 FK 不是 free-text
- **`split_order` 必須讓 Order 的累計 wafer_count = `WAFER_COUNT_PER_ORDER` (25)**;低於或高於皆 reject(test 環境用 `settings.LIMS_ENFORCE_WAFER_CAP=False` opt-out)
- **`assign_sample` 的 `assignee` 必須是 `operator` specialty 且非上游 (created_by / dispatched_by / parameters_set_by)** — 各司其職 rotation rule
- **`dispatch_sample` 必須拒絕重疊 `EquipmentBooking`** (半開區間 `started_at__lt=new_end AND ended_at__gt=new_start`)
- 廠區使用者送樣表單只有「實驗類型 / Lot ID 下拉 / 實驗需求 / 備註 / 緊急」,**不顯示機台類型 / 機台代碼 / 操作員名稱**
- `/orders/tasks` 路由 lab_manager 沒權限進去(router meta `roles=['lab_member','superuser']`),manager 用 Reports / Review
- demo 帳號只在 `SEED_DEMO_DATA=True` 時建,prod 預設 False;`admin` 永遠建,密碼來自 `LIMS_ADMIN_PASSWORD`

---

## Tech stack (具體版本)

| 層 | 細節 |
|---|---|
| Backend | Django 5.2 + DRF 3.17 + simplejwt 5.5 + django-cors-headers 4.9 + django-prometheus 2.4 + WhiteNoise 6.7 + python-json-logger 4 |
| DB driver | PyMySQL 1.1 + cryptography(MySQL 8 caching_sha2_password 必要) |
| Redis | Cache backend `django.core.cache.backends.redis.RedisCache` + Celery 5.6 broker(同一 instance) |
| Celery tasks | `scheduling.tasks.auto_close_stalled_samples` + `alert_schedule_overruns`(Celery Beat schedule;沒裝 beat 也不會壞) |
| Frontend | Vue 3 + Vite 8 + Ant Design Vue 4 + Pinia 3 + vue-i18n 9 + axios + dayjs + 手刻 SVG `LineChart` / `BarChart` |
| Image | `python:3.11-slim` builder→runtime,UID 10001 non-root,readOnlyRootFilesystem;`nginx:1.27-alpine` 同樣 non-root |
| K8s | Helm chart 14 個 templates(Deployment, Service, Ingress, ManagedCertificate, BackendConfig, FrontendConfig, HPA, PDB, NetworkPolicy, PodMonitor, ManagedPrometheusPodMonitoring, ConfigMap, ExternalSecret, Job, ServiceAccount) |
| Infra | Terraform 1.7+ + google provider ~5.40 — modules: network, gke, cloudsql, memorystore, artifact-registry, iam |
| GitOps | Argo CD ApplicationSet + AppProject;sync waves: -10 (config/secret/SA) → -5 (migrate Job, Sync hook) → 0 (deployments) |
| Observability | GCP Managed Prometheus + Cloud Logging + Cloud Trace (demo);自架 kube-prom-stack + Loki + Tempo + OTel Collector 為 optional |
| Tests | 285 pytest + 55 vitest + 8 Playwright e2e — `cd backend && pytest`、`cd frontend && npm test`、`npm run e2e` |
| CI | GitHub Actions:lint + pytest + vitest + e2e Playwright + Trivy scan + push to Artifact Registry + bump gitops tag(全部 keyless 透過 Workload Identity Federation) |

---

## Repo 結構

```
backend/                Django + Dockerfile.k8s (K8s) + Dockerfile (legacy docker-compose)
  backend/              Django settings + health.py (/healthz, /readyz)
  users/                User (role + lab_specialty), FAB, Department, WaferLot
  orders/               Order, OrderStage, Sample, Approval + services.py
                        (split_order, dispatch_sample, set_sample_parameters,
                         assign_sample, load_sample, complete_sample,
                         record_sample_telemetry, report_sample_abnormal,
                         sign_off_stage, ...)
  equipments/           Experiment, EquipmentType, Equipment, Recipe (≥5 knobs)
  scheduling/           EquipmentBooking + StageEvent (typed: receive / split /
                        dispatch / set_parameters / assign / load / unload /
                        abort / note) + Celery tasks
  monitoring/           ActivityLog + Notification + reports endpoints
                        (utilization / order business / operator activity drill /
                         per-LOT history timeline) + RequestIDMiddleware
  admin_api/            superuser CRUD endpoints (10+ models)
  utils/                logging_filters (CorrelationFilter), exception_handler
  tests/                285 tests, factories (LabCoord/Dispatcher/Engineer/
                        OperatorFactory), conftest with per-specialty fixtures

frontend/               Vue SPA + Dockerfile.k8s (nginx) + Dockerfile (Caddy legacy)
  src/views/
    requester/          OrderList (operator names auto-masked), OrderCreate
    manager/            OrderReview (sign-off auto-refresh) + ManagerReports
                        (KPI strip + stage/sub-LOT status breakdown +
                         operator activity drill + per-LOT timeline)
    member/             OrderTasks (specialty-gated tabs:
                        coord→分貨, dispatcher→派工, engineer→設定參數,
                        operator→上下貨)
    admin/              12 admin pages — dashboard, logs, 10 CRUD pages
  src/stores/auth.js    role + labSpecialty + canSplit/canDispatch/
                        canSetParameters/canOperate computed flags
  src/i18n/{zh-TW,en}.js
  src/api/{client,users,orders,equipments,scheduling,admin}.js
  src/components/charts/{LineChart,BarChart}.vue
  tests/                55 vitest, e2e/ 8 Playwright

helm/lims/              Helm chart
  Chart.yaml, values.yaml(production-leaning defaults)
  envs/{local,dev,staging,prod}.yaml      per-env overrides
  templates/*.yaml      14 個 K8s templates

infra/                  Terraform IaC
  modules/{network,gke,cloudsql,memorystore,artifact-registry,iam}
  envs/{dev,staging,prod}/{main.tf,variables.tf,terraform.tfvars.example}

gitops/                 Argo CD GitOps
  projects/lims.yaml                       AppProject (RBAC scope)
  applicationsets/{lims,observability}.yaml ApplicationSet × 2
  applications/lims-local.yaml              kind 用單獨 Application
  envs/{dev,staging,prod}/values.yaml       CI 自動 bump image.tag

scripts/
  kind-config.yaml      kind cluster 配置(host 8080 → node 30080)
  kind-deps.yaml        in-cluster mysql:8.0 + redis:7-alpine

.github/workflows/
  ci.yml                push/PR:lint → pytest → vitest → e2e → build
  cd.yml                main push:build → push to Artifact Registry → Trivy → bump gitops/envs/dev/values.yaml

docs/                   操作手冊
  01-LOCAL-KIND-VALIDATION.md       本地 kind 驗證
  02-GCP-BRINGUP-RUNBOOK.md         GCP 從零上線(11 step)
  03-ACCOUNTS-AND-CREDENTIALS.md    四層帳號 + 密碼 + 輪替
  04-OPERATIONS-MANUAL.md           日常維運(含 §L 暫停/恢復)
  05-POST-SETUP-NOTES.md            上線後 24h/1w 硬化清單
  06-ARGO-CD-ON-KIND.md             本地演練 Argo CD GitOps
  07-DEMO-COST-OPTIMIZATION.md      Scenario B 成本拆解 + 30 天行事曆
  HTTPS_DEPLOYMENT.md               HTTPS 升級指引
  README.md                         索引

Makefile                kind-{up,down,deps,build,load,deploy,status,test} + gcp-{pause,resume,destroy}
CLOUD_NATIVE_CHECKLIST.md  REPLACE-ME 速查
PROJECT-CONTEXT.md      本文
```

---

## 部署路徑

1. **Legacy docker-compose** (`docker-compose.yml`) — 本機開發 / 期末 demo 主路徑。
   `command:` 已串好 `migrate → seed_demo_accounts → enrich_recipe_parameters → seed_demo_orders → gunicorn`,
   `docker compose up --build` 即可。
2. **本地 kind 驗證** — `make kind-up && kind-deps && kind-build && kind-load && kind-deploy`,
   然後 `http://localhost:8080`(NodePort 30080)。詳見 docs/01
3. **本地 kind + Argo CD GitOps 演練** — 多裝 Argo CD,套
   `gitops/applications/lims-local.yaml`,看 sync waves 跑完。docs/06
4. **GCP demo (Scenario B, ~$210/月)** — 預設 Terraform/Helm 值已調好。docs/02 + 07
5. **GCP real prod (Scenario A, ~$700/月)** — Cloud SQL HA + Memorystore Standard 5GB + 自架 observability。docs/07 §F 的 5 行 Terraform diff

DDNS:`lims.ddns.net` A record 指向 `terraform output ingress_static_ip_address`。

---

## 帳號 (demo seed)

`SEED_DEMO_DATA=True` 才建,密碼皆為 `Lims@2026!Init`(可以 `LIMS_DEMO_PASSWORD` 覆寫)。

- `testuser` — regular_employee, attached to Photo lab
- `Lab_Mgr_Photo` / `Lab_Mgr_Process` / `Lab_Mgr_QC` — lab_manager
- 每個 lab 6 位 lab_member,specialty 分配如下(Photo 為例,其他兩個 lab 同 pattern):
  - `Lab_Mem_Photo_001` — `coord` (分貨)
  - `Lab_Mem_Photo_002` — `dispatcher` (派工)
  - `Lab_Mem_Photo_003` — `engineer` (設定參數)
  - `Lab_Mem_Photo_004 / 005 / 006` — `operator` (機台執行,系統從 pool 自動指派)

**永遠建的 superuser**:`admin`,密碼來自 `LIMS_ADMIN_PASSWORD` env
(本地 = `Admin@LIMS_2026!Sup`,prod = Secret Manager `lims-prod-lims-admin-password`)。

詳細 → docs/03

---

## 指令速查

```bash
# 後端測試
cd backend && pytest --no-header -q       # 期望:285 passed

# 前端測試 + build
cd frontend && npm test -- --run          # 期望:55 passed
cd frontend && npm run build

# 端到端 (需後端跑著)
cd frontend && npm run e2e                # Playwright × 8

# Docker Compose 本機 (fresh DB)
docker compose down -v && docker compose up --build

# 手動 reseed
docker compose exec backend python manage.py seed_demo_orders --force

# 本地 K8s 驗證
make kind-up && make kind-deps && make kind-build && make kind-load && make kind-deploy

# 本地拆掉
make kind-down

# GCP 暫停 / 恢復 / 完全 destroy
make gcp-pause GCP_PROJECT=<id>      # 降到 ~$135/月
make gcp-resume GCP_PROJECT=<id>
make gcp-destroy GCP_PROJECT=<id>    # $0/月
```

---

## 還沒做的事(下一輪 work scope)

- [ ] 跑 docs/02 把 GCP project 開起來(需要 billing account + 工作站 IP)
- [ ] DDNS A record 從家裡 IP 切到 GCLB static IP
- [ ] Argo CD 在 GKE cluster 上 bootstrap(目前只在本地 kind 驗證過)
- [ ] 第一次手動 sync `lims-prod`(prod 沒 autoSync)
- [ ] 等 ManagedCertificate 變 Active(15-60 分鐘)
- [ ] Smoke test https://lims.ddns.net 全部功能 + 觀測性
- [ ] 上線後 admin 密碼立刻換掉(docs/05 §A)
- [ ] (可選)Celery beat schedule 把 `auto_close_stalled_samples` 排成 5 分鐘跑一次

---

## 維護慣例

- **commit 風格** — imperative subject、body 講 "why" 不講 "what"、附 `Co-Authored-By: Claude Opus 4.7`
- **絕不 `git push --force` main**;rollback 用 `git revert`
- **secret 從不入 git**(`.env` 已 gitignore;CI 用 ESO + Secret Manager + Workload Identity)
- **image tag = git short SHA**(12 chars),Artifact Registry 已啟用 immutable tags
- **CD 從不直接 `kubectl apply`**,只 bump tag 然後讓 Argo CD 拉
- **新欄位 / 新表 → migration 必經;`SEED_DEMO_DATA` env-gate 任何 demo data**
- **commit 前跑 `cd backend && pytest`**,285 個測試必須全綠

---

## 對話風格(專案維持的個性)

- 中文回覆 (zh-TW)
- 簡短具體,每個 claim 都對應到實際檔案 (file:line 格式)
- 不堆敬辭 / 不灑滿 emoji / 不長篇 summary
- 多用 TodoWrite 追進度
- 模糊時先問一次,然後標記假設後繼續做
- 不超出需求加功能、不過度抽象
- code 永遠優先,文件其次

---

## 重要決策歷史(避免被推翻)

1. **MySQL 不切 Postgres** — codebase 沒有 vendor-specific 查詢,Cloud SQL for MySQL 完全支援
2. **Helm + ApplicationSet 而不是純 kustomize** — Helm values per-env 對應 Argo generator 最自然
3. **送樣表單從多階段 pipeline 改成單站** — 每個 Order 一個 lab visit,跨 lab 由廠區再送新單
4. **WaferLot 用 code 當 PK 而不是 UUID + code unique**
5. **Demo 觀測性用 Cloud managed 而不是自架** — 省 ~$40/月,demo 演示 UX 等價
6. **Cloud SQL Auth Proxy 跑 sidecar 而不是 Service** — Workload Identity 最乾淨
7. **legacy `Dockerfile` (Caddy + ACME) 跟 `Dockerfile.k8s` (nginx) 並存** — docker-compose 部署不被破壞,GKE 用新版
8. **bitnami chart 不能用** — 公開鏡像下架,改 `scripts/kind-deps.yaml` 用 mysql:8.0 + redis:7-alpine
9. **NetworkPolicy 在 kind 模式關掉** — kindnet 1.31 真的會 enforce,擋了 in-cluster MySQL :3306,只在 prod 開
10. **migrate Job 是 Sync hook 不是 PreSync** — PreSync 跑在所有 sync wave 之前,ConfigMap 還沒建,所以改 Sync + sync-wave -5,搭配 ConfigMap/Secret/SA 的 sync-wave -10
11. **訂單拆成 sub-LOT (`Sample`) 是每個獨立調度的最小單位** — 一張 Order = 一個 25-wafer FOUP,split 後每片獨立挑機台 / Recipe / 操作員,支援 DoE 多條件並行
12. **lab_manager 不可碰 split / dispatch / set_params** — 主管只簽核;`_require_specialty(allow_manager=False)` 直接擋
13. **operator 由 `_auto_pick_assignee` 從 pool 自動指派** — 不再有手動「待指派」步驟,UI tab 已移除;rotation rule 排除上游(created_by/dispatched_by/parameters_set_by)
14. **`EquipmentBooking` overlap 檢查在 `dispatch_sample` 內** — transactional `select_for_update` + 半開區間 `started_at__lt=end AND ended_at__gt=start`
15. **接件 (receive) 在 manager `sign_off_stage` 內自動 stamp** — `lab_member` 不再有「待接件」tab,signal 流程沿用既有 `receive` `StageEvent`
16. **Recipe `parameters` JSONField ≥ 5 knobs** — migration `equipments.0010_enrich_recipe_parameters` 強制保底;`Default-<type>` fallback recipe 補沒有任何 recipe 的 EquipmentType
17. **每張 Order split 總片數 = 25** — `WAFER_COUNT_PER_ORDER = 25` hard equality;測試環境 `settings.LIMS_ENFORCE_WAFER_CAP=False` opt-out
18. **Operator 身份對 requester 遮蔽** — `_MaskOperatorMixin` 在 regular_employee viewer 下把 assignee / dispatched_by / parameters_set_by 等欄位設為 `None`
19. **`/api/equipments/`、`/api/equipments/recipes/` 不分頁** — 前端 client-side filter 需要完整清單;分頁會導致 lab 機台多過 PAGE_SIZE 時 dropdown 漏項(PVD/IMP 曾因此被截掉)
20. **StageEvent.event_type 用 typed enum 而不是 'note'** — `split / dispatch / set_parameters / assign / receive / load / unload / abort / note`,Reports 時間軸才能正確分類
