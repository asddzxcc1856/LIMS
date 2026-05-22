<template>
  <CrudTable
    :resource="adminRecipes"
    :resource-label="t('admin.pages.recipes.label')"
    :title="t('admin.pages.recipes.title')"
    :subtitle="t('admin.pages.recipes.subtitle')"
    :search-placeholder="t('admin.pages.recipes.search')"
    default-ordering="name"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag, Tooltip } from 'ant-design-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import { adminRecipes, adminEquipmentTypes } from '../../api/admin'

const { t } = useI18n()

function renderParameters(value) {
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
  { title: t('admin.pages.recipes.colName'), dataIndex: 'name', sorter: true, width: 200 },
  { title: t('admin.pages.recipes.colEquipmentType'), dataIndex: 'equipment_type_name', width: 140 },
  { title: t('admin.pages.recipes.colVersion'), dataIndex: 'version', sorter: true, width: 90 },
  { title: t('admin.pages.recipes.colParameters'), dataIndex: 'parameters',
    customRender: ({ value }) => renderParameters(value) },
  { title: t('admin.pages.recipes.colActive'), dataIndex: 'is_active', width: 110,
    customRender: ({ value }) =>
      h(Tag, { color: value ? 'success' : 'default' },
        () => value ? t('admin.pages.recipes.active') : t('admin.pages.recipes.inactive'),
      ) },
])

// Round-trip parameters as a JSON textarea: object on the API, string in the form.
function stringifyParams(value) {
  if (value == null || value === '') return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return ''
  }
}

function parseParams(value) {
  if (value == null || value === '') return {}
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed) return {}
  return JSON.parse(trimmed)  // surfaces to CrudTable.handleApiError as the form error
}

const formFields = computed(() => [
  { name: 'name', label: t('admin.pages.recipes.fieldName'), type: 'text',
    required: true, placeholder: 'SEM-Standard-100kV', span: 12 },
  { name: 'equipment_type', label: t('orders.equipmentType'), type: 'select',
    required: true, optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'version', label: t('admin.pages.recipes.fieldVersion'), type: 'number',
    required: true, defaultValue: 1, span: 12 },
  { name: 'is_active', label: t('admin.pages.recipes.fieldActive'), type: 'switch',
    defaultValue: true, span: 12 },
  { name: 'parameters', label: t('admin.pages.recipes.fieldParameters'),
    type: 'textarea', placeholder: '{"temp": 250, "time_sec": 600}',
    help: t('admin.pages.recipes.parametersHelp'), span: 24,
    toFormValue: stringifyParams, toApiValue: parseParams },
  { name: 'remark', label: t('admin.pages.recipes.fieldRemark'), type: 'textarea', span: 24 },
])
</script>

<style scoped>
.muted {
  color: var(--c-text-muted);
}
</style>
