<template>
  <div class="review-page">
    <a-page-header
      :title="t('review.title')"
      :sub-title="t('review.subtitle')"
      :back-icon="false"
    >
      <template #extra>
        <a-button @click="reloadAll" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          {{ t('common.refresh') }}
        </a-button>
      </template>
    </a-page-header>

    <a-card :title="t('review.timelineTitle')" :bordered="false" class="timeline-wrapper">
      <TimelineChart
        :grouped-equipments="groupedEquipments"
        :bookings="allBookings"
        @booking-click="openEditBooking"
      />
    </a-card>

    <a-card
      :title="t('review.waitingStagesTitle')"
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
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'requirements'">
            <a-tooltip v-if="record.requirements" :title="record.requirements">
              <span class="requirements-snippet">{{ record.requirements }}</span>
            </a-tooltip>
            <span v-else class="muted">—</span>
          </template>
          <template v-else-if="column.dataIndex === 'is_urgent'">
            <a-tag v-if="record.is_urgent" color="red">{{ t('orders.urgent') }}</a-tag>
            <span v-else class="muted">—</span>
          </template>
          <template v-else-if="column.dataIndex === 'status'">
            <a-tag :color="record.status === 'approved' ? 'cyan' : 'warning'">
              {{ t(`stageStatus.${record.status}`, record.status) }}
            </a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'received_at'">
            <a-tooltip
              v-if="record.received_at"
              :title="t('review.receivedBy', { user: record.received_by_username || '' })"
            >
              <a-tag color="success">
                <CheckOutlined />&nbsp;{{ formatDate(record.received_at) }}
              </a-tag>
            </a-tooltip>
            <a-tag v-else color="warning">{{ t('review.notReceived') }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === '__actions__'">
            <a-space wrap>
              <!-- Manager flow per the new division of labour:
                   only 簽核 + 駁回 are visible. Both auto-hide the row
                   from this queue afterwards because the table is
                   filtered to WAITING — APPROVED stages move to the
                   lab member workbench. -->
              <template v-if="record.status === 'waiting'">
                <a-button type="primary" size="small" @click="openSignoff(record)">
                  <template #icon><SafetyCertificateOutlined /></template>
                  {{ t('review.signoff') }}
                </a-button>
                <a-button danger size="small" @click="openReject(record)">
                  <template #icon><CloseOutlined /></template>
                  {{ t('review.reject') }}
                </a-button>
              </template>
              <a-button type="link" size="small" @click="openApprovalHistory(record)">
                <template #icon><HistoryOutlined /></template>
                {{ t('review.signoffHistory') }}
              </a-button>
            </a-space>
          </template>
        </template>
      </a-table>
      <a-empty
        v-if="!loading && !waitingStages.length"
        :description="t('review.noWaiting')"
        style="padding: 40px 0"
      />
    </a-card>

    <a-card
      :title="t('review.activeStagesTitle')"
      :bordered="false"
      style="margin-top: 16px"
      :body-style="{ padding: 0 }"
    >
      <a-table
        :columns="activeColumns"
        :data-source="activeStages"
        row-key="id"
        :pagination="false"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'equipment_code'">
            <a-tag v-if="record.equipment_code" color="purple">
              {{ record.equipment_code }}
            </a-tag>
            <span v-else class="muted">{{ t('common.notAssigned') }}</span>
          </template>
          <template v-else-if="column.dataIndex === 'assignee_name'">
            <a-tag v-if="record.assignee_name" color="cyan">
              <UserOutlined />&nbsp;{{ record.assignee_name }}
            </a-tag>
            <span v-else class="muted">{{ t('common.notAssigned') }}</span>
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
              {{ t('review.reassign') }}
            </a-button>
          </template>
        </template>
      </a-table>
      <a-empty
        v-if="!loading && !activeStages.length"
        :description="t('review.noActive')"
        style="padding: 40px 0"
      />
    </a-card>

    <a-modal
      v-model:open="approveOpen"
      :title="t('review.approveTitle', { name: approveTarget?.equipment_type_name || '' })"
      :confirm-loading="approveBusy"
      :ok-text="t('review.confirmSchedule')"
      :cancel-text="t('common.cancel')"
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
        <a-form-item :label="t('review.noteOrderStep')">
          <a-input
            :value="`${approveTarget?.order_no} · ${approveTarget?.experiment_name || ''}`"
            readonly
          />
        </a-form-item>
        <a-form-item v-if="approveTarget?.requirements" :label="t('orders.requirements')">
          <a-textarea
            :value="approveTarget.requirements"
            :rows="3"
            readonly
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('review.scheduleStart')" required>
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
            <a-form-item :label="t('review.scheduleEnd')" required>
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
        <a-form-item :label="t('review.assignMachine')">
          <a-select
            v-model:value="approveEquipment"
            :placeholder="t('review.autoPickMachine')"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="machineOptionsForTarget"
            :loading="loadingMachines"
          />
        </a-form-item>
        <a-form-item :label="t('review.assignRecipe')">
          <a-select
            v-model:value="approveRecipe"
            :placeholder="approveEquipment
              ? t('review.recipePickerPlaceholder')
              : t('review.recipePickerDisabled')"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="recipeOptionsForTarget"
            :loading="loadingRecipes"
            :disabled="!approveEquipment"
            @change="syncOverridesWithRecipe"
          />
          <div class="recipe-help">{{ t('review.recipeHelp') }}</div>
        </a-form-item>

        <!-- 參數設定: in-range overrides on the picked recipe's knobs.
             Empty = use the recipe defaults. -->
        <a-form-item
          v-if="selectedRecipeParameters && Object.keys(selectedRecipeParameters).length"
          :label="t('review.paramOverrides')"
        >
          <a-alert
            type="info"
            show-icon
            :message="t('review.paramOverridesHint')"
            style="margin-bottom: 8px"
          />
          <div
            v-for="key in Object.keys(selectedRecipeParameters)"
            :key="key"
            class="override-row"
          >
            <div class="override-label">
              <code>{{ key }}</code>
              <span class="override-default">
                {{ t('review.paramDefault') }}:
                <code>{{ String(selectedRecipeParameters[key]) }}</code>
              </span>
            </div>
            <a-input
              v-model:value="approveParamOverrides[key]"
              :placeholder="String(selectedRecipeParameters[key])"
              allow-clear
              size="small"
            />
          </div>
        </a-form-item>

        <a-form-item :label="t('review.assignTo')">
          <a-select
            v-model:value="assignee"
            :placeholder="t('review.unassigned')"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="memberOptions"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <SampleSplitDialog
      v-model:open="splitOpen"
      :order="splitTarget"
    />

    <a-modal
      v-model:open="signoffOpen"
      :title="t('review.signoffModalTitle', { no: signoffTarget?.order_no || '' })"
      :confirm-loading="signoffBusy"
      :ok-text="t('review.signoffConfirm')"
      :cancel-text="t('common.cancel')"
      @ok="confirmSignoff"
    >
      <a-alert
        type="info"
        show-icon
        :message="t('review.signoffHint')"
        style="margin-bottom: 12px"
      />
      <a-form layout="vertical">
        <a-form-item :label="t('review.signoffComment')">
          <a-textarea
            v-model:value="signoffComment"
            :rows="3"
            :placeholder="t('review.signoffCommentPlaceholder')"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-drawer
      v-model:open="historyDrawerOpen"
      :title="t('review.signoffHistoryTitle', { no: historyDrawerTarget?.order_no || '' })"
      :width="historyDrawerWidth"
      destroy-on-close
    >
      <a-spin :spinning="historyDrawerLoading">
        <a-empty
          v-if="!historyDrawerLoading && historyDrawerRows.length === 0"
          :description="t('review.signoffEmpty')"
        />
        <a-timeline v-else>
          <a-timeline-item
            v-for="row in historyDrawerRows"
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
              <UserOutlined />&nbsp;{{ row.actor_username || t('review.signoffSystem') }}
            </div>
            <div v-if="row.comment" class="approval-comment">{{ row.comment }}</div>
          </a-timeline-item>
        </a-timeline>
      </a-spin>
    </a-drawer>

    <a-modal
      v-model:open="rejectOpen"
      :title="t('review.rejectTitle', { no: rejectTarget?.order_no || '' })"
      :ok-button-props="{ danger: true, disabled: !rejectReason.trim() }"
      :ok-text="t('review.confirmReject')"
      :cancel-text="t('common.cancel')"
      @ok="confirmReject"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('review.rejectReason')" required>
          <a-textarea
            v-model:value="rejectReason"
            :rows="4"
            :placeholder="t('review.rejectReasonPrompt')"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="reassignOpen"
      :title="t('review.reassignTitle', { no: reassignTarget?.order_no || '' })"
      :confirm-loading="reassignBusy"
      :ok-text="t('review.saveChanges')"
      :cancel-text="t('common.cancel')"
      @ok="confirmReassign"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('review.newAssignee')">
          <a-select
            v-model:value="reassignAssignee"
            :placeholder="t('review.unassigned')"
            allow-clear
            show-search
            option-filter-prop="label"
            :options="memberOptions"
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item :label="t('review.adjustStart')">
              <a-date-picker
                v-model:value="reassignStart"
                show-time
                format="YYYY-MM-DD HH:mm"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('review.adjustEnd')">
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
      :title="t('review.bookingTitle', { no: editBookingTarget?.order_no || '' })"
      :confirm-loading="editBookingBusy"
      :ok-text="t('common.save')"
      :cancel-text="t('common.cancel')"
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
        <a-descriptions-item :label="t('review.bookingEquipment')">
          {{ editBookingTarget?.equipment_code }}
          ({{ editBookingTarget?.equipment_type_name }})
        </a-descriptions-item>
      </a-descriptions>
      <a-form layout="vertical" style="margin-top: 16px">
        <a-form-item :label="t('review.startTime')">
          <a-date-picker
            v-model:value="editBookingStart"
            show-time
            format="YYYY-MM-DD HH:mm"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item :label="t('review.endTime')">
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
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'

const { t } = useI18n()
import {
  ApartmentOutlined,
  CheckOutlined,
  CloseOutlined,
  EditOutlined,
  HistoryOutlined,
  InboxOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import SampleSplitDialog from '../../components/SampleSplitDialog.vue'
import {
  fetchStageApprovals,
  fetchStages,
  receiveStage,
  reviewStage,
  signOffStage,
} from '../../api/orders'
import { fetchBookings, updateBooking } from '../../api/scheduling'
import { fetchRecipes } from '../../api/equipments'
import client from '../../api/client'
import TimelineChart from '../../components/TimelineChart.vue'
import { useBreakpoint } from '../../composables/useBreakpoint'
import { useLocalizedLabel } from '../../composables/useLocalizedLabel'

const { isMobile } = useBreakpoint()
const { localized } = useLocalizedLabel()
const historyDrawerWidth = computed(() => (isMobile.value ? '95vw' : 500))

const stages = ref([])
const members = ref([])
const groupedEquipments = ref([])
const allBookings = ref([])
const loading = ref(false)

// Manager queue now ONLY shows WAITING stages — once they sign off the
// stage flips to APPROVED and disappears from this view (the lab member
// workbench takes over from there).
const waitingStages = computed(() =>
  stages.value.filter((s) => s.status === 'waiting'),
)
const activeStages = computed(() => stages.value.filter((s) => s.status === 'in_progress'))

const memberOptions = computed(() =>
  members.value.map((u) => ({
    value: u.id,
    label: `${u.username} (${u.role})`,
  })),
)

const waitingColumns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('orders.status'), dataIndex: 'status', width: 110 },
  { title: t('review.experiment'), dataIndex: 'experiment_name', width: 200 },
  { title: t('orders.requirements'), dataIndex: 'requirements', ellipsis: true },
  { title: t('review.requester'), dataIndex: 'user_name', width: 140 },
  { title: t('orders.lotId'), dataIndex: 'lot_id', width: 120 },
  { title: t('orders.urgent'), dataIndex: 'is_urgent', width: 80 },
  { title: t('review.received'), dataIndex: 'received_at', width: 140 },
  { title: '', dataIndex: '__actions__', width: 320, fixed: 'right' },
])

const activeColumns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200 },
  { title: t('review.experiment'), dataIndex: 'experiment_name' },
  { title: t('review.machine'), dataIndex: 'equipment_code', width: 140 },
  { title: t('review.assignee'), dataIndex: 'assignee_name', width: 160 },
  { title: t('orders.schedule'), dataIndex: 'schedule', width: 240 },
  { title: '', dataIndex: '__actions__', width: 140, fixed: 'right' },
])

// Approve modal state
const approveOpen = ref(false)
const approveTarget = ref(null)
const scheduleStart = ref(null)
const scheduleEnd = ref(null)
const assignee = ref(null)
const approveEquipment = ref(null)
const approveRecipe = ref(null)
const approveParamOverrides = ref({})
const approveBusy = ref(false)
const approveError = ref('')
const scheduleWarning = ref('')
const labMachines = ref([])
const loadingMachines = ref(false)
const labRecipes = ref([])
const loadingRecipes = ref(false)

// Resolve the parameter dict of the currently-picked recipe so the
// override editor can render one input per knob. Re-syncs whenever the
// recipe pick changes (see syncOverridesWithRecipe).
const selectedRecipeParameters = computed(() => {
  if (!approveRecipe.value) return {}
  const recipe = labRecipes.value.find((r) => r.id === approveRecipe.value)
  return recipe?.parameters || {}
})

function syncOverridesWithRecipe() {
  // Clear stale overrides when the manager re-picks a recipe — the old
  // keys may not exist on the new one and the backend would reject the
  // request anyway.
  approveParamOverrides.value = {}
}

const machineOptionsForTarget = computed(() =>
  // Experiments don't pre-define equipment types anymore, so the picker
  // shows every unit in the manager's lab. Disabled options keep occupied
  // / maintenance machines visible (so the manager knows they exist) but
  // unselectable.
  labMachines.value.map((eq) => ({
    value: eq.id,
    label: `${eq.code} · ${eq.type_name || ''} · ${eq.status}`,
    disabled: eq.status !== 'available',
  })),
)

// Resolve the equipment_type for the currently picked machine so the recipe
// dropdown can scope to matching recipes. When no machine is picked the
// recipe dropdown is locked.
const selectedEquipmentTypeId = computed(() => {
  if (!approveEquipment.value) return null
  const eq = labMachines.value.find((e) => e.id === approveEquipment.value)
  return eq?.equipment_type ?? null
})

const recipeOptionsForTarget = computed(() => {
  const typeId = selectedEquipmentTypeId.value
  if (!typeId) return []
  return labRecipes.value
    .filter((r) => r.equipment_type === typeId && r.is_active)
    .map((r) => ({
      value: r.id,
      label: `${localized(r)} v${r.version}`,
    }))
})

// Signoff (簽核 only) modal state
const signoffOpen = ref(false)
const signoffTarget = ref(null)
const signoffComment = ref('')
const signoffBusy = ref(false)

// Sign-off history drawer state — lazily loads /stages/<id>/approvals/
const historyDrawerOpen = ref(false)
const historyDrawerTarget = ref(null)
const historyDrawerRows = ref([])
const historyDrawerLoading = ref(false)

// Split (分貨) dialog state
const splitOpen = ref(false)
const splitTarget = ref(null)

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

// When the manager re-picks a machine, drop the recipe — the old pick
// might be a different equipment_type and the backend would reject it
// anyway. Better to clear and force a deliberate re-pick.
watch(approveEquipment, () => {
  approveRecipe.value = null
})

async function reloadAll() {
  loading.value = true
  try {
    // Promise.allSettled (not .all) so a 403/500 from any single endpoint
    // — most commonly /equipments/status-matrix/ when a manager has no
    // matching dept — doesn't blank out the stages table that already
    // loaded successfully. Each loader does its own try/catch internally.
    await Promise.allSettled([
      loadStages(), loadMembers(), loadTimelineData(), loadMachines(), loadRecipes(),
    ])
  } finally {
    loading.value = false
  }
}

async function loadMachines() {
  loadingMachines.value = true
  try {
    const { data } = await client.get('/equipments/')
    labMachines.value = data.results || data || []
  } catch {
    labMachines.value = []
  } finally {
    loadingMachines.value = false
  }
}

async function loadRecipes() {
  loadingRecipes.value = true
  try {
    const { data } = await fetchRecipes({ is_active: true })
    labRecipes.value = data.results || data || []
  } catch {
    labRecipes.value = []
  } finally {
    loadingRecipes.value = false
  }
}

async function loadStages() {
  try {
    const { data } = await fetchStages()
    stages.value = data.results || data || []
  } catch (e) {
    // Surface the failure clearly instead of leaving the table silently
    // empty — most commonly this means token expired or backend 500.
    message.error(e.response?.data?.detail || t('orders.loadFailed'))
    stages.value = []
  }
}

async function loadMembers() {
  try {
    const { data } = await client.get('/users/')
    members.value = (data.results || data || []).filter((u) =>
      ['lab_member', 'lab_manager'].includes(u.role),
    )
  } catch {
    members.value = []   // fall back to empty assignee dropdown
  }
}

async function loadTimelineData() {
  try {
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
  } catch {
    groupedEquipments.value = []
    allBookings.value = []
  }
}

function openApprove(stage) {
  approveTarget.value = stage
  scheduleStart.value = null
  scheduleEnd.value = null
  assignee.value = null
  approveEquipment.value = null
  approveRecipe.value = null
  approveParamOverrides.value = {}
  approveError.value = ''
  scheduleWarning.value = ''
  approveOpen.value = true
}

function validateSchedule() {
  scheduleWarning.value = ''
  if (scheduleStart.value && scheduleEnd.value) {
    const now = dayjs()
    if (scheduleEnd.value.isBefore(scheduleStart.value)) {
      scheduleWarning.value = t('review.endAfterStart')
    } else if (scheduleStart.value.isBefore(now)) {
      scheduleWarning.value = t('review.noPastStart')
    }
  }
}

async function confirmApprove() {
  validateSchedule()
  if (scheduleWarning.value) return
  if (!scheduleStart.value || !scheduleEnd.value) {
    approveError.value = t('review.fillTimes')
    return
  }
  approveBusy.value = true
  try {
    // Drop empty-string overrides so the backend only stores knobs that
    // the operator actually touched. Strings get sent as-is — recipe
    // parameter values are JSON-encoded so a numeric default rendered
    // here as "250" gets stored as "250" (string). Keep it simple; let
    // the backend coerce if needed.
    const cleanedOverrides = Object.fromEntries(
      Object.entries(approveParamOverrides.value)
        .filter(([, v]) => v !== '' && v != null),
    )
    await reviewStage(approveTarget.value.id, {
      action: 'approve',
      schedule_start: scheduleStart.value.toISOString(),
      schedule_end: scheduleEnd.value.toISOString(),
      assignee: assignee.value,
      equipment: approveEquipment.value,
      recipe: approveRecipe.value,
      parameter_overrides: cleanedOverrides,
    })
    approveOpen.value = false
    message.success(t('review.approveSuccess'))
    await Promise.all([loadStages(), loadTimelineData(), loadMachines()])
  } catch (e) {
    approveError.value = e.response?.data?.detail || t('review.approveFailed')
  } finally {
    approveBusy.value = false
  }
}

function openSplit(stage) {
  // The dialog needs an Order-shaped object; the stage row carries
  // order_no but not the order id — pull it from the stage's parent FK.
  splitTarget.value = { id: stage.order || stage.order_id, order_no: stage.order_no }
  splitOpen.value = true
}

async function handleReceive(stage) {
  try {
    await receiveStage(stage.id)
    message.success(t('review.receiveSuccess', { no: stage.order_no }))
    await loadStages()
  } catch (e) {
    message.error(e.response?.data?.detail || t('review.receiveFailed'))
  }
}

function openSignoff(stage) {
  signoffTarget.value = stage
  signoffComment.value = ''
  signoffOpen.value = true
}

async function confirmSignoff() {
  if (!signoffTarget.value) return
  signoffBusy.value = true
  try {
    await signOffStage(signoffTarget.value.id, {
      decision: 'approved',
      comment: signoffComment.value,
    })
    signoffOpen.value = false
    message.success(t('review.signoffSuccess'))
    if (
      historyDrawerOpen.value
      && historyDrawerTarget.value?.id === signoffTarget.value.id
    ) {
      await refreshSignoffHistory()
    }
  } catch (e) {
    message.error(e.response?.data?.detail || t('review.signoffFailed'))
  } finally {
    signoffBusy.value = false
  }
}

function openApprovalHistory(stage) {
  historyDrawerTarget.value = stage
  historyDrawerOpen.value = true
  refreshSignoffHistory()
}

async function refreshSignoffHistory() {
  if (!historyDrawerTarget.value) return
  historyDrawerLoading.value = true
  try {
    const { data } = await fetchStageApprovals(historyDrawerTarget.value.id)
    historyDrawerRows.value = data || []
  } catch {
    historyDrawerRows.value = []
  } finally {
    historyDrawerLoading.value = false
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
    message.success(t('review.rejectSuccess'))
    await loadStages()
  } catch (e) {
    message.error(e.response?.data?.detail || t('review.rejectFailed'))
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
    message.error(t('review.endAfterStart'))
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
    message.success(t('review.reassignSuccess'))
    await Promise.all([loadStages(), loadTimelineData()])
  } catch (e) {
    message.error(e.response?.data?.detail || t('review.reassignFailed'))
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
    editBookingError.value = t('review.fillBookingTimes')
    return
  }
  if (editBookingEnd.value.isBefore(editBookingStart.value)) {
    editBookingError.value = t('review.endAfterStart')
    return
  }
  if (editBookingStart.value.isBefore(dayjs())) {
    editBookingError.value = t('review.noPastStart')
    return
  }
  editBookingBusy.value = true
  try {
    await updateBooking(editBookingTarget.value.id, {
      started_at: editBookingStart.value.toISOString(),
      ended_at: editBookingEnd.value.toISOString(),
    })
    editBookingOpen.value = false
    message.success(t('review.bookingSuccess'))
    await loadTimelineData()
  } catch (e) {
    editBookingError.value = e.response?.data?.detail || t('review.bookingFailed')
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
  color: var(--c-text-muted);
  font-style: italic;
}
.schedule-cell {
  font-size: 12px;
  line-height: 1.6;
}
.override-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}
.override-label {
  flex: 1;
  font-size: 12px;
}
.override-default {
  margin-left: 8px;
  color: var(--c-text-muted);
}
.override-row :deep(.ant-input) {
  max-width: 200px;
}
.recipe-help {
  color: var(--c-text-muted);
  font-size: 12px;
  line-height: 1.4;
  margin-top: 4px;
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
.requirements-snippet {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.5;
}
</style>
