<template>
  <div class="orders-page">
    <a-page-header title="我的訂單" sub-title="追蹤所有送樣申請的接力進度" :back-icon="false">
      <template #extra>
        <a-button @click="loadOrders" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          重新整理
        </a-button>
        <a-button type="primary" @click="$router.push('/orders/create')">
          <template #icon><FileAddOutlined /></template>
          新建訂單
        </a-button>
      </template>
    </a-page-header>

    <a-table
      :columns="columns"
      :data-source="orders"
      :loading="loading"
      row-key="id"
      :pagination="{ pageSize: 10, showTotal: (t) => `共 ${t} 筆` }"
      bordered
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'order_no'">
          <a-typography-text strong>{{ record.order_no }}</a-typography-text>
        </template>
        <template v-else-if="column.dataIndex === 'progress'">
          <div class="relay-mini-track">
            <a-tooltip
              v-for="s in record.stages || []"
              :key="s.id"
              :title="`${s.department_name} · ${s.equipment_type_name} · ${s.status}`"
            >
              <span class="relay-dot" :class="`dot-${s.status}`"></span>
            </a-tooltip>
            <span v-if="!(record.stages || []).length" class="muted">無階段</span>
          </div>
        </template>
        <template v-else-if="column.dataIndex === 'status'">
          <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'is_urgent'">
          <a-tag v-if="record.is_urgent" color="red">緊急</a-tag>
          <span v-else class="muted">—</span>
        </template>
        <template v-else-if="column.dataIndex === '__actions__'">
          <a-button type="link" size="small" @click="viewDetail(record)">
            <template #icon><EyeOutlined /></template>
            檢視
          </a-button>
        </template>
      </template>
    </a-table>

    <a-drawer
      v-model:open="detailOpen"
      :title="selectedOrder ? `訂單詳情:${selectedOrder.order_no}` : ''"
      width="720"
      placement="right"
    >
      <template v-if="selectedOrder">
        <a-card title="接力進度" :bordered="false" size="small" class="detail-card">
          <a-steps
            v-if="(selectedOrder.stages || []).length"
            :current="currentStepIndex"
            size="small"
            :status="overallStepsStatus"
          >
            <a-step
              v-for="(stage, idx) in selectedOrder.stages"
              :key="stage.id"
              :title="`${idx + 1}. ${stage.equipment_type_name}`"
              :status="stepStatus(stage)"
            >
              <template #description>
                <div class="step-desc">
                  <div>{{ stage.department_name }}</div>
                  <a-tag :color="stageStatusColor(stage.status)" style="margin-top: 4px">
                    {{ statusLabel(stage.status) }}
                  </a-tag>
                </div>
              </template>
            </a-step>
          </a-steps>
          <a-empty v-else description="此訂單尚未有階段" />
        </a-card>

        <a-divider />

        <a-descriptions title="一般資訊" bordered :column="2" size="small">
          <a-descriptions-item label="訂單編號" :span="2">
            <code>{{ selectedOrder.order_no }}</code>
          </a-descriptions-item>
          <a-descriptions-item label="實驗">
            {{ selectedOrder.experiment_name }}
          </a-descriptions-item>
          <a-descriptions-item label="Lot ID">
            {{ selectedOrder.lot_id || '—' }}
          </a-descriptions-item>
          <a-descriptions-item label="整體狀態">
            <a-tag :color="statusColor(selectedOrder.status)">
              {{ statusLabel(selectedOrder.status) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="緊急">
            <a-tag v-if="selectedOrder.is_urgent" color="red">緊急</a-tag>
            <span v-else>否</span>
          </a-descriptions-item>
          <a-descriptions-item label="建立時間" :span="2">
            {{ formatDate(selectedOrder.created_at) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-divider />

        <a-descriptions
          v-if="currentStage"
          title="當前作業站"
          bordered
          :column="1"
          size="small"
        >
          <a-descriptions-item label="實驗室">
            {{ currentStage.department_name }}
          </a-descriptions-item>
          <a-descriptions-item label="設備類型">
            {{ currentStage.equipment_type_name }}
          </a-descriptions-item>
          <a-descriptions-item label="執行人員">
            {{ currentStage.assignee_name || '尚未指派' }}
          </a-descriptions-item>
          <a-descriptions-item label="設備代碼">
            {{ currentStage.equipment_code || 'TBD' }}
          </a-descriptions-item>
          <a-descriptions-item v-if="currentStage.schedule_start" label="排程">
            {{ formatDate(currentStage.schedule_start) }}
            →
            {{ formatDate(currentStage.schedule_end) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-alert
          v-if="selectedOrder.rejection_reason"
          type="error"
          show-icon
          :message="`駁回原因:${selectedOrder.rejection_reason}`"
          style="margin-top: 16px"
        />

        <a-divider />

        <div class="remark-block">
          <h4>備註</h4>
          <p v-if="selectedOrder.remark">{{ selectedOrder.remark }}</p>
          <a-empty v-else description="無備註" :image-style="{ height: 40 }" />
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  EyeOutlined,
  FileAddOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { fetchOrder, fetchOrders } from '../../api/orders'

const orders = ref([])
const loading = ref(false)
const detailOpen = ref(false)
const selectedOrder = ref(null)

const columns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: '實驗', dataIndex: 'experiment_name', width: 220 },
  { title: 'Lot ID', dataIndex: 'lot_id', width: 130 },
  { title: '接力進度', dataIndex: 'progress', width: 200 },
  { title: '緊急', dataIndex: 'is_urgent', width: 80 },
  { title: '狀態', dataIndex: 'status', width: 110 },
  { title: '', dataIndex: '__actions__', width: 100, fixed: 'right' },
]

onMounted(loadOrders)

async function loadOrders() {
  loading.value = true
  try {
    const { data } = await fetchOrders()
    orders.value = data.results || data || []
  } catch (e) {
    message.error('載入訂單失敗')
  } finally {
    loading.value = false
  }
}

async function viewDetail(record) {
  try {
    const { data } = await fetchOrder(record.id)
    selectedOrder.value = data
    detailOpen.value = true
  } catch {
    message.error('載入訂單詳情失敗')
  }
}

const currentStage = computed(() => {
  if (!selectedOrder.value?.stages?.length) return null
  return (
    selectedOrder.value.stages.find((s) => s.status !== 'done') ||
    selectedOrder.value.stages[selectedOrder.value.stages.length - 1]
  )
})

const currentStepIndex = computed(() => {
  if (!selectedOrder.value?.stages?.length) return 0
  const idx = selectedOrder.value.stages.findIndex((s) => s.status !== 'done')
  return idx === -1 ? selectedOrder.value.stages.length - 1 : idx
})

const overallStepsStatus = computed(() => {
  if (!selectedOrder.value) return 'process'
  if (selectedOrder.value.status === 'rejected') return 'error'
  if (selectedOrder.value.status === 'done') return 'finish'
  return 'process'
})

function stepStatus(stage) {
  return {
    pending: 'wait', waiting: 'wait',
    in_progress: 'process', done: 'finish', rejected: 'error',
  }[stage.status] || 'wait'
}

function statusLabel(s) {
  return {
    created: '已建立', waiting: '等待中', pending: '待前段',
    in_progress: '進行中', done: '完成', rejected: '駁回',
  }[s] || s
}
function statusColor(s) {
  return {
    created: 'default', waiting: 'warning', pending: 'default',
    in_progress: 'processing', done: 'success', rejected: 'error',
  }[s] || 'default'
}
function stageStatusColor(s) {
  return statusColor(s)
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}
</script>

<style scoped>
.orders-page {
  padding: 0;
}
.relay-mini-track {
  display: flex;
  align-items: center;
  gap: 6px;
}
.relay-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #d9d9d9;
  display: inline-block;
}
.dot-done { background: #52c41a; }
.dot-in_progress {
  background: #1890ff;
  box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.2);
  animation: pulse 1.6s infinite;
}
.dot-waiting { background: #faad14; }
.dot-pending { background: #d9d9d9; }
.dot-rejected { background: #f5222d; }

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}
.muted {
  color: rgba(0, 0, 0, 0.4);
  font-style: italic;
  font-size: 12px;
}
.detail-card :deep(.ant-card-body) {
  padding: 16px 12px;
}
.step-desc {
  font-size: 12px;
  color: rgba(0, 0, 0, 0.55);
}
.remark-block h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
</style>
