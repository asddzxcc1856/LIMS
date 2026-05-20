<template>
  <div class="tasks-page">
    <a-page-header
      :title="t('tasks.title')"
      :sub-title="t('tasks.subtitle')"
      :back-icon="false"
    >
      <template #extra>
        <a-button @click="reloadAll" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </a-page-header>

    <a-tabs v-model:active-key="activeTab" type="card" class="stage-tabs">
      <!-- 1 · 待接件 (stage-level, still on the parent OrderStage) -->
      <a-tab-pane key="receive">
        <template #tab>
          <span><InboxOutlined />&nbsp;{{ t('tasks.tabReceive') }}
            <a-badge v-if="receiveStages.length" :count="receiveStages.length"
              :number-style="{ backgroundColor: '#fa8c16' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.tabReceiveHint')"
          style="margin-bottom: 12px" />
        <a-table :columns="receiveColumns" :data-source="receiveStages"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === '__actions__'">
              <a-popconfirm :title="t('tasks.confirmReceive', { no: record.order_no })"
                @confirm="handleReceive(record)"
                :ok-text="t('common.confirm')" :cancel-text="t('common.cancel')">
                <a-button type="primary" size="small">
                  <template #icon><InboxOutlined /></template>
                  {{ t('tasks.actionReceive') }}
                </a-button>
              </a-popconfirm>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 2 · 待分貨 (stage-level, opens dialog that creates samples) -->
      <a-tab-pane key="split">
        <template #tab>
          <span><ApartmentOutlined />&nbsp;{{ t('tasks.tabSplit') }}
            <a-badge v-if="splitStages.length" :count="splitStages.length"
              :number-style="{ backgroundColor: '#722ed1' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.tabSplitHint')"
          style="margin-bottom: 12px" />
        <a-table :columns="splitColumns" :data-source="splitStages"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === '__actions__'">
              <a-button type="primary" size="small" @click="openSplit(record)">
                <template #icon><ApartmentOutlined /></template>
                {{ t('tasks.actionSplit') }}
              </a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 3 · 待派工 — PER SAMPLE -->
      <a-tab-pane key="dispatch">
        <template #tab>
          <span><ClockCircleOutlined />&nbsp;{{ t('tasks.tabDispatch') }}
            <a-badge v-if="dispatchSamples.length" :count="dispatchSamples.length"
              :number-style="{ backgroundColor: '#1890ff' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.tabDispatchHint')"
          style="margin-bottom: 12px" />
        <a-card v-if="groupedEquipments.length"
          :title="t('review.timelineTitle')" :bordered="false"
          class="timeline-wrapper">
          <TimelineChart :grouped-equipments="groupedEquipments"
            :bookings="allBookings" />
        </a-card>
        <a-table :columns="sampleDispatchColumns" :data-source="dispatchSamples"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === '__actions__'">
              <a-button type="primary" size="small" @click="openDispatch(record)">
                <template #icon><ClockCircleOutlined /></template>
                {{ t('tasks.actionDispatch') }}
              </a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 4 · 待設定參數 — PER SAMPLE -->
      <a-tab-pane key="parameters">
        <template #tab>
          <span><SettingOutlined />&nbsp;{{ t('tasks.tabParameters') }}
            <a-badge v-if="parameterSamples.length" :count="parameterSamples.length"
              :number-style="{ backgroundColor: '#13c2c2' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.tabParametersHint')"
          style="margin-bottom: 12px" />
        <a-table :columns="sampleParameterColumns" :data-source="parameterSamples"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'recipe'">
              <a-tag v-if="record.recipe_name" color="geekblue">
                {{ localized(record, 'recipe_name') }}
                <span class="recipe-version">v{{ record.recipe_version }}</span>
              </a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'equipment'">
              <a-tag color="purple">{{ record.equipment_code }}</a-tag>
            </template>
            <template v-else-if="column.dataIndex === '__actions__'">
              <a-button type="primary" size="small" @click="openParameters(record)">
                <template #icon><SettingOutlined /></template>
                {{ t('tasks.actionSetParameters') }}
              </a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 5 · 待指派 — PER SAMPLE -->
      <a-tab-pane key="assign">
        <template #tab>
          <span><UserAddOutlined />&nbsp;{{ t('tasks.tabAssign') }}
            <a-badge v-if="assignSamples.length" :count="assignSamples.length"
              :number-style="{ backgroundColor: '#52c41a' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.tabAssignHint')"
          style="margin-bottom: 12px" />
        <a-table :columns="sampleAssignColumns" :data-source="assignSamples"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === '__actions__'">
              <a-button type="primary" size="small" @click="openAssign(record)">
                <template #icon><UserAddOutlined /></template>
                {{ t('tasks.actionAssign') }}
              </a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 6 · 上下貨 — PER SAMPLE -->
      <a-tab-pane key="running">
        <template #tab>
          <span><ToolOutlined />&nbsp;{{ t('tasks.tabRunning') }}
            <a-badge v-if="runningSamples.length" :count="runningSamples.length"
              :number-style="{ backgroundColor: '#fa541c' }" class="tab-badge" />
          </span>
        </template>
        <a-alert type="info" show-icon :message="t('tasks.timeLockNote')"
          style="margin-bottom: 12px" />
        <a-table :columns="sampleRunningColumns" :data-source="runningSamples"
          :loading="loading" row-key="id" bordered
          :row-class-name="(r) => isAssignedToMe(r) ? 'my-task-row' : ''"
          :pagination="{ pageSize: 20, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'assignee'">
              <a-tag v-if="isAssignedToMe(record)" color="green">
                <StarFilled />&nbsp;{{ t('tasks.assignedToMe') }}
              </a-tag>
              <span v-else-if="record.assignee_username">{{ record.assignee_username }}</span>
              <span v-else class="muted">{{ t('common.notAssigned') }}</span>
            </template>
            <template v-else-if="column.dataIndex === 'recipe'">
              <a-tooltip v-if="record.recipe_name"
                :title="formatRecipeParameters(record.recipe_parameters, record.parameter_overrides)">
                <a-tag color="geekblue">
                  <ExperimentOutlined />&nbsp;{{ localized(record, 'recipe_name') }}
                  <span class="recipe-version">v{{ record.recipe_version }}</span>
                </a-tag>
                <a-tag v-if="record.parameter_overrides && Object.keys(record.parameter_overrides).length"
                  color="orange" style="margin-left: 4px">
                  ⚙ {{ Object.keys(record.parameter_overrides).length }}
                </a-tag>
              </a-tooltip>
              <span v-else class="muted">—</span>
            </template>
            <template v-else-if="column.dataIndex === '__actions__'">
              <template v-if="isAssignedToMe(record)">
                <a-space wrap>
                  <a-popconfirm v-if="record.status === 'ready'"
                    :title="t('tasks.confirmLoad', { step: record.sub_code })"
                    @confirm="handleLoad(record)"
                    :ok-text="t('common.confirm')" :cancel-text="t('common.cancel')">
                    <a-button type="primary" size="small">
                      <template #icon><UploadOutlined /></template>
                      {{ t('tasks.actionLoad') }}
                    </a-button>
                  </a-popconfirm>

                  <!-- 數據蒐集 — Simulate one telemetry reading. In real
                       deployment, machine agents POST this endpoint
                       directly; this button is the demo equivalent. -->
                  <a-button v-if="record.status === 'running'"
                    size="small"
                    :loading="telemetryBusyId === record.id"
                    @click="simulateTelemetry(record)"
                  >
                    <template #icon><ApiOutlined /></template>
                    {{ t('tasks.actionTelemetry') }}
                  </a-button>

                  <a-popconfirm v-if="record.status === 'running'"
                    :title="t('tasks.confirmUnload', { code: record.full_code })"
                    @confirm="handleComplete(record)"
                    :ok-text="t('common.confirm')" :cancel-text="t('common.cancel')">
                    <a-button type="primary" size="small">
                      <template #icon><CheckCircleOutlined /></template>
                      {{ t('tasks.actionUnload') }}
                    </a-button>
                  </a-popconfirm>
                </a-space>
              </template>
              <span v-else class="muted-text">{{ t('tasks.viewOnly') }}</span>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <!-- 7 · 歷史 — PER SAMPLE -->
      <a-tab-pane key="history">
        <template #tab>
          <span><HistoryOutlined />&nbsp;{{ t('tasks.tabHistory') }}</span>
        </template>
        <a-table :columns="sampleHistoryColumns" :data-source="historySamples"
          :loading="loading" row-key="id" bordered
          :pagination="{ pageSize: 15, showTotal: paginationTotal }"
          :scroll="{ x: 'max-content' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.dataIndex === 'status'">
              <a-tag color="success">{{ record.status_display }}</a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'equipment'">
              <a-tag color="purple">{{ record.equipment_code }}</a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'recipe'">
              <a-tag v-if="record.recipe_name" color="geekblue">
                {{ localized(record, 'recipe_name') }}
              </a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'completed_at'">
              {{ formatDate(record.completed_at) }}
            </template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>

    <!-- ─── Modals ─────────────────────────────────────────────── -->
    <SampleSplitDialog v-model:open="splitOpen" :order="splitTarget" />

    <a-modal v-model:open="dispatchOpen"
      :title="t('tasks.dispatchModalTitle', { no: dispatchTarget?.full_code || '' })"
      :width="modalWidth" :confirm-loading="dispatchBusy"
      :ok-text="t('tasks.actionDispatch')" :cancel-text="t('common.cancel')"
      @ok="confirmDispatch">
      <a-form layout="vertical">
        <a-row :gutter="12">
          <a-col :xs="24" :sm="12">
            <a-form-item :label="t('review.scheduleStart')" required>
              <a-date-picker v-model:value="dispatchStart" show-time
                format="YYYY-MM-DD HH:mm" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :sm="12">
            <a-form-item :label="t('review.scheduleEnd')" required>
              <a-date-picker v-model:value="dispatchEnd" show-time
                format="YYYY-MM-DD HH:mm" style="width: 100%" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item :label="t('review.assignMachine')" required>
          <a-select v-model:value="dispatchEquipment"
            :options="machineOptions" :loading="loadingMachines"
            :placeholder="t('review.recipePickerPlaceholder')"
            show-search option-filter-prop="label" allow-clear />
        </a-form-item>
        <a-form-item :label="t('review.assignRecipe')" required>
          <a-select v-model:value="dispatchRecipe"
            :options="recipeOptionsForDispatch" :loading="loadingRecipes"
            :placeholder="dispatchEquipment ? t('review.recipePickerPlaceholder') : t('review.recipePickerDisabled')"
            :disabled="!dispatchEquipment"
            show-search option-filter-prop="label" allow-clear />
          <div class="recipe-help">{{ t('review.recipeHelp') }}</div>
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal v-model:open="paramOpen"
      :title="t('tasks.paramModalTitle', { no: paramTarget?.full_code || '' })"
      :width="modalWidth" :confirm-loading="paramBusy"
      :ok-text="t('tasks.actionSetParameters')" :cancel-text="t('common.cancel')"
      @ok="confirmParameters">
      <a-alert type="info" show-icon style="margin-bottom: 12px"
        :message="t('review.paramOverridesHint')" />
      <div v-if="paramRecipeParameters && Object.keys(paramRecipeParameters).length">
        <a-row
          v-for="key in Object.keys(paramRecipeParameters)" :key="key"
          :gutter="12"
          class="override-row"
          align="middle"
        >
          <a-col :xs="24" :sm="14">
            <code class="override-key">{{ paramLabel(key) }}</code>
            <div class="override-default">
              {{ t('review.paramDefault') }}:
              <code>{{ String(paramRecipeParameters[key]) }}</code>
            </div>
          </a-col>
          <a-col :xs="24" :sm="10">
            <a-input
              v-model:value="paramOverrides[key]"
              :placeholder="String(paramRecipeParameters[key])"
              allow-clear
              size="small"
              class="override-input"
            />
          </a-col>
        </a-row>
      </div>
      <a-empty v-else :description="t('tasks.paramNoKnobs')" />
    </a-modal>

    <a-modal v-model:open="assignOpen"
      :title="t('tasks.assignModalTitle', { no: assignTarget?.full_code || '' })"
      :width="modalWidth" :confirm-loading="assignBusy"
      :ok-text="t('tasks.actionAssign')" :cancel-text="t('common.cancel')"
      @ok="confirmAssign">
      <a-alert type="warning" show-icon style="margin-bottom: 12px"
        :message="t('tasks.assignHint')" />

      <!-- Upstream chain — surfaces who already worked on this sample
           so the user can see whom they cannot pick. -->
      <div v-if="upstreamChain.length" class="upstream-chain">
        <div class="upstream-title">{{ t('tasks.upstreamTitle') }}</div>
        <a-tag
          v-for="row in upstreamChain"
          :key="row.step"
          color="default"
          class="upstream-tag"
        >
          <strong>{{ row.step }}</strong>&nbsp;·&nbsp;{{ row.user }}
        </a-tag>
      </div>

      <a-form layout="vertical">
        <a-form-item :label="t('review.assignTo')" required>
          <a-select v-model:value="assignPick"
            :options="memberOptions"
            :placeholder="t('tasks.pickAssignee')"
            show-search option-filter-prop="label" allow-clear />
          <div class="recipe-help">{{ t('tasks.assignFilterHint') }}</div>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  ApartmentOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  InboxOutlined,
  ReloadOutlined,
  SettingOutlined,
  StarFilled,
  ToolOutlined,
  UploadOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import {
  assignSample,
  completeSample,
  dispatchSample,
  fetchSamples,
  fetchStages,
  loadSample,
  receiveStage,
  recordSampleTelemetry,
  setSampleParameters,
} from '../../api/orders'
import { fetchRecipes } from '../../api/equipments'
import { fetchBookings } from '../../api/scheduling'
import { useAuthStore } from '../../stores/auth'
import { useBreakpoint } from '../../composables/useBreakpoint'
import { useLocalizedLabel } from '../../composables/useLocalizedLabel'
import client from '../../api/client'
import SampleSplitDialog from '../../components/SampleSplitDialog.vue'
import TimelineChart from '../../components/TimelineChart.vue'

const { t, locale } = useI18n()
const auth = useAuthStore()
const { isMobile } = useBreakpoint()
const { localized } = useLocalizedLabel()

const loading = ref(false)
const activeTab = ref('receive')
const modalWidth = computed(() => (isMobile.value ? '95vw' : 640))

const stages = ref([])
const samples = ref([])
const labMembers = ref([])
const labMachines = ref([])
const labRecipes = ref([])
const loadingMachines = ref(false)
const loadingRecipes = ref(false)
const groupedEquipments = ref([])
const allBookings = ref([])

const paginationTotal = (n) => t('crud.paginationTotal', { total: n })

onMounted(reloadAll)

async function reloadAll() {
  loading.value = true
  try {
    await Promise.allSettled([
      loadStages(),
      loadSamples(),
      loadLabRoster(),
      loadMachines(),
      loadRecipes(),
      loadTimelineData(),
    ])
  } finally { loading.value = false }
}

async function loadStages() {
  const { data } = await fetchStages({ lab_queue: 'true' })
  stages.value = data.results || data || []
}

async function loadSamples() {
  const { data } = await fetchSamples()
  samples.value = Array.isArray(data) ? data : (data.results || [])
}

async function loadLabRoster() {
  try {
    const { data } = await client.get('/users/?role=lab_member')
    labMembers.value = data.results || data || []
  } catch { labMembers.value = [] }
}

async function loadMachines() {
  loadingMachines.value = true
  try {
    const { data } = await client.get('/equipments/')
    labMachines.value = data.results || data || []
  } catch { labMachines.value = [] } finally { loadingMachines.value = false }
}

async function loadRecipes() {
  loadingRecipes.value = true
  try {
    const { data } = await fetchRecipes({ is_active: true })
    labRecipes.value = data.results || data || []
  } catch { labRecipes.value = [] } finally { loadingRecipes.value = false }
}

async function loadTimelineData() {
  try {
    const [resEq, resBk, resProf] = await Promise.all([
      client.get('/equipments/status-matrix/'),
      fetchBookings(),
      client.get('/users/profile/'),
    ])
    const myDept = resProf.data.department_name
    groupedEquipments.value = (resEq.data || [])
      .map((type) => ({
        ...type,
        equipments: type.equipments.filter((eq) => eq.department_name === myDept),
      }))
      .filter((type) => type.equipments.length > 0)
    allBookings.value = resBk.data.results || resBk.data || []
  } catch {
    groupedEquipments.value = []
    allBookings.value = []
  }
}

// ── Stage-level filters (receive / split still operate on the stage) ──
const receiveStages = computed(() =>
  stages.value.filter((s) => s.status === 'waiting' && !s.received_at))

const splitStages = computed(() =>
  // APPROVED stage with sample_count == 0 — must split before per-sample
  // dispatch becomes available.
  stages.value.filter((s) => s.status === 'approved' && Number(s.sample_count || 0) === 0))

// ── Sample-level filters (派工 / 設定參數 / 指派 / 上下貨 / 歷史) ────
const dispatchSamples = computed(() =>
  samples.value.filter((s) => s.status === 'waiting'))

const parameterSamples = computed(() =>
  samples.value.filter((s) => s.status === 'dispatched'))

const assignSamples = computed(() =>
  samples.value.filter((s) => s.status === 'params_set'))

const runningSamples = computed(() =>
  samples.value.filter((s) => s.status === 'ready' || s.status === 'running'))

const historySamples = computed(() =>
  samples.value.filter((s) => s.status === 'done'))

// ── Column definitions ──────────────────────────────────────────────
const receiveColumns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('createOrder.experimentLabel'), dataIndex: 'experiment_name', width: 220 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 130 },
  { title: t('orders.urgent'), dataIndex: 'is_urgent', width: 80 },
  { title: t('orders.requirements'), dataIndex: 'requirements', ellipsis: true },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 130, fixed: 'right' },
])

const splitColumns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('createOrder.experimentLabel'), dataIndex: 'experiment_name', width: 220 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 130 },
  { title: t('orders.requirements'), dataIndex: 'requirements', ellipsis: true },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 120, fixed: 'right' },
])

const sampleDispatchColumns = computed(() => [
  { title: t('tasks.sampleCode'), dataIndex: 'full_code', width: 180, fixed: 'left' },
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('split.colCount'), dataIndex: 'wafer_count', width: 90 },
  { title: t('split.colOrder'), dataIndex: 'execution_order', width: 100 },
  { title: t('createOrder.experimentLabel'), dataIndex: 'experiment_name', width: 200 },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 130, fixed: 'right' },
])

const sampleParameterColumns = computed(() => [
  { title: t('tasks.sampleCode'), dataIndex: 'full_code', width: 180, fixed: 'left' },
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('tasks.equipment'), dataIndex: 'equipment', width: 140 },
  { title: t('tasks.recipe'), dataIndex: 'recipe', width: 220 },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 150, fixed: 'right' },
])

const sampleAssignColumns = computed(() => [
  { title: t('tasks.sampleCode'), dataIndex: 'full_code', width: 180, fixed: 'left' },
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('tasks.equipment'), dataIndex: 'equipment_code', width: 140 },
  { title: t('tasks.recipe'), dataIndex: 'recipe_name', width: 200 },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 130, fixed: 'right' },
])

const sampleRunningColumns = computed(() => [
  { title: t('tasks.sampleCode'), dataIndex: 'full_code', width: 180, fixed: 'left' },
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('tasks.equipment'), dataIndex: 'equipment_code', width: 140 },
  { title: t('tasks.recipe'), dataIndex: 'recipe', width: 220 },
  { title: t('tasks.assigneeStatus'), dataIndex: 'assignee', width: 140 },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 220, fixed: 'right' },
])

const sampleHistoryColumns = computed(() => [
  { title: t('tasks.sampleCode'), dataIndex: 'full_code', width: 180, fixed: 'left' },
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('tasks.equipment'), dataIndex: 'equipment', width: 140 },
  { title: t('tasks.recipe'), dataIndex: 'recipe', width: 200 },
  { title: t('orders.status'), dataIndex: 'status', width: 120 },
  { title: t('tasks.completedAt'), dataIndex: 'completed_at', width: 180 },
])

// ── Action handlers ─────────────────────────────────────────────────
async function handleReceive(stage) {
  try { await receiveStage(stage.id)
    message.success(t('review.receiveSuccess', { no: stage.order_no }))
    await reloadAll()
  } catch (e) { message.error(e.response?.data?.detail || t('review.receiveFailed')) }
}

async function handleLoad(sample) {
  try { await loadSample(sample.id)
    message.success(t('tasks.loadOk', { step: sample.sub_code }))
    await reloadAll()
  } catch (e) { message.error(e.response?.data?.detail || t('tasks.loadFailed')) }
}

// 數據蒐集 demo button — sends one fake measurement so the user can
// see telemetry flowing in. Real machines POST this same endpoint
// directly; this is just an in-UI way to exercise the audit chain.
const telemetryBusyId = ref(null)
async function simulateTelemetry(sample) {
  telemetryBusyId.value = sample.id
  try {
    // Generate a plausible measurement based on the recipe's knobs so
    // the audit log shows a realistic reading instead of fixed noise.
    const params = sample.recipe_parameters || {}
    const measurement = {}
    for (const key of Object.keys(params)) {
      const base = Number(params[key])
      if (Number.isFinite(base)) {
        const jitter = base * (0.95 + Math.random() * 0.10)
        measurement[key] = Math.round(jitter * 100) / 100
      } else {
        measurement[key] = params[key]
      }
    }
    measurement.sampled_at = new Date().toISOString()
    await recordSampleTelemetry(sample.id, { measurement, finished: false })
    message.success(t('tasks.telemetryOk'))
    await reloadAll()
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.telemetryFailed'))
  } finally { telemetryBusyId.value = null }
}

async function handleComplete(sample) {
  try { await completeSample(sample.id)
    message.success(t('tasks.completeOk', { step: sample.sub_code }))
    await reloadAll()
  } catch (e) { message.error(e.response?.data?.detail || t('tasks.completeFailed')) }
}

// ── Split modal ─────────────────────────────────────────────────────
const splitOpen = ref(false)
const splitTarget = ref(null)
function openSplit(stage) {
  splitTarget.value = { id: stage.order, order_no: stage.order_no }
  splitOpen.value = true
}

// ── Dispatch modal (per-sample) ─────────────────────────────────────
const dispatchOpen = ref(false)
const dispatchTarget = ref(null)
const dispatchStart = ref(null)
const dispatchEnd = ref(null)
const dispatchEquipment = ref(null)
const dispatchRecipe = ref(null)
const dispatchBusy = ref(false)

const machineOptions = computed(() =>
  labMachines.value.map((eq) => ({
    value: eq.id,
    label: machineLabel(eq),
    disabled: eq.status !== 'available',
  })))

function machineLabel(eq) {
  // Locale-aware machine label. zh-TW maps the technical EquipmentType
  // name through ``equipmentTypeZh`` so the user sees "EUV 曝光機"
  // rather than "EUV Scanner".
  const baseName = eq.type_name || ''
  const typeName = locale.value === 'en'
    ? baseName
    : t(`equipmentTypeZh.${baseName}`, baseName)
  return `${eq.code} · ${typeName} · ${eq.status}`
}

const recipeOptionsForDispatch = computed(() => {
  if (!dispatchEquipment.value) return []
  const eq = labMachines.value.find((e) => e.id === dispatchEquipment.value)
  if (!eq) return []
  return labRecipes.value
    .filter((r) => r.equipment_type === eq.equipment_type && r.is_active)
    .map((r) => ({ value: r.id, label: `${localized(r)} v${r.version}` }))
})

function openDispatch(sample) {
  dispatchTarget.value = sample
  dispatchStart.value = null
  dispatchEnd.value = null
  dispatchEquipment.value = null
  dispatchRecipe.value = null
  dispatchOpen.value = true
}

async function confirmDispatch() {
  if (!dispatchStart.value || !dispatchEnd.value
      || !dispatchEquipment.value || !dispatchRecipe.value) {
    message.warning(t('tasks.dispatchFieldsRequired'))
    return
  }
  dispatchBusy.value = true
  try {
    await dispatchSample(dispatchTarget.value.id, {
      schedule_start: dispatchStart.value.toISOString(),
      schedule_end: dispatchEnd.value.toISOString(),
      equipment: dispatchEquipment.value,
      recipe: dispatchRecipe.value,
    })
    dispatchOpen.value = false
    message.success(t('tasks.dispatchOk'))
    await reloadAll()
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.dispatchFailed'))
  } finally { dispatchBusy.value = false }
}

// ── Parameters modal (per-sample) ───────────────────────────────────
const paramOpen = ref(false)
const paramTarget = ref(null)
const paramOverrides = ref({})
const paramBusy = ref(false)

const paramRecipeParameters = computed(() => paramTarget.value?.recipe_parameters || {})

function openParameters(sample) {
  paramTarget.value = sample
  paramOverrides.value = {}
  paramOpen.value = true
}

async function confirmParameters() {
  const cleaned = Object.fromEntries(
    Object.entries(paramOverrides.value).filter(([, v]) => v !== '' && v != null),
  )
  paramBusy.value = true
  try {
    await setSampleParameters(paramTarget.value.id, { parameter_overrides: cleaned })
    paramOpen.value = false
    message.success(t('tasks.paramSetOk'))
    await reloadAll()
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.paramSetFailed'))
  } finally { paramBusy.value = false }
}

// ── Assign modal (per-sample) ───────────────────────────────────────
const assignOpen = ref(false)
const assignTarget = ref(null)
const assignPick = ref(null)
const assignBusy = ref(false)

// Build a Set of usernames that ALREADY touched this sample upstream.
// They're disabled in the dropdown so the user can't accidentally pick
// them — backend assign_sample re-validates and 400s on attempts.
const upstreamUsernames = computed(() => {
  const sample = assignTarget.value
  if (!sample) return new Set()
  return new Set([
    sample.created_by_username,
    sample.dispatched_by_username,
    sample.parameters_set_by_username,
  ].filter(Boolean))
})

const memberOptions = computed(() => {
  const myUsername = auth.user?.username
  const blocked = upstreamUsernames.value
  return labMembers.value.map((u) => {
    const isSelf = u.username === myUsername
    const isUpstream = blocked.has(u.username)
    let suffix = ''
    if (isSelf) suffix = ` · ${t('tasks.assignSelfTag')}`
    else if (isUpstream) suffix = ` · ${t('tasks.assignUpstreamTag')}`
    return {
      value: u.id,
      label: `${u.name || u.username}${suffix}`,
      disabled: isSelf || isUpstream,
    }
  })
})

// Chain of upstream operators rendered above the dropdown so the user
// understands who did what on this sample.
const upstreamChain = computed(() => {
  const sample = assignTarget.value
  if (!sample) return []
  return [
    { step: t('tasks.chainSplit'), user: sample.created_by_username },
    { step: t('tasks.chainDispatch'), user: sample.dispatched_by_username },
    { step: t('tasks.chainParams'), user: sample.parameters_set_by_username },
  ].filter((r) => r.user)
})

function openAssign(sample) {
  assignTarget.value = sample
  assignPick.value = null
  assignOpen.value = true
}

async function confirmAssign() {
  if (!assignPick.value) {
    message.warning(t('tasks.pickAssignee'))
    return
  }
  assignBusy.value = true
  try {
    await assignSample(assignTarget.value.id, { assignee: assignPick.value })
    assignOpen.value = false
    message.success(t('tasks.assignOk'))
    await reloadAll()
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.assignFailed'))
  } finally { assignBusy.value = false }
}

// ── Helpers ─────────────────────────────────────────────────────────
function isAssignedToMe(sample) { return sample.assignee === auth.user?.id }
function formatDate(value) { return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—' }

function paramLabel(key) {
  // Chinese label map for recipe knobs; falls back to the technical key.
  return t(`paramLabel.${key}`, key)
}

function formatRecipeParameters(params, overrides) {
  const base = params && typeof params === 'object' ? { ...params } : {}
  const merged = { ...base, ...(overrides || {}) }
  if (!Object.keys(merged).length) return t('tasks.recipeNoParams')
  return Object.entries(merged)
    .map(([k, v]) => overrides && k in overrides
      ? `${paramLabel(k)}: ${v}  ← override`
      : `${paramLabel(k)}: ${v}`)
    .join('\n')
}
</script>

<style scoped>
.tasks-page { padding: 0; }
.stage-tabs :deep(.ant-tabs-nav-list) { flex-wrap: wrap; }
.tab-badge { margin-left: 6px; }
.timeline-wrapper { margin-bottom: 16px; }
:deep(.my-task-row) { background: rgba(82, 196, 26, 0.05); }
:deep(.my-task-row:hover > td) { background: rgba(82, 196, 26, 0.1) !important; }
.muted { color: var(--c-text-muted); font-style: italic; }
.muted-text { color: var(--c-text-muted); font-size: 12px; }
.recipe-version { margin-left: 4px; opacity: 0.7; font-size: 11px; }
.override-row {
  margin-bottom: 10px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--c-border);
}
.override-row:last-child { border-bottom: none; }
.override-key {
  font-size: 13px;
  font-weight: 600;
  color: var(--c-text);
}
.override-default {
  font-size: 11px;
  color: var(--c-text-muted);
  margin-top: 2px;
}
/* Compact input — 160px on desktop is plenty for typical knob values
   (temp, time, dose) and keeps the form looking dense + tidy. */
.override-input { max-width: 160px; }
.override-row :deep(.ant-input) { max-width: 160px; }
@media (max-width: 575px) {
  .override-input,
  .override-row :deep(.ant-input) { max-width: 100%; }
}

.upstream-chain {
  margin-bottom: 16px;
  padding: 10px 12px;
  background: rgba(24, 144, 255, 0.06);
  border-radius: 6px;
}
.upstream-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-muted);
  margin-bottom: 8px;
}
.upstream-tag {
  margin-bottom: 4px;
}
.recipe-help { color: var(--c-text-muted); font-size: 12px; line-height: 1.4; margin-top: 4px; }
</style>
