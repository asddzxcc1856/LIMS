<template>
  <div class="tasks-page">
    <a-page-header
      title="實驗室任務"
      sub-title="執行已指派的實驗階段並回報完成"
      :back-icon="false"
    >
      <template #extra>
        <a-button @click="loadTasks" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          重新整理
        </a-button>
      </template>
    </a-page-header>

    <a-alert
      type="info"
      show-icon
      message="排程未開始的任務無法回報完成 (時間鎖)"
      style="margin-bottom: 16px"
    />

    <a-table
      :columns="columns"
      :data-source="tasks"
      :loading="loading"
      row-key="id"
      :row-class-name="rowClassName"
      :pagination="{ pageSize: 20, showTotal: (t) => `共 ${t} 筆` }"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'order_no'">
          <a-typography-text strong>{{ record.order_no || '—' }}</a-typography-text>
        </template>

        <template v-else-if="column.dataIndex === 'stage'">
          <div class="stage-cell">
            <span class="font-bold">{{ record.equipment_type_name }}</span>
            <a-tag style="margin-left: 6px">Step {{ record.step_order }}</a-tag>
          </div>
        </template>

        <template v-else-if="column.dataIndex === 'equipment_code'">
          <a-tag v-if="record.equipment_code" color="blue">
            <ToolOutlined />&nbsp;{{ record.equipment_code }}
          </a-tag>
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
            <StarFilled />&nbsp;指派給我
          </a-tag>
          <span v-else-if="record.assignee_name">{{ record.assignee_name }}</span>
          <span v-else class="muted">尚未指派</span>
        </template>

        <template v-else-if="column.dataIndex === '__actions__'">
          <template v-if="isAssignedToMe(record)">
            <a-tooltip
              v-if="!canComplete(record)"
              title="任務排程尚未開始,暫不可回報完成"
            >
              <a-button size="small" disabled>
                <template #icon><ClockCircleOutlined /></template>
                未到時間
              </a-button>
            </a-tooltip>
            <a-popconfirm
              v-else
              :title="`確認 Step ${record.step_order} (${record.equipment_type_name}) 已完成?`"
              ok-text="確認完成"
              cancel-text="取消"
              @confirm="handleComplete(record)"
            >
              <a-button type="primary" size="small">
                <template #icon><CheckCircleOutlined /></template>
                標記完成
              </a-button>
            </a-popconfirm>
          </template>
          <span v-else class="muted-text">僅供檢視</span>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ReloadOutlined,
  StarFilled,
  ToolOutlined,
} from '@ant-design/icons-vue'
import { completeStage, fetchStages } from '../../api/orders'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const tasks = ref([])
const loading = ref(false)

const columns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: '階段', dataIndex: 'stage', width: 220 },
  { title: '設備', dataIndex: 'equipment_code', width: 160 },
  { title: 'Lot ID', dataIndex: 'lot_id', width: 120 },
  { title: '排程', dataIndex: 'schedule', width: 240 },
  { title: '指派狀態', dataIndex: 'assignee', width: 140 },
  { title: '操作', dataIndex: '__actions__', width: 160, fixed: 'right' },
]

onMounted(loadTasks)

async function loadTasks() {
  loading.value = true
  try {
    const { data } = await fetchStages({ status: 'in_progress' })
    tasks.value = data.results || data || []
  } catch {
    message.error('載入任務失敗')
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

async function handleComplete(stage) {
  try {
    await completeStage(stage.id)
    message.success(`Step ${stage.step_order} 已標記為完成`)
    await loadTasks()
  } catch (e) {
    message.error(e.response?.data?.detail || '完成失敗')
  }
}

function rowClassName(record) {
  return isAssignedToMe(record) ? 'my-task-row' : ''
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
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
  color: rgba(0, 0, 0, 0.4);
  font-style: italic;
}
.muted-text {
  color: rgba(0, 0, 0, 0.4);
  font-size: 12px;
}
</style>
