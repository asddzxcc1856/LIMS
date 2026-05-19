<template>
  <div class="orders-page">
    <a-page-header :title="t('orders.title')" :sub-title="t('orders.subtitle')" :back-icon="false">
      <template #extra>
        <a-button @click="loadOrders" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
        <a-button type="primary" @click="$router.push('/orders/create')">
          <template #icon><FileAddOutlined /></template>
          {{ t('nav.createOrder') }}
        </a-button>
      </template>
    </a-page-header>

    <a-table
      :columns="columns"
      :data-source="orders"
      :loading="loading"
      row-key="id"
      :pagination="{ pageSize: 10, showTotal: (n) => t('crud.paginationTotal', { total: n }) }"
      bordered
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'order_no'">
          <a-typography-text strong>{{ record.order_no }}</a-typography-text>
        </template>
        <template v-else-if="column.dataIndex === 'status'">
          <a-tag :color="statusColor(record.status)">{{ statusLabel(record.status) }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'is_urgent'">
          <a-tag v-if="record.is_urgent" color="red">{{ t('orders.urgent') }}</a-tag>
          <span v-else class="muted">—</span>
        </template>
        <template v-else-if="column.dataIndex === '__actions__'">
          <a-button type="link" size="small" @click="viewDetail(record)">
            <template #icon><EyeOutlined /></template>
            {{ t('common.detail') }}
          </a-button>
        </template>
      </template>
    </a-table>

    <a-drawer
      v-model:open="detailOpen"
      :title="selectedOrder ? `${t('orders.detailDrawerTitle')}: ${selectedOrder.order_no}` : ''"
      width="720"
      placement="right"
    >
      <template v-if="selectedOrder">
        <a-descriptions :title="t('orders.generalInfo')" bordered :column="2" size="small">
          <a-descriptions-item :label="t('orders.orderNo')" :span="2">
            <code>{{ selectedOrder.order_no }}</code>
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.experiment')">
            {{ selectedOrder.experiment_name }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.lotId')">
            {{ selectedOrder.lot_id || '—' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.overallStatus')">
            <a-tag :color="statusColor(selectedOrder.status)">
              {{ statusLabel(selectedOrder.status) }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.urgent')">
            <a-tag v-if="selectedOrder.is_urgent" color="red">{{ t('orders.urgent') }}</a-tag>
            <span v-else>{{ t('common.no') }}</span>
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.createdAt')" :span="2">
            {{ formatDate(selectedOrder.created_at) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-divider />

        <a-descriptions
          v-if="currentStage"
          :title="t('orders.currentStation')"
          bordered
          :column="1"
          size="small"
        >
          <a-descriptions-item :label="t('orders.laboratory')">
            {{ currentStage.department_name }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('orders.operator')">
            {{ currentStage.assignee_name || t('common.notAssigned') }}
          </a-descriptions-item>
          <a-descriptions-item v-if="currentStage.schedule_start" :label="t('orders.schedule')">
            {{ formatDate(currentStage.schedule_start) }}
            →
            {{ formatDate(currentStage.schedule_end) }}
          </a-descriptions-item>
        </a-descriptions>

        <a-alert
          v-if="selectedOrder.rejection_reason"
          type="error"
          show-icon
          :message="`${t('orders.rejectReason')}: ${selectedOrder.rejection_reason}`"
          style="margin-top: 16px"
        />

        <a-divider />

        <div class="remark-block">
          <h4>{{ t('orders.requirements') }}</h4>
          <p v-if="selectedOrder.requirements" style="white-space: pre-wrap">{{ selectedOrder.requirements }}</p>
          <a-empty v-else :description="t('orders.noRequirements')" :image-style="{ height: 40 }" />
        </div>

        <a-divider />

        <div class="remark-block">
          <h4>{{ t('orders.remark') }}</h4>
          <p v-if="selectedOrder.remark" style="white-space: pre-wrap">{{ selectedOrder.remark }}</p>
          <a-empty v-else :description="t('orders.noRemark')" :image-style="{ height: 40 }" />
        </div>

        <a-divider />

        <div class="remark-block">
          <h4>{{ t('orders.samples') }}</h4>
          <a-spin :spinning="samplesLoading">
            <a-empty
              v-if="!samplesLoading && samples.length === 0"
              :description="t('orders.noSamples')"
              :image-style="{ height: 40 }"
            />
            <a-table
              v-else
              :columns="sampleColumns"
              :data-source="samples"
              row-key="id"
              size="small"
              :pagination="false"
            />
          </a-spin>
        </div>

        <a-divider />

        <div class="remark-block">
          <h4>{{ t('orders.signoffHistory') }}</h4>
          <a-spin :spinning="approvalsLoading">
            <a-empty
              v-if="!approvalsLoading && approvalRows.length === 0"
              :description="t('orders.noApprovals')"
              :image-style="{ height: 40 }"
            />
            <a-timeline v-else>
              <a-timeline-item
                v-for="row in approvalRows"
                :key="row.id"
                :color="row.decision === 'approved' ? 'green' : 'red'"
              >
                <div class="approval-row">
                  <a-tag :color="row.decision === 'approved' ? 'success' : 'error'">
                    {{ row.decision_display }}
                  </a-tag>
                  <span class="approval-time">{{ formatDate(row.decided_at) }}</span>
                </div>
                <div class="approval-meta">
                  <UserOutlined />&nbsp;{{ row.actor_username || t('orders.signoffSystem') }}
                </div>
                <div v-if="row.comment" class="approval-comment">{{ row.comment }}</div>
              </a-timeline-item>
            </a-timeline>
          </a-spin>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  EyeOutlined,
  FileAddOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import {
  fetchOrder,
  fetchOrders,
  fetchOrderSamples,
  fetchStageApprovals,
} from '../../api/orders'

const { t } = useI18n()

const orders = ref([])
const loading = ref(false)
const detailOpen = ref(false)
const selectedOrder = ref(null)
const approvalRows = ref([])
const approvalsLoading = ref(false)
const samples = ref([])
const samplesLoading = ref(false)

const sampleColumns = computed(() => [
  { title: t('orders.sampleCode'), dataIndex: 'full_code', width: 180 },
  { title: t('orders.sampleCount'), dataIndex: 'wafer_count', width: 100 },
  { title: t('orders.sampleNotes'), dataIndex: 'notes', ellipsis: true },
])

const columns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('orders.experiment'), dataIndex: 'experiment_name', width: 220 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 130 },
  { title: t('orders.urgent'), dataIndex: 'is_urgent', width: 80 },
  { title: t('orders.status'), dataIndex: 'status', width: 110 },
  { title: '', dataIndex: '__actions__', width: 100, fixed: 'right' },
])

onMounted(loadOrders)

async function loadOrders() {
  loading.value = true
  try {
    const { data } = await fetchOrders()
    orders.value = data.results || data || []
  } catch (e) {
    message.error(t('orders.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function viewDetail(record) {
  try {
    const { data } = await fetchOrder(record.id)
    selectedOrder.value = data
    detailOpen.value = true
    await Promise.all([loadApprovals(), loadSamples()])
  } catch {
    message.error(t('orders.loadDetailFailed'))
  }
}

async function loadSamples() {
  if (!selectedOrder.value?.id) {
    samples.value = []
    return
  }
  samplesLoading.value = true
  try {
    const { data } = await fetchOrderSamples(selectedOrder.value.id)
    samples.value = data || []
  } catch {
    samples.value = []
  } finally {
    samplesLoading.value = false
  }
}

async function loadApprovals() {
  // Approvals live on stages, so we aggregate every stage's history into
  // a single timeline ordered by decided_at (newest first).
  const stages = selectedOrder.value?.stages || []
  if (!stages.length) {
    approvalRows.value = []
    return
  }
  approvalsLoading.value = true
  try {
    const results = await Promise.all(
      stages.map((s) =>
        fetchStageApprovals(s.id)
          .then((r) => r.data || [])
          .catch(() => []),
      ),
    )
    approvalRows.value = results
      .flat()
      .sort((a, b) => new Date(b.decided_at) - new Date(a.decided_at))
  } finally {
    approvalsLoading.value = false
  }
}

const currentStage = computed(() => {
  if (!selectedOrder.value?.stages?.length) return null
  return (
    selectedOrder.value.stages.find((s) => s.status !== 'done') ||
    selectedOrder.value.stages[selectedOrder.value.stages.length - 1]
  )
})

function statusLabel(s) {
  return t(`orders.statusLabels.${s}`, s)
}
function statusColor(s) {
  return {
    created: 'default', waiting: 'warning', pending: 'default',
    in_progress: 'processing', done: 'success', rejected: 'error',
  }[s] || 'default'
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}
</script>

<style scoped>
.orders-page {
  padding: 0;
}
.muted {
  color: var(--c-text-muted);
  font-style: italic;
  font-size: 12px;
}
.remark-block h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.approval-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.approval-time {
  font-size: 12px;
  color: var(--c-text-muted);
}
.approval-meta {
  font-size: 12px;
  color: var(--c-text-muted);
  margin-top: 4px;
}
.approval-comment {
  margin-top: 6px;
  font-size: 13px;
  white-space: pre-wrap;
}
</style>
