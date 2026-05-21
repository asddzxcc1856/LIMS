<template>
  <div class="reports-page">
    <a-page-header
      :title="t('reports.title')"
      :sub-title="t('reports.subtitle')"
      :back-icon="false"
    >
      <template #extra>
        <a-radio-group v-model:value="days" button-style="solid" @change="reload">
          <a-radio-button :value="7">{{ t('reports.last7') }}</a-radio-button>
          <a-radio-button :value="14">{{ t('reports.last14') }}</a-radio-button>
          <a-radio-button :value="30">{{ t('reports.last30') }}</a-radio-button>
        </a-radio-group>
        <a-button @click="reload" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </a-page-header>

    <!-- Business KPI strip -->
    <a-card
      :title="t('reports.businessTitle')"
      :bordered="false"
      :body-style="{ padding: '16px' }"
      style="margin-bottom: 16px"
    >
      <a-spin :spinning="loading">
        <a-row :gutter="[12, 12]" class="kpi-row">
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic :title="t('reports.businessCreated')" :value="totals.created || 0" />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessDone')"
              :value="totals.done || 0"
              :value-style="{ color: '#52c41a' }"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessRejected')"
              :value="totals.rejected || 0"
              :value-style="{ color: '#f5222d' }"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessRejectionRate')"
              :value="totals.rejection_rate_pct || 0"
              suffix="%"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessInProgress')"
              :value="totals.in_progress || 0"
              :value-style="{ color: '#1890ff' }"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessLeadDone')"
              :value="leadTimes.mean_hours_done || 0"
              suffix="h"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessLeadRejected')"
              :value="leadTimes.mean_hours_rejected || 0"
              suffix="h"
            />
          </a-col>
          <a-col :xs="12" :sm="8" :md="6">
            <a-statistic
              :title="t('reports.businessSignoffLatency')"
              :value="leadTimes.signoff_latency_hours || 0"
              suffix="h"
            />
          </a-col>
        </a-row>
      </a-spin>
      <div class="card-foot">{{ t('reports.businessHint') }}</div>
    </a-card>

    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :md="12">
        <a-card
          :title="t('reports.utilizationTitle')"
          :bordered="false"
          :body-style="{ padding: '16px 16px 8px' }"
        >
          <a-spin :spinning="loading">
            <LineChart
              v-if="utilizationSeries.length"
              :data="utilizationSeries"
              :series="[{ name: t('reports.utilizationPct'), key: 'utilization', color: '#1890ff' }]"
              :y-max="100"
              :y-format="(v) => `${v}%`"
              :aria-label="t('reports.utilizationTitle')"
            />
            <a-empty v-else :description="t('reports.noData')" />
          </a-spin>
          <div class="card-foot">{{ t('reports.utilizationHint') }}</div>
        </a-card>
      </a-col>

      <a-col :xs="24" :md="12">
        <a-card
          :title="t('reports.orderTrendTitle')"
          :bordered="false"
          :body-style="{ padding: '16px 16px 8px' }"
        >
          <a-spin :spinning="loading">
            <LineChart
              v-if="orderTrendSeries.length"
              :data="orderTrendSeries"
              :series="[
                { name: t('reports.orderCreated'), key: 'created', color: '#1890ff' },
                { name: t('reports.orderDone'), key: 'done', color: '#52c41a' },
                { name: t('reports.orderRejected'), key: 'rejected', color: '#f5222d' },
              ]"
              :aria-label="t('reports.orderTrendTitle')"
            />
            <a-empty v-else :description="t('reports.noData')" />
          </a-spin>
          <div class="card-foot">{{ t('reports.orderTrendHint') }}</div>
        </a-card>
      </a-col>
    </a-row>

    <!-- Stage / Sample / Equipment-type breakdown -->
    <a-row :gutter="[16, 16]" style="margin-top: 16px">
      <a-col :xs="24" :md="8">
        <a-card
          :title="t('reports.businessStageStatusTitle')"
          :bordered="false"
          :body-style="{ padding: '0' }"
        >
          <a-table
            :columns="statusColumns('stage')"
            :data-source="stageStatusRows"
            :pagination="false"
            size="small"
            row-key="status"
            :scroll="{ x: 'max-content' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-card
          :title="t('reports.businessSampleStatusTitle')"
          :bordered="false"
          :body-style="{ padding: '0' }"
        >
          <a-table
            :columns="statusColumns('sample')"
            :data-source="sampleStatusRows"
            :pagination="false"
            size="small"
            row-key="status"
            :scroll="{ x: 'max-content' }"
          />
        </a-card>
      </a-col>
      <a-col :xs="24" :md="8">
        <a-card
          :title="t('reports.businessByEquipmentTitle')"
          :bordered="false"
          :body-style="{ padding: '0' }"
        >
          <a-table
            :columns="equipmentTypeColumns"
            :data-source="byEquipmentType"
            :pagination="false"
            size="small"
            row-key="equipment_type_id"
            :scroll="{ x: 'max-content' }"
          />
        </a-card>
      </a-col>
    </a-row>

    <a-card
      :title="t('reports.operatorTitle')"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: '16px' }"
    >
      <a-spin :spinning="loading">
        <BarChart
          v-if="operatorRows.length"
          :data="operatorRows"
          :aria-label="t('reports.operatorTitle')"
        />
        <a-empty v-else :description="t('reports.noData')" />
      </a-spin>
      <div class="card-foot">{{ t('reports.operatorHint') }}</div>

      <a-divider />
      <a-table
        :columns="operatorTableColumns"
        :data-source="operatorTableRows"
        :pagination="{ pageSize: 10, showTotal: paginationTotal }"
        size="small"
        row-key="user_id"
        :scroll="{ x: 'max-content' }"
        :expand-row-by-click="false"
        :expanded-row-keys="expandedRowKeys"
        @expand="onExpand"
      >
        <template #expandedRowRender="{ record }">
          <div class="timeline-wrap">
            <a-spin :spinning="!!loadingDetailFor[record.user_id]">
              <template v-if="(operatorDetail[record.user_id]?.timeline || []).length">
                <a-table
                  :columns="timelineColumns"
                  :data-source="operatorDetail[record.user_id].timeline"
                  :pagination="{ pageSize: 15, hideOnSinglePage: true }"
                  size="small"
                  row-key="rowKey"
                  :scroll="{ x: 'max-content' }"
                >
                  <template #bodyCell="{ column, record: row }">
                    <template v-if="column.dataIndex === 'ts'">
                      {{ formatTs(row.ts) }}
                    </template>
                    <template v-else-if="column.dataIndex === 'kind'">
                      <a-tag :color="kindColor(row.kind)">
                        {{ t(`reports.kind${capitalize(row.kind)}`) }}
                      </a-tag>
                    </template>
                    <template v-else-if="column.dataIndex === 'action'">
                      <a-tag :color="actionColor(row.action)">{{ actionLabel(row) }}</a-tag>
                    </template>
                    <template v-else-if="column.dataIndex === 'detail'">
                      <span class="detail-cell">{{ row.detail || '—' }}</span>
                    </template>
                  </template>
                </a-table>
              </template>
              <a-empty
                v-else-if="operatorDetail[record.user_id]"
                :description="t('reports.operatorDrillEmpty')"
              />
            </a-spin>
          </div>
        </template>
      </a-table>
    </a-card>

    <!-- 子 LOT 履歷追蹤 — every Sample row + click-to-expand timeline. -->
    <a-card
      :title="t('reports.lotHistoryTitle')"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: '16px' }"
    >
      <div class="card-foot" style="margin-bottom: 12px">
        {{ t('reports.lotHistoryHint') }}
      </div>
      <a-spin :spinning="lotLoading">
        <a-table
          :columns="lotColumns"
          :data-source="lotRows"
          :pagination="{ pageSize: 10, showTotal: paginationTotal }"
          size="small"
          row-key="id"
          :scroll="{ x: 'max-content' }"
          :expanded-row-keys="lotExpandedKeys"
          :expand-row-by-click="false"
          @expand="onLotExpand"
        >
          <template #bodyCell="{ column, record: row }">
            <template v-if="column.dataIndex === 'status_display'">
              <a-tag :color="lotStatusColor(row.status)">{{ row.status_display }}</a-tag>
            </template>
            <template v-else-if="column.dataIndex === 'completed_at' || column.dataIndex === 'loaded_at' || column.dataIndex === 'created_at'">
              {{ formatTs(row[column.dataIndex]) }}
            </template>
          </template>
          <template #expandedRowRender="{ record: row }">
            <div class="timeline-wrap">
              <a-spin :spinning="!!loadingLotDetailFor[row.id]">
                <template v-if="(lotDetail[row.id]?.timeline || []).length">
                  <div class="lot-meta">
                    <a-descriptions :column="2" size="small" bordered>
                      <a-descriptions-item :label="t('reports.lotSample')">
                        {{ lotDetail[row.id].sample.full_code }}
                      </a-descriptions-item>
                      <a-descriptions-item :label="t('reports.lotOrder')">
                        {{ lotDetail[row.id].sample.order_no }}
                      </a-descriptions-item>
                      <a-descriptions-item :label="t('reports.lotEquipment')">
                        {{ lotDetail[row.id].sample.equipment_code || '—' }}
                      </a-descriptions-item>
                      <a-descriptions-item :label="t('reports.lotRecipe')">
                        {{ lotDetail[row.id].sample.recipe_name || '—' }}
                      </a-descriptions-item>
                    </a-descriptions>
                  </div>
                  <a-timeline mode="left" class="lot-timeline">
                    <a-timeline-item
                      v-for="(step, i) in lotDetail[row.id].timeline"
                      :key="i"
                      :color="lotStepColor(step.step)"
                    >
                      <div class="lot-step-row">
                        <a-tag :color="lotStepColor(step.step)">
                          {{ lotStepLabel(step.step) }}
                        </a-tag>
                        <span class="lot-step-ts">{{ formatTs(step.ts) }}</span>
                        <span class="lot-step-actor">
                          {{ step.actor_name || step.actor || '—' }}
                        </span>
                      </div>
                      <div class="lot-step-detail">{{ step.detail || '' }}</div>
                      <div
                        v-if="step.measurement && Object.keys(step.measurement).length"
                        class="lot-step-measurement"
                      >
                        {{ formatMeasurement(step.measurement) }}
                      </div>
                    </a-timeline-item>
                  </a-timeline>
                </template>
                <a-empty
                  v-else-if="lotDetail[row.id]"
                  :description="t('reports.operatorDrillEmpty')"
                />
              </a-spin>
            </div>
          </template>
        </a-table>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ReloadOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import {
  fetchChartEquipmentUtilization,
  fetchChartOperatorActivity,
  fetchChartOrderBusiness,
  fetchChartOrderTrend,
  fetchLotHistoryDetail,
  fetchLotHistoryList,
  fetchOperatorActivityDetail,
} from '../../api/admin'
import LineChart from '../../components/charts/LineChart.vue'
import BarChart from '../../components/charts/BarChart.vue'

const { t } = useI18n()

const loading = ref(false)
const days = ref(14)
const utilizationSeries = ref([])
const orderTrendSeries = ref([])
const operatorRows = ref([])
const totals = ref({})
const leadTimes = ref({})
const stageStatusRows = ref([])
const sampleStatusRows = ref([])
const byEquipmentType = ref([])
const expandedRowKeys = ref([])
const operatorDetail = reactive({})
const loadingDetailFor = reactive({})
// LOT history state
const lotLoading = ref(false)
const lotRows = ref([])
const lotExpandedKeys = ref([])
const lotDetail = reactive({})
const loadingLotDetailFor = reactive({})

const paginationTotal = (n) => t('crud.paginationTotal', { total: n })

const operatorTableColumns = computed(() => [
  { title: t('reports.operatorName'), dataIndex: 'username' },
  { title: t('reports.operatorEvents'), dataIndex: 'events', width: 120, sorter: true },
  { title: t('reports.operatorApprovals'), dataIndex: 'approvals', width: 120, sorter: true },
  { title: t('reports.operatorTotal'), dataIndex: 'total', width: 120, sorter: true },
])

const operatorTableRows = computed(() =>
  operatorRows.value.map((row) => ({
    ...row,
    user_id: row.user_id || row.username,
    total: (row.events || 0) + (row.approvals || 0),
  })),
)

const timelineColumns = computed(() => [
  { title: t('reports.timelineWhen'), dataIndex: 'ts', width: 160 },
  { title: t('reports.timelineKind'), dataIndex: 'kind', width: 110 },
  { title: t('reports.timelineAction'), dataIndex: 'action', width: 140 },
  { title: t('reports.timelineOrder'), dataIndex: 'order_no', width: 180 },
  { title: t('reports.timelineSample'), dataIndex: 'sample_code', width: 140 },
  { title: t('reports.timelineDetail'), dataIndex: 'detail' },
])

const equipmentTypeColumns = computed(() => [
  { title: t('reports.operatorName'), dataIndex: 'name' },
  { title: t('reports.businessEqRunning'), dataIndex: 'running_stages', width: 100 },
  { title: t('reports.businessEqDone'), dataIndex: 'completed_samples', width: 110 },
  { title: t('reports.businessEqRunHours'), dataIndex: 'mean_run_hours', width: 110 },
])

function statusColumns(domain) {
  return [
    {
      title: t('reports.businessStatus'),
      dataIndex: 'status',
      customRender: ({ value }) => statusLabel(domain, value),
    },
    { title: t('reports.businessCount'), dataIndex: 'count', width: 90 },
  ]
}

function statusLabel(domain, value) {
  if (!value) return '—'
  const candidate = `${domain === 'sample' ? 'sampleStatus' : 'stageStatus'}.${value}`
  return t(candidate, value)
}

onMounted(reload)

async function reload() {
  loading.value = true
  expandedRowKeys.value = []
  for (const k of Object.keys(operatorDetail)) delete operatorDetail[k]
  lotExpandedKeys.value = []
  for (const k of Object.keys(lotDetail)) delete lotDetail[k]
  try {
    const [{ data: util }, { data: trend }, { data: ops }, { data: biz }] =
      await Promise.all([
        fetchChartEquipmentUtilization(days.value),
        fetchChartOrderTrend(days.value),
        fetchChartOperatorActivity({ days: days.value, limit: 12 }),
        fetchChartOrderBusiness(days.value),
      ])
    utilizationSeries.value = util.series || []
    orderTrendSeries.value = trend.series || []
    operatorRows.value = (ops.series || []).map((row) => ({
      ...row,
      label: row.username,
      value: (row.events || 0) + (row.approvals || 0),
    }))
    totals.value = biz.totals || {}
    leadTimes.value = biz.lead_times || {}
    stageStatusRows.value = biz.stage_status || []
    sampleStatusRows.value = biz.sample_status || []
    byEquipmentType.value = biz.by_equipment_type || []
  } finally {
    loading.value = false
  }
  reloadLotList()
}

async function reloadLotList() {
  lotLoading.value = true
  try {
    const { data } = await fetchLotHistoryList({ days: days.value })
    lotRows.value = data.rows || []
  } finally {
    lotLoading.value = false
  }
}

const lotColumns = computed(() => [
  { title: t('reports.lotSample'), dataIndex: 'full_code', width: 160, fixed: 'left' },
  { title: t('reports.lotOrder'), dataIndex: 'order_no', width: 180 },
  { title: t('reports.lotStatus'), dataIndex: 'status_display', width: 140 },
  { title: t('split.colCount'), dataIndex: 'wafer_count', width: 70 },
  { title: t('reports.lotSplitBy'), dataIndex: 'split_by', width: 140 },
  { title: t('reports.lotDispatchBy'), dataIndex: 'dispatch_by', width: 140 },
  { title: t('reports.lotParamsBy'), dataIndex: 'params_by', width: 140 },
  { title: t('reports.lotOperator'), dataIndex: 'operator', width: 140 },
  { title: t('reports.lotEquipment'), dataIndex: 'equipment_code', width: 110 },
  { title: t('reports.lotRecipe'), dataIndex: 'recipe_name', width: 160 },
  { title: t('reports.lotCreatedAt'), dataIndex: 'created_at', width: 160 },
  { title: t('reports.lotCompletedAt'), dataIndex: 'completed_at', width: 160 },
])

async function onLotExpand(expanded, record) {
  const sid = record.id
  if (!expanded) {
    lotExpandedKeys.value = lotExpandedKeys.value.filter((k) => k !== sid)
    return
  }
  lotExpandedKeys.value = [...lotExpandedKeys.value, sid]
  if (lotDetail[sid]) return
  loadingLotDetailFor[sid] = true
  try {
    const { data } = await fetchLotHistoryDetail(sid)
    lotDetail[sid] = data
  } finally {
    loadingLotDetailFor[sid] = false
  }
}

function lotStatusColor(status) {
  return {
    waiting: 'orange', dispatched: 'blue', params_set: 'cyan',
    ready: 'purple', running: 'volcano', done: 'green',
  }[status] || 'default'
}
function lotStepColor(step) {
  return {
    approval: 'gold', receive: 'geekblue',
    split: 'volcano', dispatch: 'orange', set_parameters: 'magenta',
    assign: 'purple', load: 'blue', unload: 'cyan',
    note: 'default', abort: 'red',
  }[step] || 'gray'
}
function lotStepLabel(step) {
  return {
    approval: '簽核', receive: '接件 (隨簽核)',
    split: '分貨', dispatch: '派工', set_parameters: '設定參數',
    assign: '指派 (含自動指派)',
    load: '上貨', unload: '下貨',
    note: '量測 / 備註', abort: '中止 / 異常',
  }[step] || step
}
function formatMeasurement(m) {
  if (!m || !Object.keys(m).length) return ''
  return Object.entries(m).map(([k, v]) => `${k}=${v}`).join(', ')
}

async function onExpand(expanded, record) {
  const uid = record.user_id
  if (!expanded) {
    expandedRowKeys.value = expandedRowKeys.value.filter((k) => k !== uid)
    return
  }
  expandedRowKeys.value = [...expandedRowKeys.value, uid]
  if (operatorDetail[uid]) return
  loadingDetailFor[uid] = true
  try {
    const { data } = await fetchOperatorActivityDetail(uid, { days: days.value })
    operatorDetail[uid] = {
      ...data,
      timeline: (data.timeline || []).map((row, i) => ({
        ...row,
        rowKey: `${row.ts}-${i}`,
      })),
    }
  } finally {
    loadingDetailFor[uid] = false
  }
}

function formatTs(value) {
  return value ? dayjs(value).format('MM-DD HH:mm:ss') : '—'
}
function capitalize(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : ''
}
function kindColor(kind) {
  return { approval: 'gold', event: 'blue', sample: 'purple' }[kind] || 'default'
}
function actionColor(action) {
  return {
    approved: 'green', rejected: 'red',
    load: 'blue', unload: 'cyan', receive: 'geekblue',
    dispatch: 'orange', set_parameters: 'magenta', assign: 'purple',
    split: 'volcano', note: 'default', abort: 'red',
  }[action] || 'default'
}
function actionLabel(row) {
  if (row.kind === 'approval') return t(`stageStatus.${row.action}`, row.action)
  const map = {
    receive: '接件', load: '上貨', unload: '下貨',
    note: '量測', abort: '中止 / 異常',
    split: '分貨', dispatch: '派工', set_parameters: '設定參數',
    assign: '指派',
  }
  return map[row.action] || row.action
}
</script>

<style scoped>
.reports-page { padding: 0; }
.card-foot {
  margin-top: 8px;
  color: var(--c-text-muted);
  font-size: 12px;
}
.kpi-row .ant-statistic-title {
  color: var(--c-text-muted);
  font-size: 12px;
}
.timeline-wrap {
  padding: 8px 0;
}
.detail-cell {
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--c-text-muted);
}
.lot-meta {
  margin-bottom: 12px;
}
.lot-timeline {
  margin-top: 8px;
}
.lot-step-row {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  flex-wrap: wrap;
}
.lot-step-ts {
  color: var(--c-text-muted);
  font-size: 12px;
}
.lot-step-actor {
  font-weight: 600;
}
.lot-step-detail {
  margin-top: 2px;
  color: var(--c-text-muted);
  font-size: 12px;
  white-space: pre-wrap;
}
.lot-step-measurement {
  margin-top: 4px;
  padding: 4px 8px;
  background: rgba(24, 144, 255, 0.06);
  border-left: 2px solid #1890ff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  border-radius: 2px;
}
</style>
