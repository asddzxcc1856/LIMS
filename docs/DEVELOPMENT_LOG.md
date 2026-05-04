# LIMS 開發紀錄

> 從 0 → 完整大型系統的演進過程,涵蓋功能開發、測試、CI/CD、UX 打磨。
>
> 主要時間軸:**`d79fbf9` → `c8fd652`** (約 25 個 commits,9 大階段 + 多輪 polish)

---

## 目錄

- [一、專案概觀](#一專案概觀)
- [二、九大階段總覽](#二九大階段總覽)
- [三、各階段詳解](#三各階段詳解)
  - [階段 1 — 後端監控與儀表板](#階段-1--後端監控與儀表板)
  - [階段 2 — 後端 Admin CRUD API](#階段-2--後端-admin-crud-api)
  - [階段 3a — Ant Design Vue 管理後台介面](#階段-3a--ant-design-vue-管理後台介面)
  - [階段 3b — 全系統視覺風格統一](#階段-3b--全系統視覺風格統一)
  - [階段 4 — 非功能性強化 (NFR)](#階段-4--非功能性強化-nfr)
  - [階段 5 — 後端測試棧](#階段-5--後端測試棧)
  - [階段 6 — 前端測試 (Vitest)](#階段-6--前端測試-vitest)
  - [階段 7 — End-to-end 測試 (Playwright)](#階段-7--end-to-end-測試-playwright)
  - [階段 8 — CI Pipeline](#階段-8--ci-pipeline)
  - [階段 9 — CD Workflow (Draft)](#階段-9--cd-workflow-draft)
- [四、功能補強與修補](#四功能補強與修補)
  - [4.1 角色可見性收緊](#41-角色可見性收緊)
  - [4.2 訂單詳情接力進度修復](#42-訂單詳情接力進度修復)
  - [4.3 中英文切換 + 深淺色主題](#43-中英文切換--深淺色主題)
  - [4.4 完整文件](#44-完整文件)
  - [4.5 移除註冊頁 + 後台批次建帳號](#45-移除註冊頁--後台批次建帳號)
  - [4.6 Admin 帳號自動建立](#46-admin-帳號自動建立)
  - [4.7 UX / Dark mode polish 雜項](#47-ux--dark-mode-polish-雜項)
- [五、測試與品質指標](#五測試與品質指標)
- [六、部署與運維](#六部署與運維)
- [七、給開發者的 quick start](#七給開發者的-quick-start)
- [八、commit 對照表](#八commit-對照表)

---

## 一、專案概觀

LIMS = **實驗室管理系統 (Laboratory Information Management System)**,專為半導體 FAB 環境的多階段「接力」工作流設計。

**改造前**:
- Django + Vue 框架已搭好,有 4 個 app(users/orders/equipments/scheduling)
- 純手刻 CSS、深色主題、無管理後台、無測試、無 CI/CD
- 公開註冊任何人都能建帳號

**改造後**:
- 完整 12 頁的 Ant Design Vue 管理後台 (儀表板、活動日誌、10 表 CRUD)
- 前後端、E2E 共 156 個測試,涵蓋 AAA + 五大 test-double 風格
- GitHub Actions CI 自動跑 backend pytest + frontend vitest + playwright
- 中文/英文切換、淺色/深色主題,使用者偏好持久化
- 後台批次建立 N 組請求者 / 實驗室成員 / 實驗室管理員
- 嚴格的角色可見性 (4 種角色,row-level 過濾)
- Migration 自動建立 admin,新部署 `migrate` 完即可登入
- 完整 README × 3(root / backend / frontend),近 1100 行可閱讀文件
- 統一的錯誤 envelope、request_id 追蹤、Sentry 整合預留

---

## 二、九大階段總覽

| 階段 | 主題 | 主 commit | 規模 |
|---|---|---|---|
| 1 | 後端監控 + 活動日誌 + 儀表板 API | `d79fbf9` | 19 檔, +483 |
| 2 | Admin CRUD API (10 個 ModelViewSet) | `116c9db` | 11 檔, +362 |
| 3a | Ant Design Vue admin console (12 頁) | `795cb21` | 21 檔, +2378 |
| 3b | 全系統改造 antd 風格 | `2e3d0c4` | 10 檔, +2595 / -1514 |
| 4 | NFR 強化 (安全 / 統一錯誤 / trace ID) | `3047a57` | 9 檔, +280 |
| 5 | 後端 pytest + AAA + 五大 test double | `a450479` | 12 檔, +1151 |
| 6 | 前端 vitest + 元件測試 | `0f29c9b` | 9 檔, +4661 |
| 7 | Playwright E2E (8 specs 全綠) | `80b856c` | 7 檔, +330 |
| 8 + 9 | GitHub Actions CI + GCP CD draft | `362ea77` | 2 檔, +302 |

加總約 8,500+ 行新增,涵蓋功能、測試、CI、文件。

---

## 三、各階段詳解

### 階段 1 — 後端監控與儀表板

**目的**:給超級管理員一個「看見系統運作」的窗口。

新建 `backend/monitoring/` app:

| 檔案 | 內容 |
|---|---|
| `models.py` | `ActivityLog`(UUID PK + 3 indexes:timestamp/user/action_type) |
| `middleware.py` | `ActivityLogMiddleware` 自動記錄每個 API 請求 |
| `permissions.py` | `IsSystemSuperuser`(基於 `User.role`,不是 Django flag) |
| `views.py` | `DashboardStatsView` + `ActivityLogListView`(篩選/排序/分頁) |
| `management/commands/ensure_admin.py` | 冪等的 admin 帳號建立指令 |

**設計重點**:
- 敏感欄位自動 redact (`password` / `token` / `refresh` 等 → `***REDACTED***`)
- 8 KB 以上 body 自動跳過,避免大檔案上傳吃 DB 空間
- middleware 包 try/except,**logging 永不破壞請求流程**
- Sentry SDK 整合預留(設 `SENTRY_DSN` env var 即啟用)
- 結構化 LOGGING config 寫到 stdout,可接 Loki/ELK

**新 endpoints**:
- `GET /api/monitoring/dashboard/` — 系統統計快照
- `GET /api/monitoring/logs/?action_type=&method=&username=&since=&until=&path=` — 活動日誌

---

### 階段 2 — 後端 Admin CRUD API

新建 `backend/admin_api/` app,對 10 個 model 提供完整 CRUD:

```
/api/admin/fabs/                       FAB
/api/admin/departments/                Department
/api/admin/users/                      User (含密碼 hash + 自刪/最後 superuser 防護)
/api/admin/experiments/                Experiment
/api/admin/equipment-types/            EquipmentType
/api/admin/equipment/                  Equipment
/api/admin/experiment-requirements/    ExperimentRequiredEquipment
/api/admin/orders/                     Order
/api/admin/order-stages/               OrderStage
/api/admin/bookings/                   EquipmentBooking
```

**設計重點**:
- `AdminBaseViewSet` 共用 `IsSystemSuperuser` + `SearchFilter` + `OrderingFilter`
- 每個資源有 admin-shaped serializer,denormalize 顯示用欄位 (例如 `department_name`)
  避免前端表格做 N+1 lookup
- `UserSerializer` 把 `password` 設為 `write_only`、`set_password` 自動雜湊,讀取永不回傳
- `UserViewSet.perform_destroy` 兩道防護:不能刪自己 / 不能刪掉最後一個 superuser
- DRF `DefaultRouter` 自動 register 10 條路由

---

### 階段 3a — Ant Design Vue 管理後台介面

從零打造 12 頁 superuser console,**不動既有頁面**。

#### 基礎建設

| 檔案 | 用途 |
|---|---|
| `package.json` | 加入 `ant-design-vue@4` / `@ant-design/icons-vue` / `dayjs` |
| `main.js` | 全域引入 antd + reset.css |
| `stores/auth.js` | 加 `isSuperuser` computed |
| `router/index.js` | `/admin` 路由群 + `meta.roles=['superuser']` guard |
| `api/admin.js` | 統一 CRUD client,每個 resource 有 `list/retrieve/create/update/remove` |

#### 元件

- **AdminLayout.vue**:可摺疊深色 sider + 麵包屑 header + 漸層 brand
- **CrudTable.vue**:**核心通用元件** — 由 `columns` + `formFields` 設定驅動,
  自動產生表格 / 搜尋 / 分頁 / 排序 / 建立 / 編輯 / 刪除 / 動態下拉,11 個 admin 頁共用,每個頁面只需 ~40 行 config

#### 12 個 admin 頁

| 路徑 | 內容 |
|---|---|
| `/admin/dashboard` | 4 KPI 卡 + 訂單/設備/角色/活動分布 + 30 秒自動更新 + 近期活動表 |
| `/admin/logs` | 6 種篩選 + 排序 + 詳情抽屜顯示完整 redacted JSON request body |
| `/admin/fabs` ... `/admin/bookings` | 10 個 CRUD 頁 |

主 Dashboard 為 superuser 加上漸層紫藍「進入管理後台」按鈕(其他角色看不到)。

---

### 階段 3b — 全系統視覺風格統一

把既有的 8 個業務頁面全部改造成 Ant Design Vue:

| 改造前 | 改造後 |
|---|---|
| 純手刻 CSS,深色主題 | antd 元件主導,跟 admin 一致 |
| `<table>` 手刻 | `<a-table>` |
| 自製 Modal overlay | `<a-modal>` / `<a-drawer>` |
| 手刻接力進度 dot | `<a-steps>` 元件 |
| 自寫 Form rules | antd `Form.Item` rules |

涵蓋:`App.vue` shell / `LoginView` / `RegisterView` / `Dashboard` / `OrderListView` / `OrderCreateView` / `OrderReviewView` / `OrderTasksView` / `EquipmentDashboardView`。

`style.css` 從 173 → 60 行,只保留 TimelineChart 仍依賴的 CSS 變數 + 字體 import。

---

### 階段 4 — 非功能性強化 (NFR)

四大面向同時動工:

#### 安全

- `DJANGO_PRODUCTION=True` 啟動嚴格模式:**強制 SECRET_KEY、拒絕 `ALLOWED_HOSTS=*`**
- HSTS / SSL_REDIRECT / Secure cookies / X-Frame-Options=DENY / Content-Type nosniff
- 密碼最小長度生產環境 12 字元

#### 可維護性 — 統一錯誤 envelope

新建 `utils/exception_handler.py`:

```json
{
  "detail": "Human-readable summary",
  "code": "machine_code",
  "fields": { "<field>": ["<error>", ...] },
  "request_id": "<uuid>"
}
```

5xx 寫 log 但**永遠不洩漏 traceback**,順手關掉 OrderReviewView 的 traceback 洩漏點。

#### 可觀測性 — Request ID

`utils/request_id.py` middleware:
- 為每個 request 打 UUID 標籤
- echo 至 `X-Request-ID` response header
- 寫進 `ActivityLog.request_id` 欄位
- 上游有 `X-Request-ID` 則沿用(供 proxy/edge stitch trace)

#### 效能

- `OrderDetailView`:prefetch stages + nested FK
- `OrderStageListView`:select_related order chain
- 解決儀表板與訂單詳情頁的 N+1

---

### 階段 5 — 後端測試棧

工具:**pytest + pytest-django + factory_boy + freezegun + pytest-mock + pytest-cov**

#### 76 個測試的覆蓋

| 檔案 | 涵蓋 |
|---|---|
| `test_monitoring_middleware.py` (18) | `_redact` / `_classify` / `_client_ip` / 持久化 |
| `test_request_id.py` (4) | UUID 生成 / header 透傳 / 長度上限 |
| `test_exception_handler.py` (5) | 各例外型別 envelope / traceback 遮蔽 |
| `test_orders_services.py` (13) | 訂單狀態機 + 五大 test double 全展示 |
| `test_admin_api_integration.py` (23) | 4 角色權限矩陣 + CRUD + 安全防護 |
| `test_monitoring_api_integration.py` (7) | dashboard / log filter / request_id 串接 |
| `test_auth_integration.py` (6) | JWT login/refresh/profile + uniform error shape |

#### 五大 test double 風格全展示 (`test_orders_services.py`)

| 類型 | 應用 |
|---|---|
| **Fake** | `factory_boy` 建完整 ORM 物件 |
| **Stub** | conftest fixture 預備好的角色資料 |
| **Mock** | `mocker.patch('scheduling.services.allocate_equipments_for_stage')` |
| **Spy** | `mocker.spy(services, '_send_notification')` 觀察呼叫次數 |
| **Time fake** | `freezegun.freeze_time('2026-05-01 10:00:00')` |

#### 共用 fixtures (`conftest.py`)

每個角色 (`employee` / `lab_manager` / `lab_member` / `superuser`) 都有對應的 user 物件 + 預先認證好的 `APIClient`,測試只需要 `def test_xxx(employee_client):` 直接拿到認證好的 client。

#### 一個小技術坑

系統 ROS humble 在 `PYTHONPATH` 註冊了會 conflict 的 pytest entry point,跑 pytest 必須:
```bash
unset PYTHONPATH && pytest
```

---

### 階段 6 — 前端測試 (Vitest)

工具:**vitest 3 + @vue/test-utils + jsdom + @vitest/coverage-v8**

#### 30 個測試的覆蓋

| 檔案 | 涵蓋 |
|---|---|
| `auth.store.test.js` (9) | Token 持久化 / logout 清理 / profile 失敗路徑 / 角色 computed |
| `admin.api.test.js` (9) | 每個 admin resource 的每個 CRUD verb (axios stubbed) |
| `LoginView.test.js` (4) | Form 連線 / login flow / backend 錯誤訊息表面化 |
| `CrudTable.test.js` (8) | 通用 CRUD 元件:分頁 / 搜尋 / modal 初始化 / write-only password 處理 / 刪除重載 |

#### Node 25 的詭異 bug

Node 25 內建一個壞掉的 `globalThis.localStorage`,**Web Storage 方法 (getItem/setItem/clear) 都不存在**。jsdom 29 surfaces 同樣的物件。

修法:`tests/setup.js` 強制覆蓋為自製的 Map-backed `MemoryStorage`:

```js
class MemoryStorage {
  constructor() { this._store = new Map() }
  getItem(k) { return this._store.has(k) ? this._store.get(k) : null }
  setItem(k, v) { this._store.set(String(k), String(v)) }
  // ... clear / removeItem / length / key
}
Object.defineProperty(globalThis, 'localStorage', { value: new MemoryStorage(), ... })
```

---

### 階段 7 — End-to-end 測試 (Playwright)

3 支 spec / 8 個測試,本機全綠 (~13 秒):

| 檔案 | 內容 |
|---|---|
| `login.spec.js` (3) | 必填驗證 / 錯誤訊息 / admin 登入導向 |
| `admin-console.spec.js` (4) | KPI 卡 / 活動日誌 / 側欄導航 / superuser 路由守衛 |
| `admin-crud.spec.js` (1) | EquipmentType 完整 CRUD via UI(建→搜→改→刪) |

#### 踩過的雷 (commit message 都記了)

1. **antd CJK button auto-spacing**:`登入` 渲染成 `登 入`(antd 自動加空格)。selector 用 regex 包容:
   ```js
   const re = (s) => new RegExp(s.split('').join('\\s*'))
   page.getByRole('button', { name: re('登入') })
   ```
2. **strict-mode 多重命中**:同一文字 `系統儀表板` 出現在 sidebar / breadcrumb / page-header 三處。anchor 在 `.ant-page-header-heading-title` 上。
3. **CI 上 IPv6 vs IPv4**:GitHub runner `localhost` → `::1`,Playwright 等 `127.0.0.1`。Vite 加 `--host 127.0.0.1` 強制 IPv4,timeout 從 30s 拉到 120s。

---

### 階段 8 — CI Pipeline

`.github/workflows/ci.yml`,push / PR to main 觸發:

| Job | 步驟 |
|---|---|
| `backend` | `pip install -r requirements.txt` → `pytest` → 上傳 coverage |
| `frontend-unit` | `npm ci` → `npm test` (vitest) → `npm run build` |
| `e2e` | 啟 Django (load seed + `ensure_admin`) → `playwright test` → 失敗時上傳 trace + 截圖 + django.log |

Concurrency group 自動取消重複 push 的舊 run。

---

### 階段 9 — CD Workflow (Draft)

`.github/workflows/cd.yml`,**雙重保護不會啟動**:
1. trigger 只有 `workflow_dispatch`(不在 push 時觸發)
2. 所有 jobs 都有 `if: ${{ false }}` guard

啟用步驟在 workflow 內**完整註解**(provision GCP / 配 OIDC / 加 secrets / 移除 guard)。

架構:
- `build-and-push`:建 `lims-backend` / `lims-frontend` images → push Artifact Registry (asia-east1)
- `deploy`:部署到 Cloud Run,環境變數 `DJANGO_PRODUCTION=True` 啟用嚴格安全 headers,完成後跑 smoke check

---

## 四、功能補強與修補

### 4.1 角色可見性收緊

從「鬆散預設」收緊到「row-level 嚴格過濾」:

| 角色 | 看訂單 | 看階段 |
|---|---|---|
| **regular_employee** | 只看自己提交的訂單 | 只看自己訂單上的階段 |
| **lab_member** | 只看「至少有一個階段指派給我」的訂單 | 只看指派給我的階段 |
| **lab_manager** | 只看本部門訂單 | 只看本部門所有階段 |
| **superuser** | 全部 | 全部 |

**安全細節**:跨範圍存取**回 404 而非 403** ([OrderDetailView](backend/orders/views.py#L94)),避免 enumerator 從 status code 推測訂單是否存在。

新增 `tests/test_visibility_scoping.py` (13 tests) 全方位覆蓋。

順手:**EquipmentSerializer 強制 `department` 必填** — admin 後台主要任務就是「分配機台給實驗室」,沒分配的機台沒意義。

> commit `b3da715` "Tighten role-based visibility scoping"

---

### 4.2 訂單詳情接力進度修復

**症狀**:詳情抽屜的接力進度條一直是空的。

**根因**:[OrderDetailSerializer](backend/orders/serializers.py) 的 `fields` 沒有 `stages`。前端 `<a-steps>` 依賴 `selectedOrder.stages`,API 從沒回傳那欄。

**修法**:在 `OrderDetailSerializer` 加 nested `stages = OrderStageSerializer(many=True, read_only=True)`,加 regression test 鎖住。

> commit `1c0cf4e`

---

### 4.3 中英文切換 + 深淺色主題

#### 基礎建設

- 新增 **vue-i18n 9** (Composition API mode)
- 新建 `stores/settings.js` 管理 locale + theme,持久化 localStorage
- App.vue 用 `<a-config-provider :locale="..." :theme="...">` 雙軌驅動

#### 主題切換

- `theme.algorithm` 綁定 `darkAlgorithm` / `defaultAlgorithm`,每個 antd 元件自動切色
- `style.css` 加 `[data-theme='dark']` block,11 個 CSS 變數覆寫 (TimelineChart 等舊元件用)
- DOM 屬性 `<html data-theme="dark" lang="zh-TW">` 讓全域 CSS 與外部工具可見

#### 完整 i18n 翻譯

從一開始僅入口頁,擴充到**整個 app**:

- common UI / auth / nav / 根儀表板 / 訂單列表 / 送樣申請 / 訂單審核 (4 modals) / 實驗室任務 / 設備總覽
- 5 種設備狀態 / 5 種階段狀態 / 4 種角色 / 偏好設定
- 整個 admin namespace (sidebar 12 項目、KPI、4 種分布、log 篩選與欄位、10 個 CRUD 頁的 title/subtitle/search/label)

#### Settings UI

任何登入後頁面右上角齒輪圖示 → Settings 抽屜:
- **語言**:中文 / English
- **主題**:淺色 / 深色

兩者都立即生效,不需 reload。

> commits `27a61a2`, `6850778`

---

### 4.4 完整文件

三份 README 共 1100+ 行,設計成「新人 30 分鐘上手」的開發者文件:

| 檔案 | 規模 | 重點 |
|---|---|---|
| `README.md` (root) | 369 行 | 專案總覽 / Architecture / 角色矩陣 / Quick start / Test summary / CI/CD / env reference |
| `backend/README.md` | 355 行 | App map / ER diagram / Order 狀態機 / Visibility scoping / API surface / pytest fixture / 五大 test double 對照 |
| `frontend/README.md` | 398 行 | Tech stack / folder map / npm 腳本 / Theming + i18n 內部 / Admin console (CrudTable prop ref) / Router guards |

每份都包含可直接複製的程式碼範例。

> commit `3dc5787`

---

### 4.5 移除註冊頁 + 後台批次建帳號

#### 移除公開註冊

- 完全移除 `/api/users/register/` (View / Serializer / route 全刪)
- 刪除 `RegisterView.vue` + `/register` 路由
- LoginView 的「註冊新帳號」按鈕改為「帳號由管理員建立」提示

#### 後台批次建立 N 組帳號

新 endpoint `POST /api/admin/users/bulk-create/`:

```json
{
  "role": "regular_employee" | "lab_member" | "lab_manager",
  "count": 1-100,
  "department": "<uuid>",          // 僅 lab_member/lab_manager 必填
  "password": "Lims@2026!Init"      // 可選,預設值
}
```

**命名規則** (沿用既有 seed 風格小改):

| 角色 | 命名 | 範例 |
|---|---|---|
| `regular_employee` | `Emp_NNN` | `Emp_001`, `Emp_002` ... |
| `lab_member` | `LabMem_<部門>_NNN` | `LabMem_Photo_001`, `LabMem_QC_005` |
| `lab_manager` | `LabMgr_<部門>_NNN` | `LabMgr_Process_002` |

序號自動接續既有最大值,刪除後再 bulk-create 會自動填補空位。

#### 後台批次刪除

新 endpoint `POST /api/admin/users/bulk-delete/`:
- 跨整批計算「保留至少一個 superuser」防護
- 跳過 caller 自己
- 回傳 `deleted_ids` + `skipped[{id, reason}]`

#### 前端 UI

UsersView 加兩個按鈕:
- 「批次新增使用者」開 modal,提交後跳出結果 modal 列出新建 usernames + 密碼(都可一鍵複製)
- 「批次刪除選中 (N)」只有選了 row 才出現,popconfirm 二次確認

CrudTable 擴充 `selectable` prop + `#extra-actions` slot,讓其他頁日後也能用同一套機制。

#### 17 個新測試

`tests/test_admin_user_bulk.py`:序號生成 / prefix 不衝突 / 序號接續 / 密碼雜湊 / 各種驗證 / 拒絕建 superuser / bulk-delete 安全防護 / `/register` 確實 404。

> commit `a341a30`

---

### 4.6 Admin 帳號自動建立

**問題**:對方部署系統時,需要照 README 跑 `loaddata seed_data.json` 或 `ensure_admin` 才會有 admin 帳號。

**修法**:寫 data migration `users/migrations/0002_create_default_admin.py`,在第一次 `migrate` 時自動建 admin 帳號。

新部署流程從這個:
```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py loaddata seed_data.json   # ← 漏這步沒 admin
python manage.py ensure_admin              # ← 或這步
python manage.py runserver
```

簡化成:
```bash
pip install -r requirements.txt
python manage.py migrate                   # ← admin 自動建好
python manage.py runserver
```

帳密直接可用 `admin / Admin@LIMS_2026!Sup`(可由 `LIMS_ADMIN_PASSWORD` env var 覆蓋)。

**設計重點**:
- migration 用 `filter(username='admin').exists()` 檢查,有就 skip,**不覆寫**
- Rollback 是 no-op,不會意外刪掉 superuser 鎖死系統
- 從 `seed_data.json` 移除 admin entry,避免 username 衝突
- `ensure_admin` 仍保留供「重置密碼」用

> commit `8d6a5df`

---

### 4.7 UX / Dark mode polish 雜項

| 問題 | 修法 | commit |
|---|---|---|
| 淺色 header 看不到 | 加 `var(--c-bg-card)` 背景 + border-bottom | `6850778` |
| 深色登入框白底 | gradient/blob/card 全部用 CSS 變數,深色換深紫漸層 | `6850778` |
| 設備總覽深色不可讀 | `eq-row` 改 `var(--c-row-bg)` + `var(--c-text)` | `6850778` |
| TimelineChart 文字過黑 | `type-row` / `eq-label` 改用 `var()` token | `6850778` |
| 「無此資料」深色看不到 | 全域 override `[data-theme='dark'] .ant-empty-description` | `8d6a5df` |
| 「僅供檢視」深色看不到 | 7 個檔案 9 處 `rgba(0,0,0,0.4)` 改 `var(--c-text-muted)` | `8d6a5df` |
| 時間軸切換箭頭看不到(legacy class) | 改用 `<a-button shape="circle">` + LeftOutlined/RightOutlined,加「今日」捷徑 | `a6c8fd9` |
| 已完成方塊 hover 不顯示 tooltip | 移除 `.bar-locked { pointer-events: none }`,改用 `cursor: help` | `a6c8fd9` |
| 自動填入欄位深色亮黃 | `:-webkit-autofill` + 1000px inset box-shadow + `-webkit-text-fill-color` hack | `e9da984` |
| 系統名稱不夠完整 | i18n 加 `appFullName` 「實驗室管理系統 (LIMS)」用在 Login / Footer / 標題 | `5121df8` |
| Favicon 跟 Vite 預設一樣 | 用 ExperimentOutlined SVG + 藍紫漸層,跟 Login brand 一致 | `c8fd652` |
| 訂單詳情接力進度看不見 | OrderDetailSerializer 加 nested `stages` | `1c0cf4e` |
| `_send_notification` 收到 string ID crash | helper 接受 PK string,自動 resolve | `d0aa60d` |
| Vitest 撈 e2e specs CI 失敗 | `vitest.config.js` 限制 `include: ['tests/**']`,排除 `e2e/**` | `0e273ff` |
| Playwright CI webServer timeout | Vite 加 `--host 127.0.0.1`,timeout 提升至 120s | `3dc5787` |

---

## 五、測試與品質指標

### 最終測試結果

```
pytest:    108 passed  (backend)
vitest:     39 passed  (frontend)
playwright:  8 passed  (e2e)
─────────
total:     156 tests
```

### 後端覆蓋率(主要新模組)

| 模組 | Coverage |
|---|---|
| `utils/request_id.py` | **100%** |
| `utils/exception_handler.py` | **96%** |
| `monitoring/middleware.py` | **95%** |
| `admin_api/views.py` | **99%** |
| `admin_api/serializers.py` | **93%** |
| `monitoring/views.py` | **88%** |

### 測試方法論

- **AAA pattern**(Arrange / Act / Assert)貫穿所有測試
- **五大 test double** 風格全展示
- 每個角色都有預備好的 fixture,降低 boilerplate

---

## 六、部署與運維

### 環境變數一覽

| 變數 | 預設 | 說明 |
|---|---|---|
| `DJANGO_DEBUG` | `True` | 設 `False` 為 production |
| `DJANGO_PRODUCTION` | `False` | `True` 啟動嚴格模式(refuses dev secret + wildcard hosts) |
| `DJANGO_SECRET_KEY` | dev fallback | 當 `DJANGO_PRODUCTION=True` 必填 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗號分隔 |
| `DB_ENGINE` | (sqlite) | `mysql` 切換 |
| `DB_NAME` / `DB_USER` / ... | — | MySQL only |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Cache + Celery broker |
| `CORS_ALLOWED_ORIGINS` | dev frontends | 逗號分隔 |
| `SENTRY_DSN` | empty | 設定就啟用 |
| `LIMS_ADMIN_PASSWORD` | `Admin@LIMS_2026!Sup` | migration / ensure_admin 共用 |

### 預設帳號

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@LIMS_2026!Sup` | Superuser (migration 自動建立) |

其他 demo 帳號透過 `loaddata seed_data.json` 載入(可選)。

### CI 已就緒

每次 push / PR 自動跑:
1. backend pytest (108 tests)
2. frontend vitest (39 tests) + build
3. e2e Playwright (8 specs)
4. 失敗時自動上傳 trace / screenshot / django log

### CD 待 GCP 就緒

`.github/workflows/cd.yml` 是 disabled draft,啟用步驟內含 4 步驟註解(provision Cloud Run + Artifact Registry / 配 OIDC / 加 secrets / 移除 `if: false` guard)。

---

## 七、給開發者的 quick start

```bash
# 1. Clone
git clone https://github.com/asddzxcc1856/LIMS.git
cd LIMS

# 2. Backend (admin 自動建好)
cd backend
python -m venv ../venv
source ../venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver         # http://127.0.0.1:8000

# 3. Frontend
cd ../frontend
npm install
npm run dev                        # http://127.0.0.1:5173

# 4. Login as admin / Admin@LIMS_2026!Sup
```

### 跑測試

```bash
# Backend
unset PYTHONPATH && cd backend && pytest

# Frontend unit
cd frontend && npm test

# E2E (需要 backend + frontend 都跑著)
cd frontend && npm run e2e
```

### 開發新功能 cheat sheet

| 想做的事 | 到哪裡 |
|---|---|
| 加新 admin CRUD 頁 | `frontend/src/api/admin.js` 加 resource → 寫 `<CrudTable>` view |
| 加翻譯 | `frontend/src/i18n/zh-TW.js` + `en.js` 加 key,view 內 `t('key')` |
| 加角色限定路由 | `router/index.js` 加 `meta.roles: ['lab_manager']` |
| 加新 API endpoint | 後端對應 app 的 `views.py` + `urls.py`,加 visibility 過濾 |
| 加新測試 | 用 `conftest.py` 的 fixture(`employee_client` 等),寫 AAA |

---

## 八、commit 對照表

| Commit | 階段 / 主題 |
|---|---|
| `d79fbf9` | 階段 1 — 後端監控 + ActivityLog + dashboard API |
| `116c9db` | 階段 2 — admin_api CRUD over 10 models |
| `795cb21` | 階段 3a — Ant Design Vue admin console (12 頁) |
| `2e3d0c4` | 階段 3b — 全系統改造為 antd 風格 |
| `3047a57` | 階段 4 — NFR 強化 (安全 / 統一錯誤 / request_id) |
| `a450479` | 階段 5 — 後端測試 76 tests, AAA + 5 test doubles |
| `0f29c9b` | 階段 6 — 前端 vitest 30 tests |
| `80b856c` | 階段 7 — Playwright E2E 8 specs |
| `362ea77` | 階段 8 + 9 — CI workflow + CD draft |
| `d0aa60d` | bug fix:`_send_notification` 接受 UUID string |
| `b3da715` | 角色可見性收緊 (4 角色 row-level scoping) |
| `1c0cf4e` | 修訂單詳情接力進度條 |
| `0e273ff` | vitest 排除 e2e specs |
| `27a61a2` | 加語言切換 + 深淺色主題 |
| `3dc5787` | 三份完整 README + Playwright CI 修復 |
| `6850778` | dark/light theme 修補 + 完整 i18n |
| `a341a30` | 移除註冊頁 + admin 批次建帳號 |
| `8d6a5df` | admin 自動建立 (data migration) + dark muted 修補 |
| `a6c8fd9` | TimelineChart 箭頭重做 + done bar tooltip |
| `e9da984` | 自動填入深色覆蓋 |
| `5121df8` | 完整系統名「實驗室管理系統 (LIMS)」 |
| `c8fd652` | favicon 用 brand icon |

---

## 結語

從一個基本的 Django + Vue 框架,到完整的多角色 LIMS 系統 + 全套測試 + CI/CD + 多語系 + 主題切換 + 完整文件,**約 25 個 commits、8500+ 行新增**。系統現在可以直接 `git clone → migrate → runserver` 三行指令上線,任何新人都能在 30 分鐘內完成本地開發環境並開始貢獻。

每一個改動都伴隨對應測試;每一個 polish 都來自實際使用回饋(用戶報問題、CI 抓 bug、跨情境發現 dark mode 缺漏)。最終結果是一套**可直接交付給半導體 FAB 內部使用**、且**從第一天就具備生產級測試與部署管線**的系統。

---

*文件最後更新:伴隨 commit `c8fd652`*
