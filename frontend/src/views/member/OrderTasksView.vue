<template>
  <div class="tasks-page">
    <a-page-header
      :title="t('tasks.title')"
      :sub-title="t('tasks.subtitle')"
      :back-icon="false"
    >
      <template #extra>
        <a-button @click="loadTasks" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </a-page-header>

    <a-alert
      type="info"
      show-icon
      :message="t('tasks.timeLockNote')"
      style="margin-bottom: 16px"
    />

    <a-table
      :columns="columns"
      :data-source="tasks"
      :loading="loading"
      row-key="id"
      :row-class-name="rowClassName"
      :pagination="{ pageSize: 20, showTotal: (n) => t('crud.paginationTotal', { total: n }) }"
      bordered
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'order_no'">
          <a-typography-text strong>{{ record.order_no || '—' }}</a-typography-text>
        </template>

        <template v-else-if="column.dataIndex === 'stage'">
          <div class="stage-cell">
            <span class="font-bold">
              {{ record.equipment_type_name || record.experiment_name || record.department_name }}
            </span>
            <a-tag style="margin-left: 6px">{{ t('review.step') }} {{ record.step_order }}</a-tag>
          </div>
        </template>

        <template v-else-if="column.dataIndex === 'equipment_code'">
          <a-tag v-if="record.equipment_code" color="blue">
            <ToolOutlined />&nbsp;{{ record.equipment_code }}
          </a-tag>
          <span v-else class="muted">—</span>
        </template>

        <template v-else-if="column.dataIndex === 'recipe'">
          <a-tooltip
            v-if="record.recipe_name"
            :title="formatRecipeParameters(record.recipe_parameters)"
          >
            <a-tag color="geekblue">
              <ExperimentOutlined />&nbsp;{{ record.recipe_name }}
              <span class="recipe-version">v{{ record.recipe_version }}</span>
            </a-tag>
          </a-tooltip>
          <span v-else class="muted">—</span>
        </template>

        <template v-else-if="column.dataIndex === 'schedule'">
          <div class="schedule-cell">
            <div>{{ formatDate(record.schedule_start) }}</div>
            <div class="muted">→ {{ formatDate(record.schedule_end) }}</div>
          </div>
        </template>

        <template v-else-if="column.dataIndex === 'assignee'">
          <a-tag v-if="isAssignedToMe(record)" color="green">
            <StarFilled />&nbsp;{{ t('tasks.assignedToMe') }}
          </a-tag>
          <span v-else-if="record.assignee_name">{{ record.assignee_name }}</span>
          <span v-else class="muted">{{ t('common.notAssigned') }}</span>
        </template>

        <template v-else-if="column.dataIndex === '__actions__'">
          <a-space wrap>
            <a-button size="small" @click="openHistory(record)">
              <template #icon><HistoryOutlined /></template>
              {{ t('tasks.history') }}
            </a-button>
            <template v-if="isAssignedToMe(record)">
              <a-popconfirm
                :title="t('tasks.confirmLoad', { step: record.step_order })"
                :ok-text="t('common.confirm')"
                :cancel-text="t('common.cancel')"
                @confirm="handleLoad(record)"
              >
                <a-button size="small">
                  <template #icon><UploadOutlined /></template>
                  {{ t('tasks.load') }}
                </a-button>
              </a-popconfirm>
              <a-tooltip
                v-if="!canComplete(record)"
                :title="t('tasks.notStartedTooltip')"
              >
                <a-button size="small" disabled>
                  <template #icon><ClockCircleOutlined /></template>
                  {{ t('tasks.notStarted') }}
                </a-button>
              </a-tooltip>
              <a-popconfirm
                v-else
                :title="t('tasks.confirmMarkDone', { step: record.step_order, type: record.equipment_type_name || record.experiment_name || record.department_name })"
                :ok-text="t('common.confirm')"
                :cancel-text="t('common.cancel')"
                @confirm="handleComplete(record)"
              >
                <a-button type="primary" size="small">
                  <template #icon><CheckCircleOutlined /></template>
                  {{ t('tasks.markDone') }}
                </a-button>
              </a-popconfirm>
            </template>
            <span v-if="!isAssignedToMe(record)" class="muted-text">
              {{ t('tasks.viewOnly') }}
            </span>
          </a-space>
        </template>
      </template>
    </a-table>

    <a-drawer
      v-model:open="historyOpen"
      :title="t('tasks.historyDrawerTitle', { no: historyTarget?.order_no || '' })"
      width="520"
      destroy-on-close
    >
      <a-spin :spinning="historyLoading">
        <a-empty
          v-if="!historyLoading && historyEvents.length === 0"
          :description="t('tasks.historyEmpty')"
        />
        <a-timeline v-else>
          <a-timeline-item
            v-for="event in historyEvents"
            :key="event.id"
            :color="eventColor(event.event_type)"
          >
            <div class="event-row">
              <a-tag :color="eventColor(event.event_type)">
                {{ t(`tasks.eventType.${event.event_type}`) }}
              </a-tag>
              <span class="event-time">{{ formatDate(event.occurred_at) }}</span>
            </div>
            <div class="event-meta">
              <span v-if="event.operator_username">
                <UserOutlined />&nbsp;{{ event.operator_username }}
              </span>
              <span v-if="event.equipment_code">
                · <ToolOutlined />&nbsp;{{ event.equipment_code }}
              </span>
              <span v-if="event.recipe_name">
                · <ExperimentOutlined />&nbsp;{{ event.recipe_name }} v{{ event.recipe_version }}
              </span>
            </div>
            <div v-if="event.notes" class="event-notes">{{ event.notes }}</div>
            <pre
              v-if="event.measurement && Object.keys(event.measurement).length"
              class="event-measurement"
            >{{ JSON.stringify(event.measurement, null, 2) }}</pre>
          </a-timeline-item>
        </a-timeline>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'

const { t } = useI18n()
import { message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  ReloadOutlined,
  StarFilled,
  ToolOutlined,
  UploadOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import {
  completeStage,
  fetchStageEvents,
  fetchStages,
  recordStageEvent,
} from '../../api/orders'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const tasks = ref([])
const loading = ref(false)

// History drawer state — lazily loads /stages/<id>/events/ when the
// member taps "History" so the table isn't loaded until needed.
const historyOpen = ref(false)
const historyLoading = ref(false)
const historyTarget = ref(null)
const historyEvents = ref([])

const columns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('tasks.stage'), dataIndex: 'stage', width: 220 },
  { title: t('tasks.equipment'), dataIndex: 'equipment_code', width: 160 },
  { title: t('tasks.recipe'), dataIndex: 'recipe', width: 180 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 120 },
  { title: t('tasks.schedule'), dataIndex: 'schedule', width: 240 },
  { title: t('tasks.assigneeStatus'), dataIndex: 'assignee', width: 140 },
  { title: t('tasks.actions'), dataIndex: '__actions__', width: 160, fixed: 'right' },
])

onMounted(loadTasks)

async function loadTasks() {
  loading.value = true
  try {
    const { data } = await fetchStages({ status: 'in_progress' })
    tasks.value = data.results || data || []
  } catch {
    message.error(t('tasks.loadFailed'))
  } finally {
    loading.value = false
  }
}

function isAssignedToMe(stage) {
  return stage.assignee === auth.user?.id
}

function canComplete(stage) {
  if (!stage.schedule_start) return true
  return dayjs().isAfter(dayjs(stage.schedule_start)) ||
    dayjs().isSame(dayjs(stage.schedule_start))
}

async function handleLoad(stage) {
  try {
    await recordStageEvent(stage.id, { event_type: 'load' })
    message.success(t('tasks.loadOk', { step: stage.step_order }))
    if (historyOpen.value && historyTarget.value?.id === stage.id) {
      await refreshHistory()
    }
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.loadEventFailed'))
  }
}

async function handleComplete(stage) {
  try {
    await completeStage(stage.id)
    message.success(t('tasks.completeOk', { step: stage.step_order }))
    await loadTasks()
    if (historyOpen.value && historyTarget.value?.id === stage.id) {
      await refreshHistory()
    }
  } catch (e) {
    message.error(e.response?.data?.detail || t('tasks.completeFailed'))
  }
}

async function openHistory(stage) {
  historyTarget.value = stage
  historyOpen.value = true
  await refreshHistory()
}

async function refreshHistory() {
  if (!historyTarget.value) return
  historyLoading.value = true
  try {
    const { data } = await fetchStageEvents(historyTarget.value.id)
    historyEvents.value = data || []
  } catch {
    historyEvents.value = []
  } finally {
    historyLoading.value = false
  }
}

function eventColor(type) {
  return {
    receive: 'cyan',
    load: 'blue',
    unload: 'green',
    abort: 'red',
    note: 'gray',
  }[type] || 'gray'
}

function rowClassName(record) {
  return isAssignedToMe(record) ? 'my-task-row' : ''
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}

function formatRecipeParameters(params) {
  if (!params) return t('tasks.recipeNoParams')
  if (typeof params === 'string') return params
  try {
    return JSON.stringify(params, null, 2)
  } catch {
    return t('tasks.recipeNoParams')
  }
}
</script>

<style scoped>
.tasks-page {
  padding: 0;
}
:deep(.my-task-row) {
  background: rgba(82, 196, 26, 0.05);
}
:deep(.my-task-row:hover > td) {
  background: rgba(82, 196, 26, 0.1) !important;
}
.stage-cell {
  display: flex;
  align-items: center;
}
.font-bold {
  font-weight: 600;
}
.schedule-cell {
  font-size: 12px;
  line-height: 1.6;
}
.muted {
  color: var(--c-text-muted);
  font-style: italic;
}
.muted-text {
  color: var(--c-text-muted);
  font-size: 12px;
}
.recipe-version {
  margin-left: 4px;
  opacity: 0.7;
  font-size: 11px;
}
.event-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.event-time {
  font-size: 12px;
  color: var(--c-text-muted);
}
.event-meta {
  font-size: 12px;
  color: var(--c-text-muted);
  margin-top: 4px;
}
.event-notes {
  margin-top: 6px;
  font-size: 13px;
  white-space: pre-wrap;
}
.event-measurement {
  margin-top: 6px;
  background: var(--c-bg-elevated, rgba(0, 0, 0, 0.03));
  padding: 8px;
  font-size: 12px;
  border-radius: 4px;
  overflow-x: auto;
}
</style>
