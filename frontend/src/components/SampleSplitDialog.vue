<template>
  <a-modal
    :open="open"
    :title="t('split.title', { no: order?.order_no || '' })"
    :ok-text="t('split.confirm')"
    :cancel-text="t('common.cancel')"
    :confirm-loading="busy"
    :ok-button-props="{ disabled: !matchesCap }"
    :width="modalWidth"
    @ok="confirm"
    @cancel="emit('update:open', false)"
  >
    <a-alert
      type="info"
      show-icon
      :message="t('split.hint')"
      style="margin-bottom: 12px"
    />
    <a-alert
      :type="overCapacity ? 'error' : 'warning'"
      show-icon
      :message="t('split.capInfo', {
        existing: existingTotal,
        max: MAX_WAFERS_PER_ORDER,
        remaining: remainingCapacity,
        adding: newTotal,
      })"
      style="margin-bottom: 12px"
    />
    <a-spin :spinning="loading">
      <a-table
        :columns="existingColumns"
        :data-source="existingSamples"
        size="small"
        row-key="id"
        :pagination="false"
        :empty-text="t('split.noExisting')"
        style="margin-bottom: 16px"
      />
    </a-spin>

    <a-divider>{{ t('split.newSplits') }}</a-divider>

    <a-form layout="vertical">
      <!-- Column headers shown once above the editable rows so the user
           doesn't have to guess what each cell is for. The icons help
           when the layout collapses on mobile (cells stack). -->
      <div class="split-row split-header">
        <div class="cell-sub-code">
          {{ t('split.labelSubCode') }}
          <a-tooltip :title="t('split.helpSubCode')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="cell-wafer-count">
          {{ t('split.labelWaferCount') }}
          <a-tooltip :title="t('split.helpWaferCount')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="cell-notes">
          {{ t('split.labelNotes') }}
          <a-tooltip :title="t('split.helpNotes')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="cell-remove"></div>
      </div>

      <div
        v-for="(row, idx) in splits"
        :key="idx"
        class="split-row"
      >
        <a-input
          v-model:value="row.sub_code"
          :placeholder="t('split.subCodePlaceholder')"
          class="cell-sub-code"
          allow-clear
        />
        <a-input-number
          v-model:value="row.wafer_count"
          :min="1"
          :max="MAX_WAFERS_PER_ORDER"
          :placeholder="t('split.waferCountPlaceholder')"
          class="cell-wafer-count"
        />
        <a-input
          v-model:value="row.notes"
          :placeholder="t('split.notesPlaceholder')"
          class="cell-notes"
        />
        <a-button
          type="text"
          danger
          class="cell-remove"
          @click="removeRow(idx)"
          :disabled="splits.length === 1"
        >
          <template #icon><MinusCircleOutlined /></template>
        </a-button>
      </div>
      <a-button type="dashed" block @click="addRow">
        <template #icon><PlusOutlined /></template>
        {{ t('split.addRow') }}
      </a-button>
    </a-form>
  </a-modal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  MinusCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { fetchOrderSamples, splitOrderSamples } from '../api/orders'
import { useBreakpoint } from '../composables/useBreakpoint'

const { isMobile } = useBreakpoint()
const modalWidth = computed(() => (isMobile.value ? '95vw' : 640))

const { t } = useI18n()

const props = defineProps({
  open: { type: Boolean, default: false },
  order: { type: Object, default: null },
})
const emit = defineEmits(['update:open', 'split-saved'])

// Hard equality: every order's split must sum to exactly this. Matches
// the backend ``WAFER_COUNT_PER_ORDER`` constant in orders/services.py.
const MAX_WAFERS_PER_ORDER = 25

// Default first row to 25 so the common single-LOT case is one click.
const splits = ref([{ sub_code: 'A', wafer_count: 25, notes: '' }])
const busy = ref(false)
const loading = ref(false)
const existingSamples = ref([])

const existingTotal = computed(() =>
  existingSamples.value.reduce((s, r) => s + (Number(r.wafer_count) || 0), 0),
)
const newTotal = computed(() =>
  splits.value.reduce((s, r) => s + (Number(r.wafer_count) || 0), 0),
)
const remainingCapacity = computed(() =>
  Math.max(0, MAX_WAFERS_PER_ORDER - existingTotal.value),
)
const grandTotal = computed(() => existingTotal.value + newTotal.value)
const matchesCap = computed(() => grandTotal.value === MAX_WAFERS_PER_ORDER)
// Kept name so the existing alert template doesn't need to rewrite.
// "Over capacity" now means "anything other than exactly the cap".
const overCapacity = computed(() => !matchesCap.value)

const existingColumns = [
  { title: t('split.colCode'), dataIndex: 'full_code', width: 180 },
  { title: t('split.colCount'), dataIndex: 'wafer_count', width: 90 },
  { title: t('split.colNotes'), dataIndex: 'notes', ellipsis: true },
  {
    title: t('split.colCreated'),
    dataIndex: 'created_at',
    width: 160,
    customRender: ({ value }) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'),
  },
]

function reset() {
  // Default to one row totalling the cap so the common "no DoE" case
  // is a single click. Multi-row splits override by hand.
  splits.value = [{ sub_code: 'A', wafer_count: MAX_WAFERS_PER_ORDER, notes: '' }]
}

function addRow() {
  // New rows start at 1 wafer so the user has to consciously rebalance
  // — the running total alert turns red until the remainder reaches 0.
  splits.value.push({ sub_code: '', wafer_count: 1, notes: '' })
}

function removeRow(idx) {
  if (splits.value.length === 1) return
  splits.value.splice(idx, 1)
}

async function loadExisting() {
  if (!props.order) return
  loading.value = true
  try {
    const { data } = await fetchOrderSamples(props.order.id)
    existingSamples.value = data || []
  } catch {
    existingSamples.value = []
  } finally {
    loading.value = false
  }
}

async function confirm() {
  if (!props.order) return
  const cleanRows = splits.value
    .map((r) => ({
      sub_code: (r.sub_code || '').trim(),
      wafer_count: Number(r.wafer_count) || 0,
      notes: r.notes || '',
    }))
    .filter((r) => r.sub_code)
  if (!cleanRows.length) {
    message.warning(t('split.needAtLeastOne'))
    return
  }
  const total = existingTotal.value + cleanRows.reduce((s, r) => s + r.wafer_count, 0)
  if (total !== MAX_WAFERS_PER_ORDER) {
    message.error(t('split.capMismatch', { total, max: MAX_WAFERS_PER_ORDER }))
    return
  }
  busy.value = true
  try {
    const { data } = await splitOrderSamples(props.order.id, { splits: cleanRows })
    message.success(t('split.success', { n: data.length }))
    emit('split-saved', data)
    emit('update:open', false)
    reset()
  } catch (e) {
    message.error(e.response?.data?.detail || t('split.failed'))
  } finally {
    busy.value = false
  }
}

watch(
  () => props.open,
  (val) => {
    if (val) {
      reset()
      loadExisting()
    }
  },
)
</script>

<style scoped>
.split-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}
.split-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--c-text-muted);
  border-bottom: 1px dashed var(--c-border);
  padding-bottom: 6px;
  margin-bottom: 8px;
}
.help-icon {
  margin-left: 4px;
  color: var(--c-text-muted);
  cursor: help;
}
.cell-sub-code {
  width: 110px;
  flex-shrink: 0;
}
.cell-wafer-count {
  width: 100px;
  flex-shrink: 0;
}
.cell-notes {
  flex: 1;
  min-width: 160px;
}
.cell-remove {
  width: 36px;
  flex-shrink: 0;
}

@media (max-width: 575px) {
  .cell-sub-code,
  .cell-wafer-count,
  .cell-notes {
    width: 100%;
    flex: 1 1 100%;
  }
  /* Stacked rows on mobile — the header row becomes meaningless and
     wastes vertical space; placeholders inside each input do the job. */
  .split-header {
    display: none;
  }
}
</style>
