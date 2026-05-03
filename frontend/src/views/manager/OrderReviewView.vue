<template>
  <div class="review-page">
    <a-page-header
      title="訂單審核 / 排程"
      sub-title="檢視等待中的階段、排程設備時間、指派執行人員"
      :back-icon="false"
    >
      <template #extra>
        <a-button @click="reloadAll" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          重新整理
        </a-button>
      </template>
    </a-page-header>

    <a-card title="設備時間軸" :bordered="false" class="timeline-wrapper">
      <TimelineChart
        :grouped-equipments="groupedEquipments"
        :bookings="allBookings"
        @booking-click="openEditBooking"
      />
    </a-card>

    <a-card
      title="待審核階段 (Waiting)"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: 0 }"
    >
      <a-table
        :columns="waitingColumns"
        :data-source="waitingStages"
        row-key="id"
        :pagination="false"
        :loading="loading"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'step_order'">
            <a-tag color="blue">Step {{ record.step_order }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === '__actions__'">
            <a-space>
              <a-button type="primary" size="small" @click="openApprove(record)">
                <template #icon><CheckOutlined /></template>
                排程批准
              </a-button>
              <a-button danger size="small" @click="openReject(record)">
                <template #icon><CloseOutlined /></template>
                駁回
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <a-empty
        v-if="!loading && !waitingStages.length"
        description="目前沒有待審核的階段"
        style="padding: 40px 0"
      />
    </a-card>

    <a-card
      title="進行中階段"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: 0 }"
    >
      <a-table
        :columns="activeColumns"
        :data-source="activeStages"
        row-key="id"
        :pagination="false"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'step_order'">
            <a-tag color="blue">Step {{ record.step_order }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'assignee_name'">
            <a-tag v-if="record.assignee_name" color="cyan">
              <UserOutlined />&nbsp;{{ record.assignee_name }}
            </a-tag>
            <span v-else class="muted">尚未指派</span>
          </template>
          <template v-else-if="column.dataIndex === 'schedule'">
            <div class="schedule-cell">
              <div>{{ formatDate(record.schedule_start) }}</div>
              <div class="muted">→ {{ formatDate(record.schedule_end) }}</div>
            </div>
          </template>
          <template v-else-if="column.dataIndex === '__actions__'">
            <a-button type="link" size="small" @click="openReassign(record)">
              <template #icon><EditOutlined /></template>
              重新指派
            </a-button>
          </template>
        </template>
      </a-table>
      <a-empty
        v-if="!loading && !activeStages.length"
        description="目前沒有進行中的階段"
        style="padding: 40px 0"
      />
    </a-card>

    <a-modal
      v-model:open="approveOpen"
      :title="`排程批准:${approveTarget?.equipment_type_name || ''}`"
      :confirm-loading="approveBusy"
      ok-text="確認排程"
      cancel-text="取消"
      @ok="confirmApprove"
    >
      <a-alert
        v-if="approveError"
        type="error"
        :message="approveError"
        show-icon
        style="margin-bottom: 16px"
      />
      <a-alert
        v-if="scheduleWarning"
        type="warning"
        :message="scheduleWarning"
        show-icon
        style="margin-bottom: 16px"
      />
      <a-form layout="vertical">
        <a-form-item label="訂單 / 步驟">
          <a-input
            :value="`${approveTarget?.order_no} · Step ${approveTarget?.step_order}`"
            readonly
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="排程開始" required>
              <a-date-picker
                v-model:value="scheduleStart"
                show-time
                format="YYYY-MM-DD HH:mm"
                style="width: 100%"
                @change="validateSchedule"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="排程結束" required>
              <a-date-picker
                v-model:value="scheduleEnd"
                show-time
                format="YYYY-MM-DD HH:mm"
                style="width: 100%"
                @change="validateSchedule"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="指派執行人員 (可選)">
          <a-select
            v-model:value="assignee"
            placeholder="不指派 (站別)"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="memberOptions"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="rejectOpen"
      :title="`駁回訂單 ${rejectTarget?.order_no || ''}`"
      :ok-button-props="{ danger: true, disabled: !rejectReason.trim() }"
      ok-text="確認駁回"
      cancel-text="取消"
      @ok="confirmReject"
    >
      <a-form layout="vertical">
        <a-form-item label="駁回原因" required>
          <a-textarea
            v-model:value="rejectReason"
            :rows="4"
            placeholder="請說明駁回理由..."
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="reassignOpen"
      :title="`重新指派:${reassignTarget?.order_no || ''}`"
      :confirm-loading="reassignBusy"
      ok-text="儲存變更"
      cancel-text="取消"
      @ok="confirmReassign"
    >
      <a-form layout="vertical">
        <a-form-item label="新執行人員">
          <a-select
            v-model:value="reassignAssignee"
            placeholder="不指派 (站別)"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="memberOptions"
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="調整開始時間">
              <a-date-picker
                v-model:value="reassignStart"
                show-time
                format="YYYY-MM-DD HH:mm"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="調整結束時間">
              <a-date-picker
                v-model:value="reassignEnd"
                show-time
                format="YYYY-MM-DD HH:mm"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="editBookingOpen"
      :title="`調整預約:${editBookingTarget?.order_no || ''}`"
      :confirm-loading="editBookingBusy"
      ok-text="儲存"
      cancel-text="取消"
      @ok="saveBookingUpdate"
    >
      <a-alert
        v-if="editBookingError"
        type="error"
        :message="editBookingError"
        show-icon
        style="margin-bottom: 16px"
      />
      <a-descriptions :column="1" size="small">
        <a-descriptions-item label="設備">
          {{ editBookingTarget?.equipment_code }}
          ({{ editBookingTarget?.equipment_type_name }})
        </a-descriptions-item>
      </a-descriptions>
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item label="開始時間">
          <a-date-picker
            v-model:value="editBookingStart"
            show-time
            format="YYYY-MM-DD HH:mm"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item label="結束時間">
          <a-date-picker
            v-model:value="editBookingEnd"
            show-time
            format="YYYY-MM-DD HH:mm"
            style="width: 100%"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import {
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  ReloadOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { fetchStages, reviewStage } from '../../api/orders'
import { fetchBookings, updateBooking } from '../../api/scheduling'
import client from '../../api/client'
import TimelineChart from '../../components/TimelineChart.vue'

const stages = ref([])
const members = ref([])
const groupedEquipments = ref([])
const allBookings = ref([])
const loading = ref(false)

const waitingStages = computed(() => stages.value.filter((s) => s.status === 'waiting'))
const activeStages = computed(() => stages.value.filter((s) => s.status === 'in_progress'))

const memberOptions = computed(() =>
  members.value.map((u) => ({
    value: u.id,
    label: `${u.username} (${u.role})`,
  })),
)

const waitingColumns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200 },
  { title: '步驟', dataIndex: 'step_order', width: 100 },
  { title: '設備類型', dataIndex: 'equipment_type_name' },
  { title: '申請人', dataIndex: 'user_name', width: 140 },
  { title: 'Lot ID', dataIndex: 'lot_id', width: 120 },
  { title: '', dataIndex: '__actions__', width: 220, fixed: 'right' },
]

const activeColumns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200 },
  { title: '步驟', dataIndex: 'step_order', width: 100 },
  { title: '設備類型', dataIndex: 'equipment_type_name', width: 160 },
  { title: '指派人員', dataIndex: 'assignee_name', width: 160 },
  { title: '排程', dataIndex: 'schedule', width: 240 },
  { title: '', dataIndex: '__actions__', width: 140, fixed: 'right' },
]

// Approve modal state
const approveOpen = ref(false)
const approveTarget = ref(null)
const scheduleStart = ref(null)
const scheduleEnd = ref(null)
const assignee = ref(null)
const approveBusy = ref(false)
const approveError = ref('')
const scheduleWarning = ref('')

// Reject modal state
const rejectOpen = ref(false)
const rejectTarget = ref(null)
const rejectReason = ref('')

// Reassign modal state
const reassignOpen = ref(false)
const reassignTarget = ref(null)
const reassignAssignee = ref(null)
const reassignStart = ref(null)
const reassignEnd = ref(null)
const reassignBusy = ref(false)

// Booking edit modal state
const editBookingOpen = ref(false)
const editBookingTarget = ref(null)
const editBookingStart = ref(null)
const editBookingEnd = ref(null)
const editBookingBusy = ref(false)
const editBookingError = ref('')

onMounted(reloadAll)

async function reloadAll() {
  loading.value = true
  try {
    await Promise.all([loadStages(), loadMembers(), loadTimelineData()])
  } finally {
    loading.value = false
  }
}

async function loadStages() {
  const { data } = await fetchStages()
  stages.value = data.results || data || []
}

async function loadMembers() {
  const { data } = await client.get('/users/')
  members.value = (data.results || data || []).filter((u) =>
    ['lab_member', 'lab_manager'].includes(u.role),
  )
}

async function loadTimelineData() {
  const [resEq, resBk, resProf] = await Promise.all([
    client.get('/equipments/status-matrix/'),
    fetchBookings(),
    client.get('/users/profile/'),
  ])
  const myDept = resProf.data.department_name
  groupedEquipments.value = resEq.data
    .map((type) => ({
      ...type,
      equipments: type.equipments.filter((eq) => eq.department_name === myDept),
    }))
    .filter((type) => type.equipments.length > 0)
  allBookings.value = resBk.data.results || resBk.data || []
}

function openApprove(stage) {
  approveTarget.value = stage
  scheduleStart.value = null
  scheduleEnd.value = null
  assignee.value = null
  approveError.value = ''
  scheduleWarning.value = ''
  approveOpen.value = true
}

function validateSchedule() {
  scheduleWarning.value = ''
  if (scheduleStart.value && scheduleEnd.value) {
    const now = dayjs()
    if (scheduleEnd.value.isBefore(scheduleStart.value)) {
      scheduleWarning.value = '結束時間需晚於開始時間'
    } else if (scheduleStart.value.isBefore(now)) {
      scheduleWarning.value = '開始時間不可在過去'
    }
  }
}

async function confirmApprove() {
  validateSchedule()
  if (scheduleWarning.value) return
  if (!scheduleStart.value || !scheduleEnd.value) {
    approveError.value = '請填寫排程開始與結束時間'
    return
  }
  approveBusy.value = true
  try {
    await reviewStage(approveTarget.value.id, {
      action: 'approve',
      schedule_start: scheduleStart.value.toISOString(),
      schedule_end: scheduleEnd.value.toISOString(),
      assignee: assignee.value,
    })
    approveOpen.value = false
    message.success('排程批准成功')
    await Promise.all([loadStages(), loadTimelineData()])
  } catch (e) {
    approveError.value = e.response?.data?.detail || '批准失敗'
  } finally {
    approveBusy.value = false
  }
}

function openReject(stage) {
  rejectTarget.value = stage
  rejectReason.value = ''
  rejectOpen.value = true
}

async function confirmReject() {
  try {
    await reviewStage(rejectTarget.value.id, {
      action: 'reject',
      rejection_reason: rejectReason.value,
    })
    rejectOpen.value = false
    message.success('已駁回')
    await loadStages()
  } catch (e) {
    message.error(e.response?.data?.detail || '駁回失敗')
  }
}

function openReassign(stage) {
  reassignTarget.value = stage
  reassignAssignee.value = stage.assignee || null
  reassignStart.value = stage.schedule_start ? dayjs(stage.schedule_start) : null
  reassignEnd.value = stage.schedule_end ? dayjs(stage.schedule_end) : null
  reassignOpen.value = true
}

async function confirmReassign() {
  if (reassignStart.value && reassignEnd.value && reassignEnd.value.isBefore(reassignStart.value)) {
    message.error('結束時間需晚於開始時間')
    return
  }
  reassignBusy.value = true
  try {
    await reviewStage(reassignTarget.value.id, {
      action: 'reassign',
      assignee: reassignAssignee.value,
      schedule_start: reassignStart.value?.toISOString(),
      schedule_end: reassignEnd.value?.toISOString(),
    })
    reassignOpen.value = false
    message.success('重新指派成功')
    await Promise.all([loadStages(), loadTimelineData()])
  } catch (e) {
    message.error(e.response?.data?.detail || '重新指派失敗')
  } finally {
    reassignBusy.value = false
  }
}

function openEditBooking(booking) {
  editBookingTarget.value = booking
  editBookingStart.value = booking.start ? dayjs(booking.start) : null
  editBookingEnd.value = booking.end ? dayjs(booking.end) : null
  editBookingError.value = ''
  editBookingOpen.value = true
}

async function saveBookingUpdate() {
  if (!editBookingStart.value || !editBookingEnd.value) {
    editBookingError.value = '請填寫完整時間'
    return
  }
  if (editBookingEnd.value.isBefore(editBookingStart.value)) {
    editBookingError.value = '結束時間需晚於開始時間'
    return
  }
  if (editBookingStart.value.isBefore(dayjs())) {
    editBookingError.value = '開始時間不可在過去'
    return
  }
  editBookingBusy.value = true
  try {
    await updateBooking(editBookingTarget.value.id, {
      started_at: editBookingStart.value.toISOString(),
      ended_at: editBookingEnd.value.toISOString(),
    })
    editBookingOpen.value = false
    message.success('預約已更新')
    await loadTimelineData()
  } catch (e) {
    editBookingError.value = e.response?.data?.detail || '更新失敗'
  } finally {
    editBookingBusy.value = false
  }
}

function formatDate(value) {
  return value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'
}
</script>

<style scoped>
.review-page {
  padding: 0;
}
.timeline-wrapper :deep(.ant-card-body) {
  padding: 16px;
}
.muted {
  color: rgba(0, 0, 0, 0.4);
  font-style: italic;
}
.schedule-cell {
  font-size: 12px;
  line-height: 1.6;
}
</style>
