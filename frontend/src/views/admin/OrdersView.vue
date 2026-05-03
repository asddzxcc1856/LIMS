<template>
  <CrudTable
    :resource="adminOrders"
    resource-label="訂單"
    title="訂單"
    subtitle="檢視與微調所有送樣訂單。直接改 status 會略過業務邏輯,謹慎使用"
    search-placeholder="依訂單編號 / lot / 申請人 / 實驗搜尋"
    default-ordering="-created_at"
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
  adminExperiments,
  adminOrders,
  adminUsers,
} from '../../api/admin'

const statusOptions = [
  { value: 'created', label: '已建立' },
  { value: 'waiting', label: '等待中' },
  { value: 'in_progress', label: '進行中' },
  { value: 'done', label: '完成' },
  { value: 'rejected', label: '駁回' },
]
const statusColor = {
  created: 'default', waiting: 'warning',
  in_progress: 'processing', done: 'success', rejected: 'error',
}

const columns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: '實驗', dataIndex: 'experiment_name', width: 180 },
  { title: '申請人', dataIndex: 'requester_username', width: 140 },
  { title: '部門', dataIndex: 'department_name', width: 140 },
  { title: 'Lot ID', dataIndex: 'lot_id', width: 120 },
  { title: '狀態', dataIndex: 'status', width: 120, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: statusColor[value] || 'default' }, () =>
        statusOptions.find((o) => o.value === value)?.label || value,
      ),
  },
  { title: '緊急', dataIndex: 'is_urgent', width: 80, sorter: true,
    customRender: ({ value }) =>
      h(Tag, { color: value ? 'red' : 'default' }, () => (value ? '緊急' : '一般')),
  },
  { title: '指派給', dataIndex: 'assignee_username', width: 140,
    customRender: ({ value }) => value || '—' },
  { title: '建立時間', dataIndex: 'created_at', width: 170, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
  { title: '階段數', dataIndex: 'stage_count', width: 90 },
]

const formFields = [
  { name: 'department', label: '部門', type: 'select', required: true,
    optionsResource: adminDepartments, optionLabel: 'name', span: 12 },
  { name: 'experiment', label: '實驗', type: 'select', required: true,
    optionsResource: adminExperiments, optionLabel: 'name', span: 12 },
  { name: 'user', label: '申請人', type: 'select', required: true,
    optionsResource: adminUsers, optionLabel: 'username', span: 12 },
  { name: 'assignee', label: '指派給', type: 'select',
    optionsResource: adminUsers, optionLabel: 'username',
    nullableEmpty: true, span: 12 },
  { name: 'lot_id', label: 'Lot ID', type: 'text',
    placeholder: '晶圓批號', span: 12 },
  { name: 'status', label: '狀態', type: 'select', required: true,
    options: statusOptions, defaultValue: 'waiting', span: 12 },
  { name: 'is_urgent', label: '緊急', type: 'switch', span: 12 },
  { name: 'schedule_start', label: '排程開始', type: 'datetime', span: 12 },
  { name: 'schedule_end', label: '排程結束', type: 'datetime', span: 12 },
  { name: 'rejection_reason', label: '駁回原因', type: 'textarea',
    help: '僅在狀態為「駁回」時填寫' },
  { name: 'remark', label: '備註', type: 'textarea' },
]
</script>
