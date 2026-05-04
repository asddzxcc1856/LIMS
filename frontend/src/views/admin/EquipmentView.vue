<template>
  <CrudTable
    :resource="adminEquipment"
    :resource-label="t('admin.pages.equipment.label')"
    :title="t('admin.pages.equipment.title')"
    :subtitle="t('admin.pages.equipment.subtitle')"
    :search-placeholder="t('admin.pages.equipment.search')"
    default-ordering="code"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tag } from 'ant-design-vue'
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminDepartments,
  adminEquipment,
  adminEquipmentTypes,
} from '../../api/admin'

const { t } = useI18n()

const statusOptions = computed(() => [
  { value: 'available', label: t('equipmentStatus.available') },
  { value: 'occupied', label: t('equipmentStatus.occupied') },
  { value: 'pending', label: t('equipmentStatus.pending') },
  { value: 'maintenance', label: t('equipmentStatus.maintenance') },
  { value: 'inactive', label: t('equipmentStatus.inactive') },
])
const statusColor = {
  available: 'success', occupied: 'warning',
  pending: 'default', maintenance: 'error', inactive: 'default',
}

const columns = computed(() => [
  { title: t('orders.equipmentCode'), dataIndex: 'code', sorter: true, width: 160 },
  { title: t('orders.equipmentType'), dataIndex: 'equipment_type_name', width: 160 },
  { title: t('admin.nav.departments'), dataIndex: 'department_name', width: 160,
    customRender: ({ value }) => value || '—' },
  { title: t('orders.status'), dataIndex: 'status', width: 120, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: statusColor[value] || 'default' }, () =>
        statusOptions.value.find((o) => o.value === value)?.label || value,
      ),
  },
])

const formFields = computed(() => [
  { name: 'equipment_type', label: t('orders.equipmentType'), type: 'select', required: true,
    optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'department', label: t('admin.nav.departments'), type: 'select', required: true,
    optionsResource: adminDepartments, optionLabel: 'name', span: 12 },
  { name: 'code', label: t('orders.equipmentCode'), type: 'text', required: true,
    placeholder: 'SEM-001', span: 12 },
  { name: 'status', label: t('orders.status'), type: 'select', required: true,
    options: statusOptions.value, defaultValue: 'available', span: 12 },
])
</script>
