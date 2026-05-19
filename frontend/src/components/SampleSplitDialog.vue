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
        <a-input
          v-model:value="row.notes"
          :placeholder="t('split.notesPlaceholder')"
          class="cell-notes"
        />
        <a-button
          type="text"
          danger
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
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons-vue'
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
  { title: t('split.colCount'), dataIndex: 'wafer_count', width: 100 },
  { title: t('split.colNotes'), dataIndex: 'notes', ellipsis: true },
  {
    title: t('split.colCreated'),
    dataIndex: 'created_at',
    width: 160,
    customRender: ({ value }) => (value ? dayjs(value).format('YYYY-MM-DD HH:mm') : '—'),
  },
]

function reset() {
  splits.value = [{ sub_code: '', wafer_count: 1, notes: '' }]
}

function addRow() {
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
.cell-sub-code {
  width: 130px;
  flex-shrink: 0;
}
.cell-wafer-count {
  width: 120px;
  flex-shrink: 0;
}
.cell-notes {
  flex: 1;
  min-width: 180px;
}

@media (max-width: 575px) {
  .cell-sub-code,
  .cell-wafer-count,
  .cell-notes {
    width: 100%;
    flex: 1 1 100%;
  }
}
</style>
