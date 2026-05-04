<template>
  <CrudTable
    :resource="adminOrderStages"
    :resource-label="t('admin.pages.orderStages.label')"
    :title="t('admin.pages.orderStages.title')"
    :subtitle="t('admin.pages.orderStages.subtitle')"
    :search-placeholder="t('admin.pages.orderStages.search')"
    default-ordering="step_order"
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
  adminOrderStages,
  adminOrders,
  adminUsers,
} from '../../api/admin'

const { t } = useI18n()

const statusOptions = computed(() => [
  { value: 'pending', label: t('stageStatus.pending') },
  { value: 'waiting', label: t('stageStatus.waiting') },
  { value: 'in_progress', label: t('stageStatus.in_progress') },
  { value: 'done', label: t('stageStatus.done') },
  { value: 'rejected', label: t('stageStatus.rejected') },
])
const statusColor = {
  pending: 'default', waiting: 'warning',
  in_progress: 'processing', done: 'success', rejected: 'error',
}

const columns = computed(() => [
  { title: t('orders.orderNo'), dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: t('review.step'), dataIndex: 'step_order', width: 80, sorter: true },
  { title: t('admin.nav.departments'), dataIndex: 'department_name', width: 140 },
  { title: t('orders.equipmentType'), dataIndex: 'equipment_type_name', width: 140 },
  { title: t('orders.equipmentCode'), dataIndex: 'equipment_code', width: 130,
    customRender: ({ value }) => value || '—' },
  { title: t('review.assignee'), dataIndex: 'assignee_username', width: 140,
    customRender: ({ value }) => value || '—' },
  { title: t('orders.status'), dataIndex: 'status', width: 120, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: statusColor[value] || 'default' }, () =>
        statusOptions.value.find((o) => o.value === value)?.label || value,
      ),
  },
  { title: t('orders.statusLabels.done'), dataIndex: 'completed_at', width: 170,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
])

const formFields = computed(() => [
  { name: 'order', label: t('admin.nav.orders'), type: 'select', required: true,
    optionsResource: adminOrders, optionLabel: 'order_no', span: 12 },
  { name: 'step_order', label: t('review.step'), type: 'number', required: true,
    defaultValue: 1, span: 12 },
  { name: 'department', label: t('admin.nav.departments'), type: 'select', required: true,
    optionsResource: adminDepartments, optionLabel: 'name', span: 12 },
  { name: 'equipment_type', label: t('orders.equipmentType'), type: 'select', required: true,
    optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'assignee', label: t('review.assignee'), type: 'select',
    optionsResource: adminUsers, optionLabel: 'username',
    nullableEmpty: true, span: 12 },
  { name: 'equipment', label: t('admin.nav.equipment'), type: 'select',
    optionsResource: adminEquipment, optionLabel: 'code',
    nullableEmpty: true, span: 12 },
  { name: 'status', label: t('orders.status'), type: 'select', required: true,
    options: statusOptions.value, defaultValue: 'pending', span: 12 },
  { name: 'schedule_start', label: t('review.scheduleStart'), type: 'datetime', span: 12 },
  { name: 'schedule_end', label: t('review.scheduleEnd'), type: 'datetime', span: 12 },
  { name: 'completed_at', label: t('orders.statusLabels.done'), type: 'datetime', span: 12 },
])
</script>
