<template>
  <a-modal
    :open="open"
    :title="t('split.title', { no: order?.order_no || '' })"
    :ok-text="t('split.confirm')"
    :cancel-text="t('common.cancel')"
    :confirm-loading="busy"
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
        <div class="cell-exec-order">
          {{ t('split.labelExecOrder') }}
          <a-tooltip :title="t('split.helpExecOrder')">
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
          :placeholder="t('split.waferCountPlaceholder')"
          class="cell-wafer-count"
        />
        <a-input-number
          v-model:value="row.execution_order"
          :min="0"
          :placeholder="t('split.execOrderPlaceholder')"
          class="cell-exec-order"
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

const splits = ref([{ sub_code: '', wafer_count: 1, notes: '' }])
const busy = ref(false)
const loading = ref(false)
const existingSamples = ref([])

const existingColumns = [
  { title: t('split.colCode'), dataIndex: 'full_code', width: 180 },
  { title: t('split.colCount'), dataIndex: 'wafer_count', width: 90 },
  { title: t('split.colOrder'), dataIndex: 'execution_order', width: 90 },
  { title: t('split.colNotes'), dataIndex: 'notes', ellipsis: true },
  {
    title: t('split.colCreated'),
    dataIndex: 'created_at',
    width: 160,
    customRender: ({ value }) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'),
  },
]

function reset() {
  splits.value = [{ sub_code: '', wafer_count: 1, execution_order: 0, notes: '' }]
}

function addRow() {
  splits.value.push({ sub_code: '', wafer_count: 1, execution_order: 0, notes: '' })
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
      execution_order: Number(r.execution_order) || 0,
      notes: r.notes || '',
    }))
    .filter((r) => r.sub_code)
  if (!cleanRows.length) {
    message.warning(t('split.needAtLeastOne'))
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
.cell-exec-order {
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
  .cell-exec-order,
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
