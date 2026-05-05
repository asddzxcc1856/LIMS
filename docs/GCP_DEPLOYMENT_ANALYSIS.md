# LIMS → GCP 部署分析報告

> 把目前的前端 / 後端 / 資料庫 / 快取 / 監控 / CI 全部對應到 Google Cloud Platform 服務,
> 含推薦架構、成本估算、遷移步驟、風險評估。
>
> 適合:準備上 GCP 的第一份規劃書 / 給 IT/採購主管的 cost case / 給 SRE 的 runbook 起點。

---

## 目錄

- [一、結論先行 (TL;DR)](#一結論先行-tldr)
- [二、現有架構盤點](#二現有架構盤點)
- [三、GCP 服務對應總表](#三gcp-服務對應總表)
- [四、推薦部署架構](#四推薦部署架構)
- [五、各層詳細方案](#五各層詳細方案)
  - [5.1 前端:Cloud Storage + Cloud CDN](#51-前端cloud-storage--cloud-cdn)
  - [5.2 後端:Cloud Run (Django + Gunicorn)](#52-後端cloud-run-django--gunicorn)
  - [5.3 資料庫:Cloud SQL for MySQL](#53-資料庫cloud-sql-for-mysql)
  - [5.4 快取與背景任務:Memorystore + Cloud Run jobs](#54-快取與背景任務memorystore--cloud-run-jobs)
  - [5.5 設定與機密:Secret Manager](#55-設定與機密secret-manager)
  - [5.6 監控與日誌:Cloud Logging / Trace / Monitoring](#56-監控與日誌cloud-logging--trace--monitoring)
  - [5.7 入口:HTTPS Load Balancer](#57-入口https-load-balancer)
- [六、成本估算](#六成本估算)
- [七、Migration 步驟 (從本機 → GCP)](#七migration-步驟-從本機--gcp)
- [八、CI/CD 整合](#八cicd-整合)
- [九、風險、權衡與替代方案](#九風險權衡與替代方案)
- [十、後續優化建議](#十後續優化建議)

---

## 一、結論先行 (TL;DR)

| 項目 | 推薦 GCP 服務 | 月費級距 (低流量) |
|---|---|---|
| 前端 (Vue SPA) | **Cloud Storage** + **Cloud CDN** | < $1 |
| 後端 (Django + DRF) | **Cloud Run** (serverless, scale-to-zero) | $0–$15 |
| 資料庫 | **Cloud SQL for MySQL** (db-f1-micro) | ~$10 |
| 快取 / Celery broker | **Memorystore for Redis** (basic 1 GB) | ~$35 |
| Celery worker | **Cloud Run** (常駐 service) 或 **Cloud Run jobs** | ~$5 |
| Secrets | **Secret Manager** | < $1 |
| 入口流量 | **HTTPS Load Balancer** + GCP-managed cert | ~$18 |
| 日誌 / 追蹤 | **Cloud Logging** + **Cloud Trace** | $0 (free tier 範圍內) |
| **預估月費 (低流量,3 lab × 50 訂單/天)** | | **~$70–$100 USD** |

**架構決策三原則**:

1. **Serverless 優先**:後端用 Cloud Run,scale-to-zero 省成本,流量暴增時自動橫向擴展
2. **Managed services**:Cloud SQL、Memorystore、Secret Manager 都不要自管 VM
3. **Region 統一在 `asia-east1` (彰化)**,避開跨區延遲與費用

**關鍵 trade-off**:Memorystore Redis 一個月 $35 的固定成本,目前的 LIMS 用量並不真的需要 Redis(rate-limit / cache 都還沒用上,Celery broker 暫時也未啟用 critical path)。**短期可先不開 Memorystore**,改用 Cloud SQL 的內建 cache + Django 的 LocMemCache,等 Celery 真的要用時再開。下表估算依「保守完整版」計算。

---

## 二、現有架構盤點

```
┌────────────────────────────────────────────────────────────────────┐
│                          LIMS 現況                                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [Browser]                                                          │
│       │  HTTP                                                       │
│       │                                                             │
│       ▼                                                             │
│  [Vite Dev Server :5173]              ← 開發時                      │
│  [Static dist/ via nginx]             ← production build            │
│       │                                                             │
│       │  /api/* via VITE_API_BASE                                   │
│       ▼                                                             │
│  [Django + DRF :8000]                                               │
│  └─ JWT auth (simplejwt)                                            │
│  └─ ActivityLogMiddleware → 寫 DB                                   │
│  └─ RequestIDMiddleware → X-Request-ID header                       │
│  └─ custom_exception_handler → 統一錯誤 envelope                    │
│       │                                                             │
│       ├──> [SQLite db.sqlite3] (dev) / [MySQL] (configured)         │
│       ├──> [Redis] (configured 但非 critical-path)                   │
│       ├──> [Celery 5.6] (broker 設定好,任務未啟用)                   │
│       └──> [Sentry SDK] (DSN 留空時 inert)                          │
│                                                                     │
│  測試:108 pytest + 39 vitest + 8 playwright = 156 tests             │
│  CI:GitHub Actions (`.github/workflows/ci.yml`)                    │
│  CD:`.github/workflows/cd.yml` 已存在但 `if: false` 等 GCP         │
└────────────────────────────────────────────────────────────────────┘
```

**特性盤點**:

| 維度 | 現況 | 對 GCP 部署的意義 |
|---|---|---|
| 容器化 | `backend/Dockerfile` + `frontend/Dockerfile` 已存在 | Cloud Run 直接吃 |
| Stateless backend | Django 沒寫 server-side session,純 JWT | 完全 cloud-native,可 scale-to-zero |
| 設定外部化 | 所有 secret 都從 env var 讀 | Secret Manager 直接接 |
| Static files | Django `STATIC_URL = 'static/'`,Vue `dist/` 獨立輸出 | Cloud Storage 各自 host |
| Media files | 目前沒檔案上傳功能 | 預留 GCS bucket 規劃 |
| 觀察性 | structured logging stdout + Sentry SDK | Cloud Logging 自動接,Sentry 並行 |
| CI 已驗證綠 | pytest / vitest / playwright 全綠 | 部署管線可信 |

---

## 三、GCP 服務對應總表

| 現有元件 | GCP 服務 | 替代方案 | 為何選這個 |
|---|---|---|---|
| Vue SPA dist/ | **Cloud Storage** + **Cloud CDN** | Firebase Hosting / Cloud Run+nginx | 純 static,CDN 最快;Firebase 也行但 GCP IAM 整合略弱 |
| Django + DRF | **Cloud Run** | GKE / Compute Engine / App Engine Standard | scale-to-zero,容器即部署,費用低 |
| Gunicorn / WSGI | (Cloud Run 內建) | — | Cloud Run 自動處理 HTTP→WSGI |
| MySQL | **Cloud SQL for MySQL** | Cloud SQL for PostgreSQL / Spanner | 對應現有 `DB_ENGINE=mysql` |
| Redis (cache) | **Memorystore for Redis** | Cloud SQL 替代 / Django LocMemCache | Managed,跟 Django CACHES 一致 |
| Celery broker | **Memorystore for Redis** (共用) | Pub/Sub | 直接接既有設定 |
| Celery worker | **Cloud Run** (`--no-cpu-throttling`) 或 Cloud Run jobs | GKE pod | scale-to-zero 不適合常駐;若不可中斷可用 GKE |
| Static files (Django) | **Cloud Storage** | Cloud CDN | `collectstatic` 推上 GCS,Django 設 `STATIC_URL` |
| Media files (未來) | **Cloud Storage** | — | `django-storages[google]` 直接接 |
| `DJANGO_SECRET_KEY` 等 | **Secret Manager** | env var (less secure) | 自動輪替 + IAM 控管 |
| `DJANGO_ALLOWED_HOSTS` | Cloud Run env var | — | 非 secret,直接設 |
| HTTPS / TLS cert | **Google-managed SSL cert** (HTTPS LB) | Let's Encrypt | 自動續期 |
| Domain mapping | **Cloud Domains** + LB | external DNS | 簡化 |
| 結構化 log | **Cloud Logging** | Stackdriver (legacy) | Django `logger.info()` 自動接 |
| 錯誤追蹤 | **Sentry** (continued) + Cloud Error Reporting | — | 雙軌,Sentry 對開發者更友善 |
| Trace 串接 | `X-Request-ID` + **Cloud Trace** | Sentry trace | 已寫好 middleware,GCP auto-correlates |
| Uptime / latency | **Cloud Monitoring** + uptime check | — | 對 `/api/users/profile/` 排程 ping |
| GitHub → GCP auth | **Workload Identity Federation** | service account JSON | 無 long-lived secret,業界 best practice |
| Image Registry | **Artifact Registry** | Container Registry (deprecated) | docker-compose 推這裡 |
| 部署觸發 | GitHub Actions (`.github/workflows/cd.yml`) | Cloud Build | 已有 draft,沿用 |

---

## 四、推薦部署架構

```
                             ┌─────────────────┐
                             │  Cloud Domains  │
                             │  lims.example   │
                             └────────┬────────┘
                                      │
                                      ▼
                        ┌──────────────────────────┐
                        │  HTTPS Load Balancer     │
                        │  (Google-managed cert)   │
                        └────────────┬─────────────┘
                                     │
                  ┌──────────────────┴──────────────────┐
                  │                                      │
              path: /                              path: /api/*
                  │                                      │
                  ▼                                      ▼
       ┌──────────────────────┐             ┌──────────────────────┐
       │   Cloud CDN          │             │   Cloud Run          │
       │   (frontend cache)   │             │   lims-backend       │
       └──────────┬───────────┘             │   ─ Django + Gunicorn│
                  │                          │   ─ scale 0 → N      │
                  ▼                          │   ─ region asia-east1│
       ┌──────────────────────┐             └──────────┬───────────┘
       │   Cloud Storage      │                        │
       │   bucket: lims-spa   │                        │
       │   ─ Vue dist/        │                        │
       └──────────────────────┘                        │
                                                        │
                                ┌───────────────────────┼───────────────────────┐
                                │                       │                       │
                                ▼                       ▼                       ▼
                      ┌──────────────────┐    ┌──────────────────┐   ┌──────────────────┐
                      │  Cloud SQL       │    │  Memorystore     │   │  Secret Manager  │
                      │  MySQL 8         │    │  Redis (basic)   │   │  ─ DJANGO_SECRET │
                      │  db-f1-micro     │    │  1 GB            │   │  ─ DB_PASSWORD   │
                      │  Private IP only │    │  Private IP only │   │  ─ SENTRY_DSN    │
                      └──────────────────┘    └──────────────────┘   └──────────────────┘
                                                        │
                                                        ▼ (optional)
                                              ┌──────────────────┐
                                              │  Cloud Run       │
                                              │  lims-celery     │
                                              │  ─ Celery worker │
                                              │  ─ no CPU throttle│
                                              └──────────────────┘

                            ┌──────────────────────────────────────┐
                            │  Observability (auto)                │
                            │  ─ Cloud Logging  (stdout 自動接)    │
                            │  ─ Cloud Trace    (X-Request-ID 串)  │
                            │  ─ Cloud Monitoring (uptime + p99)   │
                            │  ─ Sentry          (錯誤追蹤,並行)  │
                            └──────────────────────────────────────┘

                            ┌──────────────────────────────────────┐
                            │  CI/CD                                │
                            │  GitHub Actions                       │
                            │  ─ ci.yml: pytest+vitest+playwright   │
                            │  ─ cd.yml: build → Artifact Registry  │
                            │           → deploy Cloud Run          │
                            │  Auth via Workload Identity Federation│
                            └──────────────────────────────────────┘
```

**設計重點**:
- 前後端**同一個域名**,Load Balancer 用 path-based routing 分流(`/` → CDN+GCS,`/api/*` → Cloud Run)。避免 CORS 設定地獄。
- Cloud SQL 與 Memorystore 都用 **Private IP**(VPC peering),Cloud Run 透過 **Serverless VPC Connector** 連入,**從不暴露在公網**。
- Cloud Run 設 **min-instances=0** (scale to zero) + **max-instances=10** (避免 runaway billing)。
- Region 全部 `asia-east1` (彰化),延遲低、合規。

---

## 五、各層詳細方案

### 5.1 前端:Cloud Storage + Cloud CDN

**為何不用 Cloud Run 跑 nginx?**
- 純 static SPA 沒有伺服器邏輯,Cloud Run 起容器是 over-engineering。
- GCS + CDN 邊緣節點命中率 > 95%,p99 延遲 < 50ms。
- 成本最低:1 GB / 月 + 100 GB 流量 < $1。

**設置流程**:
```bash
# 1. 建 bucket
gsutil mb -l asia-east1 -b on gs://lims-spa-prod

# 2. 設為公開讀
gsutil iam ch allUsers:objectViewer gs://lims-spa-prod

# 3. 設網站模式 (404 也回 index.html,SPA 路由用)
gsutil web set -m index.html -e index.html gs://lims-spa-prod

# 4. 上傳 frontend/dist/
cd frontend && npm run build
gsutil -m rsync -r -d dist gs://lims-spa-prod

# 5. 加 CDN (在 Load Balancer backend 設 enableCDN=true)
```

**SPA 路由處理**:GCS 預設 404 不會 redirect 到 `index.html`。Web 設定的 `errorPage=index.html` 解決 `/admin/dashboard` 直接訪問會 404 的問題。或用 Load Balancer 的 URL rewrite。

**HTTP 快取設定**:
- `index.html`:`Cache-Control: no-cache` (always check ETag)
- `assets/*-[hash].js/css`:`Cache-Control: public, max-age=31536000, immutable`(hash 改了就是新檔)

設置:
```bash
gsutil setmeta -h "Cache-Control:no-cache" gs://lims-spa-prod/index.html
gsutil setmeta -h "Cache-Control:public,max-age=31536000,immutable" gs://lims-spa-prod/assets/**
```

---

### 5.2 後端:Cloud Run (Django + Gunicorn)

#### 為何 Cloud Run 不選別的

| 選項 | 優點 | 缺點 | 結論 |
|---|---|---|---|
| **Cloud Run** | scale-to-zero、容器即部署、HTTP/2、free tier 慷慨 | 12 minute request timeout、cold start | ✅ **選此** |
| GKE | 完全可控、k8s 生態 | 維運成本高、最低費用 ~$70/month | 流量大才划算 |
| Compute Engine | 最像本機 | 自管 OS / patching / scaling | 老派,不推薦新案 |
| App Engine Standard | 全託管 | Django 支援差、客制化受限 | 不推薦 |

#### Dockerfile 調整

現有 `backend/Dockerfile` 應確保:
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
EXPOSE 8080
# Cloud Run 期望服務 listen $PORT (預設 8080)
CMD ["gunicorn", "backend.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "8", \
     "--timeout", "60", \
     "--access-logfile", "-"]
```

#### Cloud Run 部署指令

```bash
gcloud run deploy lims-backend \
  --image asia-east1-docker.pkg.dev/$PROJECT/lims/lims-backend:$SHA \
  --region asia-east1 \
  --platform managed \
  --no-allow-unauthenticated \                    # only LB can invoke
  --port 8080 \
  --cpu 1 --memory 512Mi \
  --min-instances 0 --max-instances 10 \
  --concurrency 80 \                              # 80 req per container
  --vpc-connector lims-vpc-connector \            # 連 Cloud SQL / Redis
  --vpc-egress private-ranges-only \
  --set-env-vars DJANGO_PRODUCTION=True,DJANGO_DEBUG=False \
  --set-env-vars DJANGO_ALLOWED_HOSTS=lims.example.com,DB_ENGINE=mysql \
  --set-env-vars DB_HOST=10.0.0.3,DB_NAME=lims,DB_USER=django,DB_PORT=3306 \
  --set-env-vars REDIS_URL=redis://10.0.0.5:6379/0 \
  --set-env-vars CORS_ALLOWED_ORIGINS=https://lims.example.com \
  --set-secrets DJANGO_SECRET_KEY=django-secret-key:latest \
  --set-secrets DB_PASSWORD=lims-db-password:latest \
  --set-secrets LIMS_ADMIN_PASSWORD=lims-admin-password:latest \
  --set-secrets SENTRY_DSN=sentry-dsn:latest
```

#### Migrations 怎麼跑

Cloud Run 不適合在每次冷啟動跑 `migrate`。三個選擇:

| 方案 | 適用 |
|---|---|
| **Cloud Run jobs** + 部署前 hook | ✅ 推薦,clear separation |
| 啟動時 `python manage.py migrate` | 簡單但每次冷啟動慢 |
| GitHub Action 內手動跑 | 風險:容易忘 |

推薦 cd.yml 加一步:
```yaml
- name: Run migrations
  run: |
    gcloud run jobs deploy lims-migrate \
      --image $IMAGE --region asia-east1 \
      --command python --args manage.py,migrate \
      ...
    gcloud run jobs execute lims-migrate --wait
```

---

### 5.3 資料庫:Cloud SQL for MySQL

#### 為何 MySQL 而非 PostgreSQL

對現有 codebase 而言:
- `settings.py` 已支援 `DB_ENGINE=mysql`,**0 行程式碼修改**
- 對 Django 來說兩者都是 first-class citizen
- 若願意花時間改造,PostgreSQL 對 Django 親和度更好(JSON / array / partial index 支援更佳)
- **第一階段保持 MySQL,後續視業務需求再評估遷移**

#### Instance 規格建議

| 環境 | 規格 | 月費 |
|---|---|---|
| Production (低流量) | `db-f1-micro`, 1 vCPU, 614 MB | ~$10 |
| Production (中流量) | `db-custom-2-7680`, 2 vCPU, 7.5 GB | ~$60 |
| Staging | `db-f1-micro` | ~$10 |

選 `db-f1-micro` 起步:LIMS 一天訂單量低於千筆時 CPU < 5%。

#### 關鍵設定

```bash
gcloud sql instances create lims-db-prod \
  --database-version=MYSQL_8_0 \
  --region=asia-east1 \
  --tier=db-f1-micro \
  --availability-type=ZONAL \                      # ZONAL=便宜,REGIONAL=高可用
  --network=projects/$PROJECT/global/networks/default \
  --no-assign-ip \                                 # 只開 Private IP
  --backup-start-time=18:00 \
  --enable-bin-log \                               # PITR 必要
  --retained-backups-count=7 \
  --retained-transaction-log-days=7
```

**Private IP only** 是安全要求 — 不可直接從公網連 DB。Cloud Run 透過 Serverless VPC Connector 連入。

#### 連線 string

`backend/backend/settings.py` 已有完整支援,環境變數設好即可:
```
DB_ENGINE=mysql
DB_HOST=10.0.0.3                                   # private IP
DB_NAME=lims
DB_USER=django
DB_PASSWORD=<from Secret Manager>
DB_PORT=3306
```

#### 備份策略

- **每日自動備份** 18:00 (台北時間),保留 7 天
- **Binary logs PITR** 7 天回溯(任意時間點)
- **每月手動匯出** 到 GCS bucket(成本: < $1/year),保留 3 年作為合規佐證

---

### 5.4 快取與背景任務:Memorystore + Cloud Run jobs

#### 是否需要 Memorystore?

**目前實際依賴**:
- `CACHES['default']` 配置成 Redis,但 Django 程式碼**沒寫 `cache.set()`/`cache.get()`**
- `CELERY_BROKER_URL` 配置成 Redis,但**沒有 critical-path 任務**(Celery 5.6 已裝但沒任務在跑)

**結論**:**短期可不開 Memorystore**,等實際要用 Celery / Cache 時再開。

**若要開**:
```bash
gcloud redis instances create lims-redis \
  --region=asia-east1 \
  --tier=basic \                                   # basic=便宜,standard=高可用
  --size=1                                          # 1 GB
```

`basic 1 GB ≈ $35/month`。

#### Celery worker 怎麼跑

Cloud Run **不適合常駐長任務**(80 req concurrency model 會 starve worker)。三個選擇:

| 方案 | 適用 |
|---|---|
| **Cloud Run service** with `--no-cpu-throttling`,健康檢查 disabled | 適合短任務 + Pub/Sub trigger |
| **Cloud Run jobs** | 一次性任務(每天清舊 log、產報表) |
| **GKE Autopilot** | 真的要 24/7 worker pool |

LIMS 目前的 Celery 用例不存在 — 當業務上要寄 Email、產 PDF 報表、定時同步 FAB MES 時,首選 **Cloud Run jobs** + Cloud Scheduler 觸發。

---

### 5.5 設定與機密:Secret Manager

#### 哪些放 Secret Manager,哪些放 env var

| 變數 | 何處 | 原因 |
|---|---|---|
| `DJANGO_SECRET_KEY` | **Secret** | session/JWT 簽名,洩漏即災難 |
| `DB_PASSWORD` | **Secret** | DB 密碼 |
| `LIMS_ADMIN_PASSWORD` | **Secret** | 預設 admin 密碼 |
| `SENTRY_DSN` | **Secret** (含 token) | 可發送錯誤 |
| `DJANGO_ALLOWED_HOSTS` | env var | 公開資訊 |
| `CORS_ALLOWED_ORIGINS` | env var | 公開資訊 |
| `DB_HOST` / `DB_USER` / `DB_NAME` | env var | 非機密(內部 IP / username 不算 secret) |
| `REDIS_URL` | env var (host) | host 是 private IP |
| `DJANGO_PRODUCTION` | env var | flag |

#### 自動輪替 (rotation)

Secret Manager 支援設定 rotation period:
```bash
gcloud secrets create lims-db-password \
  --replication-policy=automatic \
  --rotation-period=90d \
  --next-rotation-time=2026-08-01T00:00:00Z
```

90 天輪替 DB 密碼。需要寫 Cloud Function 接受 rotation event 並更新 Cloud SQL 的密碼,**初期可不開**。

---

### 5.6 監控與日誌:Cloud Logging / Trace / Monitoring

#### Logging — 自動接

Cloud Run 把容器 stdout/stderr 自動進 Cloud Logging。Django 已設定 `LOGGING` 寫 stdout,**完全不需改程式**。

查 log:
```bash
gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=lims-backend' --limit 50
```

或在 Cloud Console:Logs Explorer → 過濾 service。

#### 結構化 log

Django 用 stdlib `logging`。Cloud Run 自動把 stdout 視為 unstructured 字串。要結構化 log(例如過濾 status=500 的請求),建議:

```python
# settings.py
LOGGING['formatters']['gcp_json'] = {
    'format': json.dumps({
        'severity': '{levelname}',
        'message': '{message}',
        'request_id': '%(request_id)s',
    }),
    'style': '{',
}
```

**進階**:用 `google-cloud-logging` SDK 直接 emit structured logs(`{"severity": "ERROR", "trace": "..."}`),Cloud Logging 自動串 Cloud Trace。

#### Trace — request_id 自動串

階段 4 已寫好的 `RequestIDMiddleware`、`X-Request-ID` header、`ActivityLog.request_id` 欄位,跟 GCP 完全相容:
- Cloud Run 收到 `X-Cloud-Trace-Context` header,自動產生 trace
- 自製 `X-Request-ID` 跟 GCP `trace` 並存,兩個都進 ActivityLog,**可從 Sentry/log 任一面向 stitch**

#### Monitoring — uptime check

```bash
gcloud monitoring uptime create-http \
  --resource-labels=host=lims.example.com \
  --path=/api/users/profile/ \                     # 401 也算 alive
  --period=60 \
  --timeout=10
```

p99 latency / error rate alert:在 Cloud Console → Monitoring → Alerting 建 policy。

#### Sentry

仍推薦並行 Sentry,因為:
- Sentry 對開發者 UX 比 Cloud Error Reporting 好(stack trace, breadcrumbs, user context)
- 開源 / 多雲友善(將來換 cloud 不用改 codebase)
- 階段 1 已預留:設 `SENTRY_DSN` env var 就啟用

---

### 5.7 入口:HTTPS Load Balancer

#### 為何用 LB 而非直接綁 Cloud Run domain

- **同一域名前後端**:`https://lims.example.com/` (前端) + `https://lims.example.com/api/...` (後端)
- **CDN 整合**:LB 才能掛 Cloud CDN
- **WAF / Cloud Armor**:LB 可掛防 DDoS / OWASP rules
- **HTTP/3 (QUIC)**:LB 自動支援

#### Path-based routing

```
forwarding rule (anycast IP)
  └─ URL map "lims-router"
      ├─ default backend: lims-spa-cdn (GCS bucket + CDN)
      └─ path matcher
          ├─ /api/* → backend service "lims-backend" (Cloud Run NEG)
          └─ /admin/django/* → backend service "lims-backend" (Django admin)
```

Frontend 的 SPA 路由 (`/admin/dashboard`、`/orders/create` 等)走 default → SPA → Vue Router 處理。

#### TLS

Google-managed cert 自動續期:
```bash
gcloud compute ssl-certificates create lims-cert \
  --domains=lims.example.com,api.lims.example.com \
  --global
```

附在 LB 的 target HTTPS proxy 上。**0 維運**。

---

## 六、成本估算

### 月費試算 (低流量,3 個實驗室,每天 ~50 訂單,~10 個活躍使用者)

| 項目 | 規格 | 估算 (USD/月) |
|---|---|---|
| Cloud Run lims-backend | 0–5 instance, ~50K req/month | **$0** (free tier 內) |
| Cloud Run lims-celery (若啟用) | 1 常駐 instance | ~$5 |
| Cloud SQL MySQL | db-f1-micro, 10 GB SSD | **~$10** |
| Memorystore Redis (若啟用) | basic 1 GB | ~$35 |
| Cloud Storage | 1 GB SPA + 5 GB media | < $1 |
| Cloud CDN | 100 GB egress | ~$8 |
| HTTPS Load Balancer | 1 forwarding rule + 5 GB processed | ~$18 |
| Secret Manager | 5 secrets × < 100 access/day | < $1 |
| Cloud Logging | < 50 GB/month | $0 (free tier 內) |
| Cloud Monitoring | uptime checks | $0 (free tier 內) |
| Artifact Registry | 5 GB image storage | < $1 |
| **Sum (no Redis/Celery)** | | **~$38** |
| **Sum (with Redis + Celery)** | | **~$78** |

### 中流量 (50 lab × 100 order/day)

| 項目 | 規格 | 估算 |
|---|---|---|
| Cloud Run lims-backend | 0–20 instance, ~5M req/month | ~$30 |
| Cloud SQL MySQL | db-custom-2-7680 + REGIONAL HA | ~$120 |
| Memorystore Redis | standard 4 GB | ~$220 |
| 其他 | (同上 scale up) | ~$50 |
| **Sum** | | **~$420** |

### 高流量 (200+ lab,即時 dashboard)

需要重新評估架構:
- Cloud SQL → 升 PostgreSQL with read replicas / 或評估 AlloyDB
- Cloud Run → GKE Autopilot 或 Cloud Run with 高 max-instances
- Memorystore → standard tier with replicas
- 預估 $1500–3000/月

---

## 七、Migration 步驟 (從本機 → GCP)

### Phase 0:準備 (1–2 天)

- [ ] 建 GCP project,啟用必要 API:
  ```bash
  gcloud services enable run.googleapis.com sqladmin.googleapis.com \
                          redis.googleapis.com secretmanager.googleapis.com \
                          artifactregistry.googleapis.com vpcaccess.googleapis.com \
                          servicenetworking.googleapis.com
  ```
- [ ] 設 billing alert($100 / $500 兩階)
- [ ] 設 IAM:建 GitHub Actions 用的 OIDC service account,bind 必要 roles
- [ ] 註冊網域(若還沒)

### Phase 1:基礎設施 (半天)

- [ ] 建 VPC + subnet + Serverless VPC Connector
- [ ] 建 Cloud SQL instance (Private IP)
- [ ] 建 Artifact Registry repo: `lims`
- [ ] 建 Secret Manager 4 個 secret
- [ ] 建 GCS bucket: `lims-spa-prod`(設 web mode)

### Phase 2:首次部署 (半天)

- [ ] 推 `lims-backend` image 到 Artifact Registry
- [ ] 部署 Cloud Run service (no traffic)
- [ ] 跑 Cloud Run job: `manage.py migrate`(會觸發 admin auto-create migration)
- [ ] 把 frontend `dist/` 推上 GCS
- [ ] 建 HTTPS LB,接 Cloud Run + GCS,綁 cert

### Phase 3:DNS 切換 (15 分鐘)

- [ ] 更新 DNS A record 指向 LB 的 anycast IP
- [ ] 驗證 `https://lims.example.com/` (前端) + `https://lims.example.com/api/users/profile/` (後端 API)
- [ ] 用 admin / `Admin@LIMS_2026!Sup` 登入測試

### Phase 4:CI/CD 啟用 (半天)

- [ ] 在 `.github/workflows/cd.yml` 移除 `if: false` guard
- [ ] 移除 `workflow_dispatch` 限制,改 `push: branches: [main]`
- [ ] 設定 4 個 GitHub repo secrets:`GCP_WORKLOAD_IDENTITY_PROVIDER` / `GCP_SERVICE_ACCOUNT` / `GCP_PROJECT_ID` / `DJANGO_SECRET_KEY` / `LIMS_ADMIN_PASSWORD`
- [ ] 觸發一次 manual run,驗證 build → deploy 流程
- [ ] 確認 traffic 自動切到新 revision

### Phase 5:監控告警 (1–2 天)

- [ ] Sentry DSN 寫入 Secret Manager
- [ ] Cloud Monitoring uptime check 建好
- [ ] Cloud Logging 過濾規則:status >= 500 / unhandled exception
- [ ] Slack / email alerting 設定

### Phase 6:資料遷移 (依現況調整)

- [ ] 從 SQLite (本機) export `python manage.py dumpdata > prod_data.json`
- [ ] Cloud Run job 跑 `loaddata prod_data.json`(若是真實資料)
- [ ] 或用 Cloud SQL Auth Proxy 直接從本機把 MySQL dump push 上去

---

## 八、CI/CD 整合

### 既有 ci.yml — 不需改

`.github/workflows/ci.yml` 100% 雲端無關,push/PR to main 自動跑:
- backend pytest (108)
- frontend vitest (39) + build
- Playwright e2e (8)

### cd.yml — 5 處要改

階段 9 寫好的 draft 已經完整,只要:

1. **trigger 改 push**:
   ```yaml
   on:
     push:
       branches: [main]
     workflow_dispatch:
   ```
2. **移除兩個 jobs 上的 `if: ${{ false }}`**
3. **GitHub repo secrets** 填好(第 4 步建好的 OIDC + project ID)
4. **加 migration job** 在 deploy 前:
   ```yaml
   - name: Run DB migrations
     run: |
       gcloud run jobs deploy lims-migrate \
         --image="${IMAGE}:${{ github.sha }}" \
         --region=asia-east1 \
         --command="python" \
         --args="manage.py,migrate,--noinput"
       gcloud run jobs execute lims-migrate --region=asia-east1 --wait
   ```
5. **加 traffic split** 漸進部署(可選):
   ```yaml
   - run: gcloud run services update-traffic lims-backend --to-revisions LATEST=10
   # ... wait, monitor ...
   - run: gcloud run services update-traffic lims-backend --to-revisions LATEST=100
   ```

---

## 九、風險、權衡與替代方案

### 主要風險

| 風險 | 衝擊 | 緩解 |
|---|---|---|
| **Cold start 延遲** | 第一個 request 多 1–3 秒 | min-instances=1 (花 ~$15/月買常駐) |
| **Cloud Run 12 分鐘 timeout** | 長任務會被砍 | 移到 Cloud Run jobs |
| **Cloud SQL Private IP 連不到本機** | 開發者沒法直連 | Cloud SQL Auth Proxy |
| **Memorystore 沒有 free tier** | 每月固定 $35 | 短期不開,改 Django LocMemCache |
| **Cloud Run cost runaway** | DDoS 暴增 → 帳單爆 | max-instances=10 + Cloud Armor rate limit |
| **單一 region (asia-east1) 故障** | 全停 | DR plan: cross-region replica + DNS failover (進階) |
| **Egress fee** | 流量費用累積 | CDN 命中率優化 + 大檔上傳走 GCS direct upload |

### 替代雲端方案比較

| 雲 | 等價組合 | 為何 GCP |
|---|---|---|
| **AWS** | S3+CloudFront / ECS+Fargate / RDS / ElastiCache | 都可以,但 GCP Cloud Run scale-to-zero 比 ECS 強 |
| **Azure** | Static Web Apps / Container Apps / Azure SQL / Azure Cache | 也行,微軟 stack 的選擇 |
| **Vercel + Railway** | 前端 Vercel,後端 Railway | 最快上線,但成本對中型 + 合規不友善 |

選 GCP 主要原因:
1. Cloud Run 的 scale-to-zero 對小型 LIMS 成本最低
2. 半導體 FAB 客戶常已有 GCP 簽約
3. CD draft 已經是 GCP 寫好

### 不採用 GKE 的理由

- 維運門檻高(需要 SRE)
- 最低費用 ~$70/月(control plane fee + node pool 起跳)
- LIMS 流量規模用 Cloud Run 已綽綽有餘

### 升 PostgreSQL 的成本

對 codebase 而言:
- 改 1 行 settings.py
- requirements.txt 加 `psycopg2-binary`
- migrations 要重新生成或 dump → load
- 既有測試基本不需改(testing 用 SQLite)

成本:約 1 個工程師日。**第一階段不做**,等業務發展再評估。

---

## 十、後續優化建議

### 短期 (上線後 1–3 個月)

- [ ] 加 Cloud Armor 防 OWASP top 10 + rate limit
- [ ] Cloud Monitoring SLO + error budget
- [ ] Sentry 接到 Slack
- [ ] Cloud SQL slow query log → BigQuery 分析

### 中期 (3–6 個月)

- [ ] Frontend bundle 拆 chunks (目前 1.7 MB single chunk,gzip 后 535 KB)
- [ ] 後端加 cache layer(熱端點如 dashboard stats)
- [ ] Celery 真的啟用後,評估 Pub/Sub 替代 Redis broker
- [ ] BigQuery sink ActivityLog,長期審計分析

### 長期 (6 個月+)

- [ ] 升 PostgreSQL + read replicas
- [ ] 多 region 部署 (asia-east1 + asia-east2 active-passive)
- [ ] AlloyDB 評估(若 PostgreSQL 流量大)
- [ ] 自動化 DR drill(每季演練 region failover)

---

## 附錄:跨參考

| 主題 | 參考 |
|---|---|
| 既有 CI/CD draft | [`.github/workflows/cd.yml`](../.github/workflows/cd.yml) |
| 環境變數總表 | [`backend/README.md` § Configuration](../backend/README.md#configuration--environment) |
| 完整開發紀錄 | [`docs/DEVELOPMENT_LOG.md`](DEVELOPMENT_LOG.md) |
| Django settings 實作 | [`backend/backend/settings.py`](../backend/backend/settings.py) |
| 既有 Dockerfile | [`backend/Dockerfile`](../backend/Dockerfile), [`frontend/Dockerfile`](../frontend/Dockerfile) |

---

*本報告針對 LIMS 現況撰寫,實際成本、規格依 GCP 即時定價與工作負載微調。*
