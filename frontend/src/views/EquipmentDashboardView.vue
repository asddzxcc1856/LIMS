<template>
  <div class="eq-page">
    <a-page-header
      title="設備總覽"
      sub-title="即時呈現所有設備的當前狀態與占用訂單"
      :back-icon="false"
    >
      <template #extra>
        <a-radio-group v-model:value="filter" button-style="solid">
          <a-radio-button value="all">全部</a-radio-button>
          <a-radio-button value="available">可用</a-radio-button>
          <a-radio-button value="occupied">占用中</a-radio-button>
          <a-radio-button value="maintenance">維修</a-radio-button>
        </a-radio-group>
        <a-button @click="load" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          重新整理
        </a-button>
      </template>
    </a-page-header>

    <div class="legend">
      <a-tag color="success">
        <CheckCircleOutlined />&nbsp;可用 ({{ countByStatus.available || 0 }})
      </a-tag>
      <a-tag color="processing">
        <SyncOutlined :spin="true" />&nbsp;占用中 ({{ countByStatus.occupied || 0 }})
      </a-tag>
      <a-tag color="error">
        <WarningOutlined />&nbsp;維修 ({{ countByStatus.maintenance || 0 }})
      </a-tag>
      <a-tag color="default">
        <PauseCircleOutlined />&nbsp;停用 ({{ countByStatus.inactive || 0 }})
      </a-tag>
    </div>

    <a-skeleton :loading="loading && !matrix.length" active>
      <a-row :gutter="[16, 16]">
        <a-col
          v-for="group in filteredMatrix"
          :key="group.type_id"
          :xs="24"
          :sm="12"
          :md="8"
          :xl="6"
        >
          <a-card :title="group.type_name" :bordered="false" hoverable>
            <template #extra>
              <a-tag>{{ group.equipments.length }}</a-tag>
            </template>
            <div class="eq-list">
              <div
                v-for="eq in group.equipments"
                :key="eq.id"
                class="eq-row"
                :class="`status-${eq.status}`"
                :style="{ cursor: eq.active_order ? 'pointer' : 'default' }"
                @click="eq.active_order ? showOrder(eq) : null"
              >
                <span class="eq-dot"></span>
                <div class="eq-meta">
                  <div class="eq-code">{{ eq.code }}</div>
                  <div class="eq-dept">{{ eq.department_name || '—' }}</div>
                </div>
                <a-tag :color="statusColor(eq.status)">
                  {{ statusLabel(eq.status) }}
                </a-tag>
                <a-tag v-if="eq.active_order" color="blue" class="order-tag">
                  {{ eq.active_order.order_no }}
                </a-tag>
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>
    </a-skeleton>

    <a-empty
      v-if="!loading && !filteredMatrix.length"
      description="沒有符合篩選的設備"
      style="margin: 60px 0"
    />

    <a-modal
      v-model:open="modalOpen"
      :title="`${selectedEq?.code || ''} — 當前訂單`"
      :footer="null"
      width="480"
    >
      <template v-if="selectedEq?.active_order">
        <a-descriptions :column="1" bordered size="small">
          <a-descriptions-item label="訂單編號">
            <a-typography-text strong>
              {{ selectedEq.active_order.order_no }}
            </a-typography-text>
          </a-descriptions-item>
          <a-descriptions-item label="開始時間">
            {{ formatDate(selectedEq.active_order.started_at) }}
          </a-descriptions-item>
          <a-descriptions-item label="結束時間">
            {{ formatDate(selectedEq.active_order.ended_at) }}
          </a-descriptions-item>
        </a-descriptions>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import {
  CheckCircleOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import { fetchStatusMatrix } from '../api/equipments'

const matrix = ref([])
const loading = ref(false)
const filter = ref('all')
const modalOpen = ref(false)
const selectedEq = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await fetchStatusMatrix()
    matrix.value = data || []
  } finally {
    loading.value = false
  }
}

const countByStatus = computed(() => {
  const counts = {}
  for (const group of matrix.value) {
    for (const eq of group.equipments) {
      counts[eq.status] = (counts[eq.status] || 0) + 1
    }
  }
  return counts
})

const filteredMatrix = computed(() => {
  if (filter.value === 'all') return matrix.value
  return matrix.value
    .map((group) => ({
      ...group,
      equipments: group.equipments.filter((eq) => eq.status === filter.value),
    }))
    .filter((group) => group.equipments.length > 0)
})

function showOrder(eq) {
  selectedEq.value = eq
  modalOpen.value = true
}

function statusLabel(s) {
  return {
    available: '可用', occupied: '占用中',
    maintenance: '維修', inactive: '停用', pending: '待處理',
  }[s] || s
}
function statusColor(s) {
  return {
    available: 'success', occupied: 'processing',
    maintenance: 'error', inactive: 'default', pending: 'default',
  }[s] || 'default'
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}
</script>

<style scoped>
.eq-page {
  padding: 0;
}
.legend {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.legend .ant-tag {
  font-size: 13px;
  padding: 4px 12px;
}
.eq-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.eq-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #fafafa;
  border: 1px solid #f0f0f0;
  transition: all 0.15s ease;
}
.eq-row:hover {
  background: #f0f5ff;
  border-color: #91caff;
  transform: translateX(2px);
}
.eq-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-available .eq-dot { background: #52c41a; box-shadow: 0 0 0 3px rgba(82, 196, 26, 0.15); }
.status-occupied .eq-dot { background: #1890ff; box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.15); animation: pulse 1.6s infinite; }
.status-maintenance .eq-dot { background: #f5222d; }
.status-inactive .eq-dot { background: #bfbfbf; }
.status-pending .eq-dot { background: #faad14; }

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

.eq-meta {
  flex: 1;
  min-width: 0;
}
.eq-code {
  font-weight: 600;
  font-size: 13px;
}
.eq-dept {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.45);
}
.order-tag {
  margin-right: 0 !important;
}
</style>
