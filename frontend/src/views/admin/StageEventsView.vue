<template>
  <CrudTable
    :resource="adminStageEvents"
    :resource-label="t('admin.pages.stageEvents.label')"
    :title="t('admin.pages.stageEvents.title')"
    :subtitle="t('admin.pages.stageEvents.subtitle')"
    :search-placeholder="t('admin.pages.stageEvents.search')"
    default-ordering="-occurred_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag, Tooltip } from 'ant-design-vue'
import dayjs from 'dayjs'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminStageEvents } from '../../api/admin'

const { t } = useI18n()

const eventTypeColor = {
  receive: 'cyan',
  load: 'blue',
  unload: 'green',
  abort: 'red',
  note: 'default',
}

function renderMeasurement(value) {
  if (!value || (typeof value === 'object' && Object.keys(value).length === 0)) {
    return h('span', { class: 'muted' }, '—')
  }
  const text = JSON.stringify(value)
  const short = text.length > 48 ? `${text.slice(0, 45)}…` : text
  return h(Tooltip, { title: text }, () =>
    h('code', { style: 'font-size: 12px' }, short),
  )
}

const columns = computed(() => [
  { title: t('admin.pages.stageEvents.colTime'), dataIndex: 'occurred_at', width: 170,
    sorter: true, customRender: ({ value }) =>
      value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' },
  { title: t('admin.pages.stageEvents.colType'), dataIndex: 'event_type', width: 100,
    customRender: ({ value, record }) =>
      h(Tag, { color: eventTypeColor[value] || 'default' }, () => record.event_type_display) },
  { title: t('admin.pages.stageEvents.colOrder'), dataIndex: 'stage_order_no', width: 220 },
  { title: t('admin.pages.stageEvents.colEquipment'), dataIndex: 'equipment_code', width: 140 },
  { title: t('admin.pages.stageEvents.colRecipe'), dataIndex: 'recipe_name', width: 140 },
  { title: t('admin.pages.stageEvents.colOperator'), dataIndex: 'operator_username', width: 140 },
  { title: t('admin.pages.stageEvents.colMeasurement'), dataIndex: 'measurement',
    customRender: ({ value }) => renderMeasurement(value) },
])

// Stage events are append-only in real workflows. Admin can still create
// rows manually for backfill / data correction, so the form exposes the
// minimal editable fields.
const formFields = computed(() => [
  { name: 'stage', label: t('admin.pages.stageEvents.fieldStage'),
    type: 'text', required: true,
    help: t('admin.pages.stageEvents.fieldStageHelp') },
  { name: 'event_type', label: t('admin.pages.stageEvents.fieldEventType'),
    type: 'select', required: true, defaultValue: 'note',
    options: [
      { value: 'receive', label: t('tasks.eventType.receive') },
      { value: 'load', label: t('tasks.eventType.load') },
      { value: 'unload', label: t('tasks.eventType.unload') },
      { value: 'abort', label: t('tasks.eventType.abort') },
      { value: 'note', label: t('tasks.eventType.note') },
    ] },
  { name: 'notes', label: t('admin.pages.stageEvents.fieldNotes'), type: 'textarea',
    span: 24 },
])
</script>

<style scoped>
.muted { color: var(--c-text-muted); }
</style>
