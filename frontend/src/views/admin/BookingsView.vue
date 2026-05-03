<template>
  <CrudTable
    :resource="adminBookings"
    resource-label="設備預約"
    title="設備預約"
    subtitle="個別設備在指定時段的占用紀錄"
    search-placeholder="依訂單編號或設備代碼搜尋"
    default-ordering="-started_at"
    :columns="columns"
    :form-fields="formFields"
  />
</template>

<script setup>
import CrudTable from '../../components/admin/CrudTable.vue'
import {
  adminBookings,
  adminEquipment,
  adminOrderStages,
  adminOrders,
} from '../../api/admin'

const columns = [
  { title: '訂單編號', dataIndex: 'order_no', width: 200, fixed: 'left' },
  { title: '設備代碼', dataIndex: 'equipment_code', width: 160 },
  { title: '開始時間', dataIndex: 'started_at', width: 180, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
  { title: '結束時間', dataIndex: 'ended_at', width: 180, sorter: true,
    customRender: ({ value }) => value ? value.replace('T', ' ').slice(0, 19) : '—',
  },
]

const formFields = [
  { name: 'order', label: '訂單', type: 'select', required: true,
    optionsResource: adminOrders, optionLabel: 'order_no', span: 12 },
  { name: 'equipment', label: '設備', type: 'select', required: true,
    optionsResource: adminEquipment, optionLabel: 'code', span: 12 },
  { name: 'stage', label: '對應階段', type: 'select',
    optionsResource: adminOrderStages, optionLabel: 'order_no',
    nullableEmpty: true, span: 12,
    help: '可選:綁定到特定的 OrderStage' },
  { name: 'started_at', label: '開始時間', type: 'datetime', required: true, span: 12 },
  { name: 'ended_at', label: '結束時間', type: 'datetime', required: true, span: 12 },
]
</script>
