<template>
  <CrudTable
    :resource="adminOrderStages"
    resource-label="訂單階段"
    title="訂單階段"
    subtitle="接力流程的個別階段,每筆訂單依步驟順序執行"
    search-placeholder="依訂單編號搜尋"
    default-ordering="step_order"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import { h } from 'vue'
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

const statusOptions = [
  { value: 'pending', label: '待前段' },
  { value: 'waiting', label: '待指派' },
  { value: 'in_progress', label: '進行中' },
  { value: 'done', label: '完成' },
  { value: 'rejected', label: '駁回' },
]
const statusColor = {
  pending: 'default', waiting: 'warning',
  in_progress: 'processing', done: 'success', rejected: 'error',
}

const columns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: '步驟', dataIndex: 'step_order', width: 80, sorter: true },
  { title: '部門', dataIndex: 'department_name', width: 140 },
  { title: '設備類型', dataIndex: 'equipment_type_name', width: 140 },
  { title: '已派設備', dataIndex: 'equipment_code', width: 130,
    customRender: ({ value }) => value || '—' },
  { title: '指派給', dataIndex: 'assignee_username', width: 140,
    customRender: ({ value }) => value || '—' },
  { title: '狀態', dataIndex: 'status', width: 120, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: statusColor[value] || 'default' }, () =>
        statusOptions.find((o) => o.value === value)?.label || value,
      ),
  },
  { title: '完成時間', dataIndex: 'completed_at', width: 170,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
]

const formFields = [
  { name: 'order', label: '訂單', type: 'select', required: true,
    optionsResource: adminOrders, optionLabel: 'order_no', span: 12 },
  { name: 'step_order', label: '步驟順序', type: 'number', required: true,
    defaultValue: 1, span: 12 },
  { name: 'department', label: '執行部門', type: 'select', required: true,
    optionsResource: adminDepartments, optionLabel: 'name', span: 12 },
  { name: 'equipment_type', label: '設備類型', type: 'select', required: true,
    optionsResource: adminEquipmentTypes, optionLabel: 'name', span: 12 },
  { name: 'assignee', label: '指派給', type: 'select',
    optionsResource: adminUsers, optionLabel: 'username',
    nullableEmpty: true, span: 12 },
  { name: 'equipment', label: '指派設備', type: 'select',
    optionsResource: adminEquipment, optionLabel: 'code',
    nullableEmpty: true, span: 12 },
  { name: 'status', label: '狀態', type: 'select', required: true,
    options: statusOptions, defaultValue: 'pending', span: 12 },
  { name: 'schedule_start', label: '排程開始', type: 'datetime', span: 12 },
  { name: 'schedule_end', label: '排程結束', type: 'datetime', span: 12 },
  { name: 'completed_at', label: '完成時間', type: 'datetime', span: 12 },
]
</script>
